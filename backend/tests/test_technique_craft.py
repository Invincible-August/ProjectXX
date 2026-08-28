"""
功法自研 P1：协议常量、YAML 解析、卡片使用、草稿、镶嵌、条件词条、定稿与装备。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.constants.technique import TECHNIQUE_SLOT_ART, TECHNIQUE_SLOT_MAIN
from app.constants.technique_craft import (
    CARD_BLANK_ID,
    CARD_FORMAL_EFFICACY_ID,
    CARD_FORMAL_ELEMENT_ID,
    CARD_MANUAL_ID,
    CARD_TYPE_EFFICACY_ID,
    CARD_TYPE_ELEMENT_ID,
    ERR_CRAFT_CARD,
    ERR_CRAFT_CULTIVATE,
    ERR_CRAFT_EMBED,
    ERR_CRAFT_EQUIP_ROLE,
    ERR_CRAFT_FINALIZE,
    ERR_CRAFT_LEARN,
    ERR_CRAFT_MANUAL,
    element_ids_from_spirit_root_tags,
)
from app.db.models.research import PrivateTechnique
from app.db.models.technique import CharacterTechnique
from app.services.technique_service import TechniqueService
from app.domain.technique_craft import filter_affixes, roll_three
from app.core.config import get_settings
from app.db.models.inventory_item import InventoryItem
from app.db.models.research import ResearchSession
from app.db.models.technique_craft import TechniqueResearchDraft
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


def test_learner_meets_manual_rank_qi_refining_needs_qi_refining() -> None:
    from app.domain.technique_craft import learner_meets_manual_rank

    assert learner_meets_manual_rank("qi_refining", "body_tempering") is True
    assert learner_meets_manual_rank("body_tempering", "qi_refining") is False
    assert learner_meets_manual_rank("qi_refining", "qi_refining") is True
    assert learner_meets_manual_rank("unknown_major", "body_tempering") is False
    assert learner_meets_manual_rank("body_tempering", "unknown_rank") is False


def test_technique_craft_config_loads() -> None:
    clear_game_config_cache()
    craft = get_game_config().research.technique_craft
    assert abs(craft.blank_to_type_p_element - 0.5) < 1e-6
    assert "spell_attack" in craft.efficacy_weights
    assert craft.embed_fail_rate >= 0
    assert "body_tempering" in craft.ranks
    assert len(craft.affixes) >= 6


def test_technique_manual_catalog_and_print_cost_load() -> None:
    from app.constants.inventory import UseEffectKind
    from app.constants.technique_craft import CARD_MANUAL_ID
    from app.services.realm_config import clear_game_config_cache, get_game_config

    clear_game_config_cache()
    cfg = get_game_config()
    craft = cfg.research.technique_craft
    assert craft.print_manual_cost_cultivation == 500
    assert craft.print_manual_cost_body == 500
    item = cfg.inventory.items[CARD_MANUAL_ID]
    assert item.item_type == "manual"
    assert item.manual_kind == "technique"
    assert item.tradable is True
    assert item.max_stack == 1
    assert (item.use_effect or {}).get("kind") == UseEffectKind.TECH_MANUAL_LEARN


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


async def _grant_formal_element(session, char, elements: list[str]) -> str:
    """Insert one formal element card and return its item_uid."""
    inv = InventoryService(session)
    await inv.add_item(
        char.id,
        item_type="consumable",
        item_id=CARD_FORMAL_ELEMENT_ID,
        quantity=1,
        meta={"elements": elements},
    )
    await session.flush()
    row = (
        await session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == char.id,
                InventoryItem.item_id == CARD_FORMAL_ELEMENT_ID,
                InventoryItem.quantity > 0,
            )
            .order_by(InventoryItem.id.desc())
            .limit(1)
        )
    ).scalar_one()
    return str(row.item_uid)


async def _formal_element_left(session, char_id: int) -> list[InventoryItem]:
    return list(
        (
            await session.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == char_id,
                    InventoryItem.item_id == CARD_FORMAL_ELEMENT_ID,
                    InventoryItem.quantity > 0,
                )
            )
        ).scalars()
    )


def test_embed_fail_consumes_card_keeps_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: False,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "embed_fail.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "embedfail@test.com", "镶嵌失败测")
                svc = TechniqueCraftService(session)
                draft = await svc.create_draft(char)
                uid = await _grant_formal_element(session, char, ["metal", "fire"])
                await session.commit()
                out = await svc.embed_card(char, int(draft["id"]), uid)
                await session.commit()
                assert out["elements"] == []
                assert not out["efficacy"]
                assert out["id"] == draft["id"]
                assert await _formal_element_left(session, char.id) == []
                listed = await svc.list_drafts(char)
                assert len(listed) == 1
                assert listed[0]["elements"] == []
                assert listed[0]["efficacy"] in (None, "")

    _run(_body())


def test_embed_success_locks_elements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "embed_ok.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "embedok@test.com", "镶嵌成功测")
                svc = TechniqueCraftService(session)
                draft = await svc.create_draft(char)
                uid = await _grant_formal_element(session, char, ["metal", "fire"])
                await session.commit()
                out = await svc.embed_card(char, int(draft["id"]), uid)
                await session.commit()
                assert out["elements"] == ["metal", "fire"]
                assert not out["efficacy"]
                assert await _formal_element_left(session, char.id) == []
                listed = await svc.list_drafts(char)
                assert listed[0]["elements"] == ["metal", "fire"]

    _run(_body())


def test_embed_second_element_card_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "embed_lock.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "embedlock@test.com", "二次镶嵌测")
                svc = TechniqueCraftService(session)
                draft = await svc.create_draft(char)
                first_uid = await _grant_formal_element(session, char, ["metal"])
                await session.commit()
                await svc.embed_card(char, int(draft["id"]), first_uid)
                await session.commit()
                second_uid = await _grant_formal_element(session, char, ["fire"])
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.embed_card(char, int(draft["id"]), second_uid)
                assert exc.value.code == ERR_CRAFT_EMBED
                await session.commit()
                left = await _formal_element_left(session, char.id)
                assert len(left) == 1
                assert str(left[0].item_uid) == second_uid
                listed = await svc.list_drafts(char)
                assert listed[0]["elements"] == ["metal"]

    _run(_body())


def test_filter_hides_martial_affix_from_spell() -> None:
    craft = get_game_config().research.technique_craft
    got = filter_affixes(craft.affixes, efficacy="spell_attack")
    ids = {str(getattr(item, "affix_id", item)) for item in got}
    assert "sa_edge" in ids
    assert "ma_edge" not in ids
    assert "mb_ward" not in ids
    assert "ib_bone" not in ids


def test_affix_roll_three_duplicates_when_pool_has_one() -> None:
    options = roll_three(["sa_edge"])
    assert len(options) == 3
    assert options == ["sa_edge", "sa_edge", "sa_edge"]


async def _grant_formal_efficacy(session, char, efficacy: str) -> str:
    """Insert one formal efficacy card and return its item_uid."""
    inv = InventoryService(session)
    await inv.add_item(
        char.id,
        item_type="consumable",
        item_id=CARD_FORMAL_EFFICACY_ID,
        quantity=1,
        meta={"efficacy": efficacy},
    )
    await session.flush()
    row = (
        await session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == char.id,
                InventoryItem.item_id == CARD_FORMAL_EFFICACY_ID,
                InventoryItem.quantity > 0,
            )
            .order_by(InventoryItem.id.desc())
            .limit(1)
        )
    ).scalar_one()
    return str(row.item_uid)


async def _ready_embedded_draft(session, char, svc, *, elements: list[str], efficacy: str):
    """Create a draft and embed both formal cards (caller patches embed success)."""
    draft = await svc.create_draft(char)
    el_uid = await _grant_formal_element(session, char, elements)
    await svc.embed_card(char, int(draft["id"]), el_uid)
    ef_uid = await _grant_formal_efficacy(session, char, efficacy)
    await svc.embed_card(char, int(draft["id"]), ef_uid)
    await session.commit()
    return int(draft["id"])


def test_conditions_allow_both_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "cond_empty.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "condempty@test.com", "条件空测")
                svc = TechniqueCraftService(session)
                draft_id = await _ready_embedded_draft(
                    session, char, svc, elements=["metal", "fire"], efficacy="spell_attack"
                )
                out = await svc.set_conditions(char, draft_id)
                await session.commit()
                assert out["element_limit"] in (None, "")
                assert out["weapon_limit"] in (None, "")
                listed = await svc.list_drafts(char)
                assert listed[0]["element_limit"] in (None, "")
                assert listed[0]["weapon_limit"] in (None, "")

    _run(_body())


def test_choose_affix_sets_chosen_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "choose_affix.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "chooseaffix@test.com", "选词条测")
                svc = TechniqueCraftService(session)
                draft_id = await _ready_embedded_draft(
                    session, char, svc, elements=["metal"], efficacy="spell_attack"
                )
                rolled = await svc.roll_affix(char, draft_id, slot=0)
                await session.commit()
                slot0 = rolled["affixes"][0]
                assert len(slot0["options"]) == 3
                pick = str(slot0["options"][0])
                chosen = await svc.choose_affix(char, draft_id, slot=0, affix_id=pick)
                await session.commit()
                assert chosen["affixes"][0]["chosen_id"] == pick

    _run(_body())


def test_reroll_affix_clears_levels_and_deducts_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "reroll_affix.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "rerollaffix@test.com", "重随测")
                svc = TechniqueCraftService(session)
                draft_id = await _ready_embedded_draft(
                    session, char, svc, elements=["metal"], efficacy="spell_attack"
                )
                rolled = await svc.roll_affix(char, draft_id, slot=0)
                pick = str(rolled["affixes"][0]["options"][0])
                await svc.choose_affix(char, draft_id, slot=0, affix_id=pick)
                await session.commit()

                row = await session.get(TechniqueResearchDraft, draft_id)
                assert row is not None
                slots = json.loads(row.affixes_json or "[]")
                slots[0]["chosen_level"] = 3
                slots[0]["upgrade_count"] = 2
                row.affixes_json = json.dumps(slots, ensure_ascii=False)
                await session.commit()
                await session.refresh(char)

                cost = int(get_game_config().research.technique_craft.affix_reroll_cost[0])
                before = int(char.cultivation_points)
                out = await svc.reroll_affix(char, draft_id, slot=0)
                await session.commit()
                await session.refresh(char)

                slot0 = out["affixes"][0]
                assert len(slot0["options"]) == 3
                assert int(slot0.get("chosen_level") or 0) == 0
                assert int(slot0.get("upgrade_count") or 0) == 0
                assert int(char.cultivation_points) == before - cost

    _run(_body())


async def _ready_chosen_draft(
    session,
    char,
    svc,
    *,
    elements: list[str],
    efficacy: str,
):
    """Embed both cards, confirm empty conditions, roll and lock slot 0."""
    draft_id = await _ready_embedded_draft(
        session, char, svc, elements=elements, efficacy=efficacy
    )
    await svc.set_conditions(char, draft_id)
    rolled = await svc.roll_affix(char, draft_id, slot=0)
    pick = str(rolled["affixes"][0]["options"][0])
    await svc.choose_affix(char, draft_id, slot=0, affix_id=pick)
    await session.commit()
    return draft_id, pick


def test_finalize_requires_affix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "fin_affix.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "finaffix@test.com", "定稿词条测")
                svc = TechniqueCraftService(session)
                draft_id = await _ready_embedded_draft(
                    session, char, svc, elements=["metal"], efficacy="spell_attack"
                )
                await svc.set_conditions(char, draft_id)
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.finalize_draft(char, draft_id, label_zh="玄铁吐纳残篇")
                assert exc.value.code == ERR_CRAFT_FINALIZE

    _run(_body())


def test_finalize_enters_learn_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "fin_learn.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "finlearn@test.com", "定稿已学测")
                svc = TechniqueCraftService(session)
                draft_id, pick = await _ready_chosen_draft(
                    session, char, svc, elements=["metal"], efficacy="spell_attack"
                )
                out = await svc.finalize_draft(char, draft_id, label_zh="玄铁吐纳残篇")
                await session.commit()
                assert out["phase"] == "finalized"
                tech_id = str((out.get("private") or {}).get("id") or out.get("technique_id") or "")
                assert tech_id.startswith("custom:technique:")
                assert str(char.id) in tech_id

                drafts = await svc.list_drafts(char)
                assert all(int(row["id"]) != draft_id for row in drafts)

                private = (
                    await session.execute(
                        select(PrivateTechnique).where(
                            PrivateTechnique.technique_id == tech_id,
                        )
                    )
                ).scalar_one()
                assert int(private.author_character_id) == int(char.id)
                payload = json.loads(private.payload_json or "{}")
                assert payload.get("efficacy") == "spell_attack"

                learned = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == char.id,
                            CharacterTechnique.technique_id == tech_id,
                        )
                    )
                ).scalar_one()
                assert learned.source == "research"

                listed = await TechniqueService(session).list_my_techniques(char)
                custom = next((t for t in listed if t["id"] == tech_id), None)
                assert custom is not None
                assert custom["name"] == "玄铁吐纳残篇"
                assert custom["efficacy"] == "spell_attack"
                assert custom["author_character_id"] == char.id
                assert custom["cultivable"] is True

                mine = await ResearchService(session).list_mine(char)
                mine_tech = next((t for t in mine if t["id"] == tech_id), None)
                assert mine_tech is not None
                assert mine_tech["efficacy"] == "spell_attack"
                assert mine_tech["author_character_id"] == char.id
                assert mine_tech["cultivable"] is True
                assert pick in (mine_tech.get("affix_ids") or [])

    _run(_body())


def test_equip_attack_spell_as_main_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "equip_atk.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "equipatk@test.com", "主槽拒绝测")
                svc = TechniqueCraftService(session)
                draft_id, _pick = await _ready_chosen_draft(
                    session, char, svc, elements=["metal"], efficacy="spell_attack"
                )
                out = await svc.finalize_draft(char, draft_id, label_zh="玄铁吐纳残篇")
                await session.commit()
                tech_id = str((out.get("private") or {}).get("id") or out.get("technique_id") or "")
                tech = TechniqueService(session)
                with pytest.raises(AppError) as exc:
                    await tech.equip_technique(
                        char,
                        technique_id=tech_id,
                        slot_type=TECHNIQUE_SLOT_MAIN,
                        slot_index=0,
                    )
                assert exc.value.code == ERR_CRAFT_EQUIP_ROLE
                assert "主功法" in exc.value.message
                page = await tech.equip_technique(
                    char,
                    technique_id=tech_id,
                    slot_type=TECHNIQUE_SLOT_ART,
                    slot_index=0,
                )
                arts = [
                    s for s in page["loadout"]["slots"] if s["slot_type"] == TECHNIQUE_SLOT_ART
                ]
                assert arts[0]["technique_id"] == tech_id

    _run(_body())


def test_equip_idle_spirit_as_main_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "equip_idle.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "equipidle@test.com", "主槽允许测")
                svc = TechniqueCraftService(session)
                draft_id, _pick = await _ready_chosen_draft(
                    session, char, svc, elements=["metal"], efficacy="idle_spirit"
                )
                out = await svc.finalize_draft(char, draft_id, label_zh="玄铁吐纳残篇")
                await session.commit()
                tech_id = str((out.get("private") or {}).get("id") or out.get("technique_id") or "")
                page = await TechniqueService(session).equip_technique(
                    char,
                    technique_id=tech_id,
                    slot_type=TECHNIQUE_SLOT_MAIN,
                    slot_index=0,
                )
                mains = [
                    s for s in page["loadout"]["slots"] if s["slot_type"] == TECHNIQUE_SLOT_MAIN
                ]
                assert mains[0]["technique_id"] == tech_id

    _run(_body())


async def _finalize_spell_attack(session, char, svc) -> str:
    """Embed, choose affix, finalize a spell_attack original. Returns technique_id."""
    draft_id, _pick = await _ready_chosen_draft(
        session, char, svc, elements=["metal"], efficacy="spell_attack"
    )
    out = await svc.finalize_draft(char, draft_id, label_zh="玄铁吐纳残篇")
    await session.commit()
    return str((out.get("private") or {}).get("id") or out.get("technique_id") or "")


async def _load_private(session, tech_id: str) -> PrivateTechnique:
    return (
        await session.execute(
            select(PrivateTechnique).where(PrivateTechnique.technique_id == tech_id)
        )
    ).scalar_one()


async def _grant_manual(session, character_id: int, meta: dict) -> str:
    """Insert one unstacked tech_manual and return its item_uid."""
    inv = InventoryService(session)
    await inv.add_item(
        character_id,
        item_type="manual",
        item_id=CARD_MANUAL_ID,
        quantity=1,
        meta=meta,
    )
    await session.flush()
    row = (
        await session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_id == CARD_MANUAL_ID,
                InventoryItem.quantity > 0,
            )
            .order_by(InventoryItem.id.desc())
            .limit(1)
        )
    ).scalar_one()
    return str(row.item_uid)


async def _manual_qty(session, item_uid: str) -> int:
    row = (
        await session.execute(
            select(InventoryItem).where(InventoryItem.item_uid == item_uid)
        )
    ).scalar_one_or_none()
    if row is None:
        return 0
    return int(row.quantity)


def test_two_attack_upgrades_second_costs_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nth base upgrade uses cost index N-1; second attack click is more expensive."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "base_up.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "baseup@test.com", "基础加成测")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, char, svc)
                await session.refresh(char)
                craft = get_game_config().research.technique_craft
                before = int(char.cultivation_points)

                first = await svc.upgrade_base(char, tech_id, stat="attack")
                await session.commit()
                await session.refresh(char)
                after_first = int(char.cultivation_points)
                first_cost = before - after_first

                second = await svc.upgrade_base(char, tech_id, stat="attack")
                await session.commit()
                await session.refresh(char)
                second_cost = after_first - int(char.cultivation_points)

                assert first_cost == int(craft.spirit_upgrade_cost[0])
                assert second_cost == int(craft.spirit_upgrade_cost[1])
                assert second_cost > first_cost

                private = await _load_private(session, tech_id)
                payload = json.loads(private.payload_json or "{}")
                assert int((payload.get("base") or {}).get("attack") or 0) == 2
                expected_pts = int(craft.base_bonus_points[0]) + int(craft.base_bonus_points[1])
                assert int(payload.get("upgrade_points") or 0) == expected_pts
                listed = await TechniqueService(session).list_my_techniques(char)
                custom = next((t for t in listed if t["id"] == tech_id), None)
                assert custom is not None
                per = float(craft.base_stat_per_click)
                affix_stats = float(craft.affixes["sa_edge"].stats.get("magic_atk") or 0)
                # chosen_level stays 0; ATTR = clicks * per + affix * (1 + mult * level)
                assert custom["stats"].get("magic_atk") == pytest.approx(
                    2 * per + affix_stats * (1.0 + float(craft.affix_level_mult) * 0)
                )
                assert first["base"]["attack"] == 1
                assert second["base"]["attack"] == 2

    _run(_body())


def test_breakthrough_fail_keeps_points_and_rank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_breakthrough_success",
        lambda *_a, **_k: False,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_fail.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "btfail@test.com", "突破失败测")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, char, svc)
                char.major_realm = "qi_refining"
                private = await _load_private(session, tech_id)
                payload = json.loads(private.payload_json or "{}")
                payload["upgrade_points"] = 100
                private.payload_json = json.dumps(payload, ensure_ascii=False)
                await session.commit()
                await session.refresh(char)
                craft = get_game_config().research.technique_craft
                before_pts = int(payload["upgrade_points"])
                before_rank = str(private.major_rank)
                before_cult = int(char.cultivation_points)

                await svc.breakthrough(char, tech_id)
                await session.commit()
                await session.refresh(char)
                private = await _load_private(session, tech_id)
                payload = json.loads(private.payload_json or "{}")
                assert str(private.major_rank) == before_rank == "body_tempering"
                assert int(payload.get("upgrade_points") or 0) == before_pts
                assert int(char.cultivation_points) == before_cult - int(
                    craft.breakthrough_cost_cultivation
                )

    _run(_body())


def test_breakthrough_success_raises_rank_keeps_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_breakthrough_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_ok.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "btok@test.com", "突破成功测")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, char, svc)
                char.major_realm = "qi_refining"
                private = await _load_private(session, tech_id)
                payload = json.loads(private.payload_json or "{}")
                payload["upgrade_points"] = 100
                private.payload_json = json.dumps(payload, ensure_ascii=False)
                await session.commit()
                await session.refresh(char)
                before_pts = int(payload["upgrade_points"])

                out = await svc.breakthrough(char, tech_id)
                await session.commit()
                private = await _load_private(session, tech_id)
                payload = json.loads(private.payload_json or "{}")
                assert str(private.major_rank) == "qi_refining"
                assert out["major_rank"] == "qi_refining"
                assert int(payload.get("upgrade_points") or 0) == before_pts
                assert len(payload.get("affixes") or []) >= 2

                char.major_realm = "body_tempering"
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.breakthrough(char, tech_id)
                assert exc.value.code == ERR_CRAFT_CULTIVATE

    _run(_body())


def test_affix_upgrade_fail_keeps_level_still_charges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_affix_upgrade_success",
        lambda *_a, **_k: False,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "affix_fail.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "affixfail@test.com", "词条失败测")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, char, svc)
                await session.refresh(char)
                craft = get_game_config().research.technique_craft
                cost = int(craft.affix_upgrade_cost[0])
                before = int(char.cultivation_points)
                private = await _load_private(session, tech_id)
                level_before = int(
                    (json.loads(private.payload_json or "{}").get("affixes") or [{}])[0].get(
                        "chosen_level"
                    )
                    or 0
                )

                await svc.upgrade_affix(char, tech_id, slot=0)
                await session.commit()
                await session.refresh(char)
                private = await _load_private(session, tech_id)
                payload = json.loads(private.payload_json or "{}")
                assert int((payload.get("affixes") or [{}])[0].get("chosen_level") or 0) == level_before
                assert int(char.cultivation_points) == before - cost

    _run(_body())


def test_print_manual_consumes_points_and_grants_unmerged_books(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "print_ok.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "printok@test.com", "印制测")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, char, svc)
                craft = get_game_config().research.technique_craft
                cost = int(craft.print_manual_cost_cultivation)
                char.cultivation_points = cost * 4
                await session.commit()
                await session.refresh(char)
                private = await _load_private(session, tech_id)
                payload_before = str(private.payload_json)
                before = int(char.cultivation_points)

                first = await svc.print_manual(char, tech_id)
                await session.commit()
                second = await svc.print_manual(char, tech_id)
                await session.commit()
                await session.refresh(char)

                assert int(char.cultivation_points) == before - 2 * cost
                private = await _load_private(session, tech_id)
                assert str(private.payload_json) == payload_before

                rows = list(
                    (
                        await session.execute(
                            select(InventoryItem).where(
                                InventoryItem.character_id == char.id,
                                InventoryItem.item_id == CARD_MANUAL_ID,
                                InventoryItem.quantity > 0,
                            )
                        )
                    ).scalars()
                )
                assert len(rows) == 2
                for row in rows:
                    assert row.item_type == "manual"
                    meta = json.loads(row.meta_json or "{}")
                    assert meta["manual_kind"] == "technique"
                    assert meta["origin_technique_id"] == tech_id
                    assert int(meta["author_character_id"]) == int(char.id)
                    assert meta["label_zh"] == "玄铁吐纳残篇"
                    assert "payload" in meta
                    assert "stats" in meta
                    assert "affix_ids" in meta
                    assert "major_rank" in meta
                assert first["item_id"] == CARD_MANUAL_ID
                assert second["item_id"] == CARD_MANUAL_ID

    _run(_body())


def test_print_manual_rejected_for_non_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "print_na.db") as factory:
            async with factory() as session:
                char = await _prepare_researcher(session, "printna@test.com", "非作者测")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, char, svc)
                private = await _load_private(session, tech_id)
                private.author_character_id = int(char.id) + 999
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await svc.print_manual(char, tech_id)
                assert exc.value.code == ERR_CRAFT_MANUAL
                assert exc.value.message == "仅原创者可制成秘籍"

    _run(_body())


def test_use_manual_author_cannot_learn_own_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "learn_self.db") as factory:
            async with factory() as session:
                author = await _prepare_researcher(session, "learnself@test.com", "自学拒")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, author, svc)
                craft = get_game_config().research.technique_craft
                author.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                await session.commit()
                printed = await svc.print_manual(author, tech_id)
                await session.commit()
                uid = (
                    await session.execute(
                        select(InventoryItem.item_uid).where(
                            InventoryItem.character_id == author.id,
                            InventoryItem.item_id == CARD_MANUAL_ID,
                            InventoryItem.quantity > 0,
                        )
                    )
                ).scalar_one()
                inv = InventoryService(session)
                with pytest.raises(AppError) as exc:
                    await inv.use_item(author, item_uid=str(uid))
                assert exc.value.code == ERR_CRAFT_MANUAL
                assert exc.value.message == "不可学习自己的秘籍"
                assert printed["snapshot"]["origin_technique_id"] == tech_id
                assert await _manual_qty(session, str(uid)) == 1

    _run(_body())


def test_use_manual_same_origin_twice_does_not_consume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "learn_dup.db") as factory:
            async with factory() as session:
                author = await _prepare_researcher(session, "learndupa@test.com", "印书甲")
                learner = await _prepare_researcher(session, "learndupb@test.com", "学书乙")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, author, svc)
                craft = get_game_config().research.technique_craft
                author.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                learner.major_realm = "qi_refining"
                await session.commit()
                printed = await svc.print_manual(author, tech_id)
                await session.commit()
                snapshot = printed["snapshot"]
                first_uid = await _grant_manual(session, learner.id, snapshot)
                second_uid = await _grant_manual(session, learner.id, snapshot)
                await session.commit()
                inv = InventoryService(session)
                await inv.use_item(learner, item_uid=first_uid)
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await inv.use_item(learner, item_uid=second_uid)
                assert exc.value.code == ERR_CRAFT_LEARN
                assert exc.value.message == "已习得该功法"
                assert await _manual_qty(session, second_uid) == 1

    _run(_body())


def test_use_manual_below_rank_does_not_consume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "learn_rank.db") as factory:
            async with factory() as session:
                author = await _prepare_researcher(session, "learnranka@test.com", "印书丙")
                learner = await _prepare_researcher(session, "learnrankb@test.com", "学书丁")
                learner.major_realm = "body_tempering"
                await session.commit()
                snapshot = {
                    "manual_kind": "technique",
                    "origin_technique_id": "custom:technique:9:deadbeef",
                    "author_character_id": int(author.id),
                    "label_zh": "高阶残篇",
                    "major_rank": "qi_refining",
                    "payload": {"efficacy": "spell_attack", "elements": ["metal"]},
                    "stats": {"magic_atk": 1.0},
                    "affix_ids": [],
                }
                uid = await _grant_manual(session, learner.id, snapshot)
                await session.commit()
                inv = InventoryService(session)
                with pytest.raises(AppError) as exc:
                    await inv.use_item(learner, item_uid=uid)
                assert exc.value.code == ERR_CRAFT_LEARN
                assert await _manual_qty(session, uid) == 1

    _run(_body())


def test_use_manual_learns_frozen_copy_and_consumes_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "learn_ok.db") as factory:
            async with factory() as session:
                author = await _prepare_researcher(session, "learnoka@test.com", "印书戊")
                learner = await _prepare_researcher(session, "learnokb@test.com", "学书己")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, author, svc)
                craft = get_game_config().research.technique_craft
                author.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                await session.commit()
                private = await _load_private(session, tech_id)
                payload_before = str(private.payload_json)
                printed = await svc.print_manual(author, tech_id)
                await session.commit()
                snapshot = printed["snapshot"]
                learner.major_realm = str(snapshot.get("major_rank") or "qi_refining")
                uid = await _grant_manual(session, learner.id, snapshot)
                await session.commit()

                inv = InventoryService(session)
                await inv.use_item(learner, item_uid=uid)
                await session.commit()

                listed = await TechniqueService(session).list_my_techniques(learner)
                copies = [
                    row
                    for row in listed
                    if str(row.get("author_character_id") or 0) == str(author.id)
                    and row.get("cultivable") is False
                ]
                assert len(copies) == 1
                copy_item = copies[0]
                learned = (
                    await session.execute(
                        select(CharacterTechnique).where(
                            CharacterTechnique.character_id == learner.id,
                            CharacterTechnique.technique_id == copy_item["id"],
                        )
                    )
                ).scalar_one()
                assert learned.source == "chance"
                assert copy_item["cultivable"] is False

                b_private = await _load_private(session, str(copy_item["id"]))
                assert int(b_private.character_id) == int(learner.id)
                assert int(b_private.author_character_id) == int(author.id)
                assert str(b_private.label_zh) == str(snapshot["label_zh"])
                assert str(b_private.major_rank) == str(snapshot["major_rank"])
                expected_payload = json.loads(json.dumps(snapshot["payload"]))
                expected_payload["origin_technique_id"] = snapshot["origin_technique_id"]
                assert json.loads(b_private.payload_json) == expected_payload
                assert json.loads(b_private.stats_json) == json.loads(
                    json.dumps(snapshot["stats"])
                )
                assert json.loads(json.dumps(copy_item.get("stats") or {})) == json.loads(
                    json.dumps(snapshot["stats"])
                )

                author_private = await _load_private(session, tech_id)
                assert str(author_private.payload_json) == payload_before
                assert await _manual_qty(session, uid) == 0

    _run(_body())


def test_copied_technique_cannot_upgrade_or_print(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Learned copies are listed as chance, not cultivable, and cannot upgrade or reprint."""
    monkeypatch.setattr(
        "app.services.technique_craft_service.roll_embed_success",
        lambda *_a, **_k: True,
        raising=False,
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "copy_ro.db") as factory:
            async with factory() as session:
                author = await _prepare_researcher(session, "copyroa@test.com", "只读甲")
                learner = await _prepare_researcher(session, "copyrob@test.com", "只读乙")
                svc = TechniqueCraftService(session)
                tech_id = await _finalize_spell_attack(session, author, svc)
                craft = get_game_config().research.technique_craft
                author.cultivation_points = int(craft.print_manual_cost_cultivation) * 2
                await session.commit()
                printed = await svc.print_manual(author, tech_id)
                await session.commit()
                snapshot = printed["snapshot"]
                learner.major_realm = str(snapshot.get("major_rank") or "qi_refining")
                uid = await _grant_manual(session, learner.id, snapshot)
                await session.commit()
                await InventoryService(session).use_item(learner, item_uid=uid)
                await session.commit()

                author_listed = await TechniqueService(session).list_my_techniques(author)
                original = next((t for t in author_listed if t["id"] == tech_id), None)
                assert original is not None
                assert original["source"] == "research"
                assert original["cultivable"] is True

                listed = await TechniqueService(session).list_my_techniques(learner)
                copies = [
                    row
                    for row in listed
                    if str(row.get("author_character_id") or 0) == str(author.id)
                ]
                assert len(copies) == 1
                copy_item = copies[0]
                assert copy_item["source"] == "chance"
                assert copy_item["cultivable"] is False

                with pytest.raises(AppError) as up_exc:
                    await svc.upgrade_base(learner, str(copy_item["id"]), stat="attack")
                assert up_exc.value.code == ERR_CRAFT_CULTIVATE

                with pytest.raises(AppError) as print_exc:
                    await svc.print_manual(learner, str(copy_item["id"]))
                assert print_exc.value.code == ERR_CRAFT_MANUAL

    _run(_body())
