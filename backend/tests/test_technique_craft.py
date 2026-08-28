"""
功法自研 P1：协议常量、YAML 解析、卡片使用、草稿创建/列表/放弃。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique_craft import (
    CARD_BLANK_ID,
    CARD_FORMAL_ELEMENT_ID,
    CARD_TYPE_EFFICACY_ID,
    CARD_TYPE_ELEMENT_ID,
    ERR_CRAFT_CARD,
    element_ids_from_spirit_root_tags,
)
from app.core.config import get_settings
from app.db.models.inventory_item import InventoryItem
from app.db.models.research import ResearchSession
from app.schemas.common import AppError
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.research_service import ResearchService
from app.services.technique_craft_service import TechniqueCraftService
from tests.async_db import open_test_session_factory, run_async as _run
from tests.test_research_technique_finalize import _prepare_researcher


def test_mixed_root_expands_to_five_elements() -> None:
    got = set(element_ids_from_spirit_root_tags(["mixed_root"]))
    assert got == {"metal", "wood", "water", "fire", "earth"}


def test_metal_root_only_metal() -> None:
    assert element_ids_from_spirit_root_tags(["metal_root"]) == ["metal"]


def test_technique_craft_config_loads() -> None:
    clear_game_config_cache()
    craft = get_game_config().research.technique_craft
    assert abs(craft.blank_to_type_p_element - 0.5) < 1e-6
    assert "spell_attack" in craft.efficacy_weights
    assert craft.embed_fail_rate >= 0
    assert "body_tempering" in craft.ranks
    assert len(craft.affixes) >= 6


def test_technique_craft_defaults_when_block_missing() -> None:
    from app.services.realm_config import _parse_research

    cfg = get_game_config()
    parsed = _parse_research(
        {"technique": {}, "formation": {}, "talisman": {}, "affixes": {}},
        combat_attrs=cfg.combat_attrs,
    )
    assert abs(parsed.technique_craft.blank_to_type_p_element - 0.5) < 1e-6
    assert "spell_attack" in parsed.technique_craft.efficacy_weights
    assert "body_tempering" in parsed.technique_craft.ranks
    assert len(parsed.technique_craft.affixes) >= 6


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


def test_add_item_with_meta_does_not_merge(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "meta.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "meta@test.com", "元数据测")
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="consumable",
                    item_id=CARD_FORMAL_ELEMENT_ID,
                    quantity=1,
                    meta={"elements": ["metal"]},
                )
                await inv.add_item(
                    char.id,
                    item_type="consumable",
                    item_id=CARD_FORMAL_ELEMENT_ID,
                    quantity=1,
                    meta={"elements": ["fire"]},
                )
                await session.commit()
                rows = list(
                    (
                        await session.execute(
                            select(InventoryItem).where(
                                InventoryItem.character_id == char.id,
                                InventoryItem.item_id == CARD_FORMAL_ELEMENT_ID,
                            )
                        )
                    ).scalars()
                )
                assert len(rows) == 2
                metas = {
                    tuple(json.loads(r.meta_json or "{}").get("elements") or [])
                    for r in rows
                }
                assert metas == {("metal",), ("fire",)}

    _run(_body())


def test_blank_card_becomes_type_card(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "blank.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "blank@test.com", "空白测")
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="consumable",
                    item_id=CARD_BLANK_ID,
                    quantity=1,
                )
                await session.commit()
                row = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == CARD_BLANK_ID,
                        )
                    )
                ).scalar_one()
                await inv.use_item(char, item_uid=row.item_uid)
                await session.commit()
                left = list(
                    (
                        await session.execute(
                            select(InventoryItem).where(
                                InventoryItem.character_id == char.id,
                                InventoryItem.item_id == CARD_BLANK_ID,
                                InventoryItem.quantity > 0,
                            )
                        )
                    ).scalars()
                )
                assert left == []
                type_ids = {
                    r.item_id
                    for r in (
                        await session.execute(
                            select(InventoryItem).where(
                                InventoryItem.character_id == char.id,
                                InventoryItem.quantity > 0,
                            )
                        )
                    ).scalars()
                }
                assert CARD_TYPE_ELEMENT_ID in type_ids or CARD_TYPE_EFFICACY_ID in type_ids

    _run(_body())


def test_formal_element_card_uses_actor_roots(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "formal.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "formal@test.com", "属性测")
                char.spirit_root_tags_json = json.dumps(["metal_root"])
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="consumable",
                    item_id=CARD_TYPE_ELEMENT_ID,
                    quantity=1,
                )
                await session.commit()
                row = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == CARD_TYPE_ELEMENT_ID,
                        )
                    )
                ).scalar_one()
                await inv.use_item(char, item_uid=row.item_uid)
                await session.commit()
                formal = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == CARD_FORMAL_ELEMENT_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                meta = json.loads(formal.meta_json or "{}")
                assert meta["elements"] == ["metal"]

    _run(_body())


def test_element_type_card_empty_pool_does_not_consume(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "empty.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "empty@test.com", "空灵根测")
                char.spirit_root_tags_json = json.dumps([])
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="consumable",
                    item_id=CARD_TYPE_ELEMENT_ID,
                    quantity=1,
                )
                await session.commit()
                row = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == CARD_TYPE_ELEMENT_ID,
                        )
                    )
                ).scalar_one()
                with pytest.raises(AppError) as exc:
                    await inv.use_item(char, item_uid=row.item_uid)
                assert exc.value.code == ERR_CRAFT_CARD
                await session.commit()
                left = (
                    await session.execute(
                        select(InventoryItem).where(
                            InventoryItem.character_id == char.id,
                            InventoryItem.item_id == CARD_TYPE_ELEMENT_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                assert int(left.quantity) == 1

    _run(_body())


def test_create_two_drafts_independent(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "drafts.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "drafts@test.com", "草稿测")
                svc = TechniqueCraftService(session)
                first = await svc.create_draft(char)
                second = await svc.create_draft(char)
                await session.commit()
                listed = await svc.list_drafts(char)
                assert len(listed) == 2
                ids = {row["id"] for row in listed}
                assert ids == {first["id"], second["id"]}
                for row in listed:
                    assert row["phase"] == "embedding"
                    assert row["can_finalize"] is False
                    assert row["elements"] == []
                    assert not row["efficacy"]
                await svc.abandon_draft(char, int(first["id"]))
                await session.commit()
                remaining = await svc.list_drafts(char)
                assert len(remaining) == 1
                assert remaining[0]["id"] == second["id"]

    _run(_body())


def test_create_session_technique_kind_rejected(tmp_path: Path) -> None:
    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "oldtech.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "oldtech@test.com", "旧会话测")
                svc = ResearchService(session)
                with pytest.raises(AppError) as exc:
                    await svc.create_session(
                        char,
                        kind="technique",
                        materials=[{"item_id": "herb_spirit_grass", "quantity": 2}],
                        spends={"cultivation_points": 20},
                    )
                assert exc.value.code == 40201
                assert "草稿" in exc.value.message

    _run(_body())


def test_leftover_technique_session_writes_rejected(tmp_path: Path) -> None:
    """Pre-existing R2 technique sessions cannot reroll/finalize and are omitted from open list."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "leftover.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "leftover@test.com", "遗留会话")
                leftover = ResearchSession(
                    character_id=char.id,
                    kind="technique",
                    phase="previewed",
                    materials_json='[{"item_id": "herb_spirit_grass", "quantity": 2}]',
                    spends_json='{"cultivation_points": 20}',
                    seed=1,
                    dice_roll=50,
                    affix_preview_json='[{"id": "phys_edge"}]',
                    reroll_count=0,
                    expires_at=None,
                )
                session.add(leftover)
                await session.commit()
                await session.refresh(leftover)

                svc = ResearchService(session)
                open_items = await svc.list_open_sessions(char)
                assert all(row["kind"] != "technique" for row in open_items)

                with pytest.raises(AppError) as reroll_exc:
                    await svc.reroll_session(char, int(leftover.id))
                assert reroll_exc.value.code == 40201
                assert reroll_exc.value.message == "请改用功法自研草稿接口"

                with pytest.raises(AppError) as fin_exc:
                    await svc.finalize_session(
                        char,
                        session_id=int(leftover.id),
                        label_zh="玄铁吐纳残篇",
                    )
                assert fin_exc.value.code == 40201
                assert fin_exc.value.message == "请改用功法自研草稿接口"

    _run(_body())
