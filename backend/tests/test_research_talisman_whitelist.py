"""
M8 R4: custom talisman research / whitelist / scribe / preload / item_trigger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import InventoryItem, User
from app.domain.talisman_battle import inject_item_triggers
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.autochess_service import AutochessService
from app.services.craft_service import CraftService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.research_service import ResearchService
from tests.async_db import open_test_session_factory, run_async as _run

_NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "autochess_rng_seed", 20260817)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _prepare_researcher(session, email: str, name: str):
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name, gender="male"),
    )
    await session.commit()
    char = await character_service.get_character_by_user_id(session, user.id)
    assert char is not None
    char.cultivation_points = 200
    inv = InventoryService(session)
    await inv.add_item(
        char.id,
        item_type="material",
        item_id="herb_spirit_grass",
        quantity=10,
    )
    await inv.add_item(
        char.id,
        item_type="material",
        item_id="talisman_paper",
        quantity=20,
    )
    await session.commit()
    return user, char


def test_research_catalog_opens_talisman() -> None:
    cfg = get_game_config()
    assert cfg.research.talisman.min_materials >= 1
    assert cfg.research.talisman.battle_enabled is True
    assert "first_hit_ward" in cfg.talisman_effects
    catalog = ResearchService(MagicMock()).get_catalog()
    kinds = {k["id"]: k["open"] for k in catalog["kinds"]}
    assert kinds["talisman"] is True


def test_inject_item_trigger_respects_enabled_switch() -> None:
    events = [
        {"type": "battle_start", "units": [{"uid": "main", "side": 0, "kind": "main"}]},
        {"type": "damage", "target": "main", "final": 1},
        {"type": "battle_end"},
    ]
    talismans = [{"label_zh": "护体残符", "source_label_zh": "自研", "effect_id": "first_hit_ward"}]
    off = inject_item_triggers(events, talismans, enabled=False, attacker_uids={"main"})
    assert all(e.get("type") != "item_trigger" for e in off)
    on = inject_item_triggers(events, talismans, enabled=True, attacker_uids={"main"})
    triggers = [e for e in on if e.get("type") == "item_trigger"]
    assert len(triggers) == 1
    assert triggers[0]["label_zh"] == "护体残符"


def test_talisman_illegal_effect_rejected(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r4bad.db") as factory:
            async with factory() as session:
                _user, char = await _prepare_researcher(session, "r4bad@test.com", "伪符甲")
                svc = ResearchService(session)
                created = await svc.create_session(
                    char,
                    kind="talisman",
                    materials=[{"item_id": "talisman_paper", "quantity": 1}],
                    spends={"cultivation_points": 10},
                    effect_id="not_a_real_effect",
                )
                assert created["kind"] == "talisman"
                with pytest.raises(AppError) as exc:
                    await svc.finalize_session(
                        char,
                        session_id=int(created["id"]),
                        label_zh="非法符",
                    )
                assert exc.value.code == 40204

    _run(_body())


def test_talisman_finalize_scribe_preload_and_battle(tmp_path: Path) -> None:
    """Whitelist finalize → scribe into bag → preload → PVE item_trigger Chinese log."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r4ok.db") as factory:
            async with factory() as session:
                user, char = await _prepare_researcher(session, "r4ok@test.com", "符研乙")
                svc = ResearchService(session)
                created = await svc.create_session(
                    char,
                    kind="talisman",
                    materials=[{"item_id": "talisman_paper", "quantity": 1}],
                    spends={"cultivation_points": 10},
                    effect_id="first_hit_ward",
                )
                assert created["phase"] == "drafting"
                assert created["effect_id"] == "first_hit_ward"
                finalized = await svc.finalize_session(
                    char,
                    session_id=int(created["id"]),
                    label_zh="护体残符",
                )
                await session.commit()
                assert finalized["phase"] == "finalized"
                tid = finalized["private"]["id"]
                assert tid.startswith("custom:talisman:")
                mine = await svc.list_mine(char)
                assert any(i["id"] == tid and i["kind"] == "talisman" for i in mine)

                craft = CraftService(session)
                scribed = await craft.scribe_talisman(char, template_id=tid, quantity=2)
                await session.commit()
                assert scribed["quantity"] == 2
                rows = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_type == "talisman",
                            InventoryItem.item_id == tid,
                        ),
                    )
                ).scalars().all()
                assert sum(int(r.quantity) for r in rows) == 2
                inv_id = int(rows[0].id)

                pre = await craft.set_talisman_preload(char, [inv_id])
                await session.commit()
                assert pre["slots"][0]["inventory_item_id"] == inv_id

                battle = await AutochessService(session).start_pve(
                    user,
                    "tutorial_slime",
                    now=_NOW,
                )
                await session.commit()
                events = battle["report"]["events"]
                triggers = [e for e in events if e.get("type") == "item_trigger"]
                assert triggers
                assert triggers[0]["label_zh"] == "护体残符"
                assert "符箓：护体残符" in "\n".join(battle["report"]["detailed_log"])
                left = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == tid,
                        ),
                    )
                ).scalars().all()
                assert sum(int(r.quantity) for r in left) == 1

    _run(_body())
