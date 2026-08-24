"""
M8 R2: custom technique research session / finalize / combat source label.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.character_service import CharacterService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.research_service import ResearchService
from app.services.technique_service import TechniqueService
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
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
    await InventoryService(session).add_item(
        char.id,
        item_type="material",
        item_id="herb_spirit_grass",
        quantity=10,
    )
    await session.commit()
    return char


def test_research_config_loads() -> None:
    cfg = get_game_config()
    assert "phys_edge" in cfg.research.affixes
    assert cfg.research.technique.min_materials >= 1


def test_create_session_rejects_illegal_materials(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r2bad.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "r2bad@test.com", "非法研")
                svc = ResearchService(session)
                with pytest.raises(AppError) as exc:
                    await svc.create_session(
                        char,
                        kind="technique",
                        materials=[{"item_id": "not_a_real_item", "quantity": 1}],
                        spends={"cultivation_points": 20},
                    )
                assert exc.value.code == 40200

    _run(_body())


def test_research_technique_finalize(tmp_path: Path) -> None:
    """Illegal materials already covered; finalize yields equippable custom technique."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r2ok.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "r2ok@test.com", "合法研")
                svc = ResearchService(session)
                created = await svc.create_session(
                    char,
                    kind="technique",
                    materials=[{"item_id": "herb_spirit_grass", "quantity": 2}],
                    spends={"cultivation_points": 20},
                )
                assert created["kind"] == "technique"
                assert created["phase"] in {"drafting", "previewed"}
                assert created["dice"]["purpose"] == "research_technique"
                assert created["affix_previews"]
                await session.commit()

                with pytest.raises(AppError) as review_exc:
                    await svc.submit_review(char, session_id=int(created["id"]))
                assert review_exc.value.code == 40210

                finalized = await svc.finalize_session(
                    char,
                    session_id=int(created["id"]),
                    label_zh="玄铁吐纳残篇",
                )
                await session.commit()
                assert finalized["phase"] == "finalized"
                assert finalized["private"]["source_label_zh"] == "自研"
                tech_id = finalized["private"]["id"]
                assert tech_id.startswith("custom:technique:")

                listed = await TechniqueService(session).list_my_techniques(char)
                custom = next((t for t in listed if t["id"] == tech_id), None)
                assert custom is not None
                assert custom["source_label_zh"] == "自研"
                assert custom["name"] == "玄铁吐纳残篇"

                packed = await CharacterService(session).build_combat_attrs(char)
                tech_row = next(
                    (r for r in packed["combat"]["breakdown"] if r.get("source") == "technique"),
                    None,
                )
                assert tech_row is not None
                custom_stats = custom.get("stats") or {}
                for key, value in custom_stats.items():
                    if abs(float(value or 0)) > 1e-9:
                        assert float(tech_row.get(key) or 0) >= float(value)
                summary = packed["technique_summary"]
                custom_sum = next((t for t in summary if t["id"] == tech_id), None)
                assert custom_sum is not None
                assert custom_sum.get("source_label_zh") == "自研"

    _run(_body())
