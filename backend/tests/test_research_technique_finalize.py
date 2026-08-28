"""
M8 功法自研定稿：新草稿路径写入已学列表后可装备。
旧 R2 材料会话用例已删除；technique kind 拒绝见 test_technique_craft。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique import TECHNIQUE_SLOT_MAIN
from app.constants.technique_craft import CARD_FORMAL_EFFICACY_ID, CARD_FORMAL_ELEMENT_ID
from app.core.config import get_settings
from app.db.models import User
from app.db.models.inventory_item import InventoryItem
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.character_service import CharacterService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.technique_craft_service import TechniqueCraftService
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


async def _grant_formal(session, char, item_id: str, meta: dict) -> str:
    inv = InventoryService(session)
    await inv.add_item(
        char.id, item_type="consumable", item_id=item_id, quantity=1, meta=meta
    )
    await session.flush()
    row = (
        await session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == char.id,
                InventoryItem.item_id == item_id,
                InventoryItem.quantity > 0,
            )
            .order_by(InventoryItem.id.desc())
            .limit(1)
        )
    ).scalar_one()
    return str(row.item_uid)


def test_research_technique_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the new finalize path, the custom technique is learned and equippable."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "r2ok.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "r2ok@test.com", "合法研")
                craft = TechniqueCraftService(session)
                draft = await craft.create_draft(char)
                draft_id = int(draft["id"])
                el_uid = await _grant_formal(
                    session, char, CARD_FORMAL_ELEMENT_ID, {"elements": ["metal"]}
                )
                await craft.embed_card(char, draft_id, el_uid)
                ef_uid = await _grant_formal(
                    session, char, CARD_FORMAL_EFFICACY_ID, {"efficacy": "idle_spirit"}
                )
                await craft.embed_card(char, draft_id, ef_uid)
                await craft.set_conditions(char, draft_id)
                rolled = await craft.roll_affix(char, draft_id, slot=0)
                pick = str(rolled["affixes"][0]["options"][0])
                await craft.choose_affix(char, draft_id, slot=0, affix_id=pick)
                await session.commit()
                finalized = await craft.finalize_draft(
                    char, draft_id, label_zh="玄铁吐纳残篇"
                )
                await session.commit()
                assert finalized["phase"] == "finalized"
                tech_id = str(
                    (finalized.get("private") or {}).get("id")
                    or finalized.get("technique_id")
                    or ""
                )
                assert tech_id.startswith("custom:technique:")
                assert (finalized.get("private") or {}).get("source_label_zh") == "自研"

                listed = await TechniqueService(session).list_my_techniques(char)
                custom = next((t for t in listed if t["id"] == tech_id), None)
                assert custom is not None
                assert custom["source_label_zh"] == "自研"
                assert custom["name"] == "玄铁吐纳残篇"
                assert custom["efficacy"] == "idle_spirit"
                assert custom["cultivable"] is True

                page = await TechniqueService(session).equip_technique(
                    char,
                    technique_id=tech_id,
                    slot_type=TECHNIQUE_SLOT_MAIN,
                    slot_index=0,
                )
                mains = [
                    s
                    for s in page["loadout"]["slots"]
                    if s["slot_type"] == TECHNIQUE_SLOT_MAIN
                ]
                assert mains[0]["technique_id"] == tech_id

                packed = await CharacterService(session).build_combat_attrs(char)
                summary = packed["technique_summary"]
                custom_sum = next((t for t in summary if t["id"] == tech_id), None)
                assert custom_sum is not None
                assert custom_sum.get("source_label_zh") == "自研"

    _run(_body())
