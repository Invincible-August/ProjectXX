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
    CARD_TYPE_EFFICACY_ID,
    CARD_TYPE_ELEMENT_ID,
    ERR_CRAFT_CARD,
    ERR_CRAFT_EMBED,
    ERR_CRAFT_EQUIP_ROLE,
    ERR_CRAFT_FINALIZE,
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
