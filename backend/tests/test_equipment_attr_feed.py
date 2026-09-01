"""
M8 R1 equipment attr feed tests (ATTR-D02 / IDLE-R01 / DICE-R01).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.equipment import (
    EQUIPMENT_SLOT_ACCESSORY_1,
    EQUIPMENT_SLOT_ACCESSORY_2,
    EQUIPMENT_SLOT_FUBAO,
    EQUIPMENT_SLOT_LABELS_ZH,
    EQUIPMENT_SLOT_WEAPON_1,
    EQUIPMENT_SLOT_WEAPON_2,
    EQUIPMENT_SLOTS,
    compatible_pointer_slots,
)
from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.character_service import CharacterService
from app.services.dice_service import DiceService
from app.services.env_preview_service import resolve_idle_bonus_channels
from app.services.equipment_service import EquipmentService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache, get_game_config
from tests.async_db import open_test_session_factory, run_async as _run


def test_equipment_slot_labels_zh_player_facing() -> None:
    """Player-facing slot names stay Chinese; machine ids stay English."""
    assert EQUIPMENT_SLOT_LABELS_ZH[EQUIPMENT_SLOT_WEAPON_1] == "主手"
    assert EQUIPMENT_SLOT_LABELS_ZH[EQUIPMENT_SLOT_WEAPON_2] == "副手"
    assert EQUIPMENT_SLOT_LABELS_ZH[EQUIPMENT_SLOT_ACCESSORY_1] == "项链"
    assert EQUIPMENT_SLOT_LABELS_ZH[EQUIPMENT_SLOT_ACCESSORY_2] == "饰品"
    assert EQUIPMENT_SLOT_LABELS_ZH[EQUIPMENT_SLOT_FUBAO] == "符宝"
    assert set(EQUIPMENT_SLOT_LABELS_ZH) == set(EQUIPMENT_SLOTS)


def test_compatible_pointer_slots_catalog_kinds() -> None:
    """YAML slot/equip_kind maps onto 17-zone pointer ids (slot picker filter)."""
    assert set(compatible_pointer_slots("weapon_1h")) == {"weapon_1", "weapon_2"}
    assert set(compatible_pointer_slots("weapon_2h")) == {"weapon_1", "weapon_2"}
    assert compatible_pointer_slots("armor_head") == ("armor_head",)
    assert set(compatible_pointer_slots("accessory")) == {"accessory_1", "accessory_2"}
    assert compatible_pointer_slots("fubao") == ("fubao",)
    assert compatible_pointer_slots("pet") == ("pet",)
    assert compatible_pointer_slots("unknown_kind") == ()


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


async def _prepare(session: AsyncSession, email: str, name: str) -> tuple[User, str]:
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name, gender="male"),
    )
    await session.commit()
    character = await character_service.get_character_by_user_id(session, user.id)
    assert character is not None
    inv = InventoryService(session)
    await inv.add_item(
        character.id,
        item_type="equipment",
        item_id="iron_sword_t1",
        quantity=1,
    )
    await session.commit()
    rows = await inv.list_items(character.id)
    sword = next(r for r in rows if r["item_id"] == "iron_sword_t1")
    return user, str(sword["item_uid"])


def test_equipment_config_and_channels_enabled() -> None:
    cfg = get_game_config()
    assert "iron_sword_t1" in cfg.equipment.items
    assert cfg.combat_attrs.channels["equipment"]["enabled"] is True
    assert cfg.idle.bonus_channels["equipment_idle"].enabled is True
    assert cfg.dice.bonus_channels["equipment"].enabled is True


def test_equipment_attr_feed(tmp_path: Path) -> None:
    """Wear weapon → phys_atk breakdown includes equipment source."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "eq1.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                _, item_uid = await _prepare(session, "eq1@test.com", "装备甲")
                user = (
                    await session.execute(select(User).where(User.email == "eq1@test.com"))
                ).scalar_one()
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                bag_state = await EquipmentService(session).get_slots_state(char)
                sword_bag = next(
                    i for i in bag_state["bag_equipment"] if i["item_id"] == "iron_sword_t1"
                )
                assert "weapon_1" in sword_bag["compatible_slots"]
                assert "weapon_2" in sword_bag["compatible_slots"]
                assert sword_bag.get("rarity") == "white"
                assert sword_bag.get("rarity_label_zh") == "普通"
                assert sword_bag.get("icon") == "iron_sword_t1"
                await EquipmentService(session).equip_item(
                    char,
                    slot="weapon_1",
                    item_uid=item_uid,
                )
                await session.commit()
                packed = await CharacterService(session).build_combat_attrs(char)
                breakdown = packed["combat"]["breakdown"]
                eq_row = next((r for r in breakdown if r.get("source") == "equipment"), None)
                assert eq_row is not None
                assert eq_row.get("label_zh") == "装备"
                assert float(eq_row.get("phys_atk") or 0) >= 3.0
                assert int(packed["combat"]["final"]["phys_atk"]) >= 3
                worn = await EquipmentService(session).get_slots_state(char)
                w1 = next(s for s in worn["slots"] if s["slot"] == "weapon_1")
                assert w1.get("rarity") == "white"
                assert w1.get("rarity_label_zh") == "普通"
                assert w1.get("icon") == "iron_sword_t1"

    _run(_body())


def test_equipment_slot_rarity_from_craft_quality(tmp_path: Path) -> None:
    """Craft meta quality surfaces as rarity + Chinese label for UI (§0.0.3)."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "eq_rarity.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                from app.db.models.inventory_item import InventoryItem

                _, item_uid = await _prepare(session, "eqr@test.com", "品质甲")
                user = (
                    await session.execute(select(User).where(User.email == "eqr@test.com"))
                ).scalar_one()
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                row = (
                    await session.execute(
                        select(InventoryItem).where(InventoryItem.item_uid == item_uid),
                    )
                ).scalar_one()
                row.meta_json = '{"quality": "superb"}'
                await session.commit()
                state = await EquipmentService(session).get_slots_state(char)
                bag = next(i for i in state["bag_equipment"] if i["item_uid"] == item_uid)
                assert bag["rarity"] == "purple"
                assert bag["rarity_label_zh"] == "史诗"
                await EquipmentService(session).equip_item(
                    char,
                    slot="weapon_1",
                    item_uid=item_uid,
                )
                await session.commit()
                worn = await EquipmentService(session).get_slots_state(char)
                w1 = next(s for s in worn["slots"] if s["slot"] == "weapon_1")
                assert w1["rarity"] == "purple"
                assert w1["rarity_label_zh"] == "史诗"

                row.meta_json = '{"quality": "orange"}'
                await session.commit()
                worn2 = await EquipmentService(session).get_slots_state(char)
                w1b = next(s for s in worn2["slots"] if s["slot"] == "weapon_1")
                assert w1b["rarity"] == "orange"
                assert w1b["rarity_label_zh"] == "传说"

    _run(_body())


def test_equipment_channel_disabled_additive() -> None:
    """Disabled equipment AdditiveSource does not change final stats."""
    from app.domain.combat import AdditiveSource, CombatAttrAssembleInput, assemble_combat_attr_block

    cfg = get_game_config().combat_attrs
    labels = {k: a.label_zh for k, a in cfg.attrs.items()}
    attr_categories = {k: a.category for k, a in cfg.attrs.items()}
    defaults = dict(cfg.defaults)
    base = assemble_combat_attr_block(
        CombatAttrAssembleInput(
            realm_phys_atk=10,
            realm_hp=100,
            realm_speed=10,
            rein_mult=1.0,
            grade_atk_mul=1.0,
            grade_hp_mul=1.0,
            additive_sources=(
                AdditiveSource(
                    source_id="equipment",
                    label_zh="装备",
                    amounts={"phys_atk": 5.0},
                    enabled=False,
                    note_zh="装备属性通道未启用",
                ),
            ),
            primary={},
            primary_map=dict(cfg.primary_map),
            defaults=defaults,
            labels=labels,
            aliases=dict(cfg.aliases),
            channels=dict(cfg.channels),
            schema_version=cfg.schema_version,
            entity_kind="player",
            allowed_categories=tuple(cfg.entity_profiles.get("player") or ()),
            attr_categories=attr_categories,
            growth={},
        ),
    )
    assert int(base["final"]["phys_atk"]) == 10


def test_equipment_idle_dice_channels(tmp_path: Path) -> None:
    """Idle and dice breakdown include equipment after wear."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "eq3.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                _, item_uid = await _prepare(session, "eq3@test.com", "装备丙")
                user = (await session.execute(select(User).where(User.email == "eq3@test.com"))).scalar_one()
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                await EquipmentService(session).equip_item(
                    char,
                    slot="weapon_1",
                    item_uid=item_uid,
                )
                await session.commit()

                _, idle_items = await resolve_idle_bonus_channels(session, char)
                idle_eq = [i for i in idle_items if i.source == "equipment"]
                assert idle_eq
                assert idle_eq[0].mult > 1.0

                bounds = await DiceService(session).resolve_for_character(
                    char,
                    purpose="breakthrough",
                )
                dice_eq = [b for b in bounds.breakdown if b.source == "equipment"]
                assert dice_eq

    _run(_body())


def test_puppet_channel(tmp_path: Path) -> None:
    """Puppet meta combat_stats feed puppet breakdown on puppet preview."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "puppet.db") as factory:
            async with factory() as session:
                combat = await CharacterService(session).build_puppet_combat_preview(
                    base_phys_atk=10,
                    base_hp=50,
                    base_speed=8,
                    actor_meta_json='{"combat_stats": {"phys_atk": 4}}',
                )
                row = next((r for r in combat["breakdown"] if r.get("source") == "puppet"), None)
                assert row is not None
                assert float(row.get("phys_atk") or 0) == 4.0
                assert int(combat["final"]["phys_atk"]) >= 14

    _run(_body())


def test_weapon_2h_dual_pointer_and_aggregate(tmp_path: Path) -> None:
    """Two-handed weapon writes both hands; stats counted once; unequip clears both."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "eq2h.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="eq2h@test.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "eq2h@test.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="双手甲", gender="male"),
                )
                await session.commit()
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="equipment",
                    item_id="iron_sword_t1",
                    quantity=1,
                )
                await inv.add_item(
                    char.id,
                    item_type="equipment",
                    item_id="iron_greatsword_t1",
                    quantity=1,
                )
                await session.commit()
                rows = await inv.list_items(char.id)
                sword = next(r for r in rows if r["item_id"] == "iron_sword_t1")
                great = next(r for r in rows if r["item_id"] == "iron_greatsword_t1")
                eq = EquipmentService(session)
                await eq.equip_item(char, slot="weapon_1", item_uid=str(sword["item_uid"]))
                await eq.equip_item(char, slot="weapon_2", item_uid=str(great["item_uid"]))
                await session.commit()
                state = await eq.get_slots_state(char)
                by_slot = {s["slot"]: s for s in state["slots"]}
                assert by_slot["weapon_1"]["item_uid"] == great["item_uid"]
                assert by_slot["weapon_2"]["item_uid"] == great["item_uid"]
                stats, _, _, _ = await eq.aggregate_equipped_modifiers(char.id)
                assert float(stats.get("phys_atk") or 0) == 6.0
                await eq.unequip_slot(char, slot="weapon_2")
                await session.commit()
                state2 = await eq.get_slots_state(char)
                by2 = {s["slot"]: s for s in state2["slots"]}
                assert by2["weapon_1"]["item_uid"] is None
                assert by2["weapon_2"]["item_uid"] is None

    _run(_body())


def test_puppet_loadout_and_bench_filter(tmp_path: Path) -> None:
    """Puppet loadout toggles occupancy; bench only lists deployed puppets."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pload.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                from app.services.formation_service import FormationService

                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="pload@test.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "pload@test.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="编成甲", gender="male"),
                )
                await session.commit()
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="puppet",
                    item_id="puppet_wood_v1",
                    quantity=1,
                )
                await session.commit()
                rows = await inv.list_items(char.id)
                puppet = next(r for r in rows if r["item_id"] == "puppet_wood_v1")
                uid = str(puppet["item_uid"])
                eq = EquipmentService(session)
                state = await eq.add_puppet_to_loadout(char, item_uid=uid)
                assert any(p["item_uid"] == uid for p in state["puppet_loadout"])
                assert not any(p["item_uid"] == uid for p in state["bag_puppets"])
                await session.commit()
                bench = await FormationService(session).bench_units(char)
                puppet_bench = [b for b in bench if b.get("unit_kind") == "puppet" and b.get("unit_uid") == uid]
                assert len(puppet_bench) == 1
                state2 = await eq.remove_puppet_from_loadout(char, item_uid=uid)
                assert not any(p["item_uid"] == uid for p in state2["puppet_loadout"])
                assert any(p["item_uid"] == uid for p in state2["bag_puppets"])
                await session.commit()
                bench2 = await FormationService(session).bench_units(char)
                assert not any(
                    b.get("unit_uid") == uid for b in bench2 if b.get("unit_kind") == "puppet"
                )

    _run(_body())


def test_replace_puppet_loadout_and_sense_payload(tmp_path: Path) -> None:
    """PUT-style replace writes occupancy; slots DTO carries puppet sense preview."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "psense.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="psense@test.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "psense@test.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="神识傀", gender="male"),
                )
                await session.commit()
                char = await character_service.get_character_by_user_id(session, user.id)
                assert char is not None
                inv = InventoryService(session)
                await inv.add_item(
                    char.id,
                    item_type="puppet",
                    item_id="puppet_wood_v1",
                    quantity=1,
                )
                await session.commit()
                rows = await inv.list_items(char.id)
                puppet = next(r for r in rows if r["item_id"] == "puppet_wood_v1")
                uid = str(puppet["item_uid"])
                eq = EquipmentService(session)
                from app.constants.divine_sense import (
                    PUPPET_LOADOUT_MAX,
                    PUPPET_LOADOUT_MAX_ZH,
                    PUPPET_SENSE_HELP_ZH,
                )
                from app.schemas.common import AppError
                from app.services.divine_sense_service import DivineSenseService

                empty = await eq.get_slots_state(char)
                pool = DivineSenseService.snapshot_for_character(char)
                assert empty["puppet_sense"]["capacity"] == pool["capacity"]
                assert empty["puppet_sense"]["capacity"] > 0
                assert empty["puppet_sense"]["default_cost"] == 2
                assert empty["puppet_sense"]["percent"] == 100
                assert empty["puppet_sense"]["load"] == 0
                assert empty["puppet_sense"]["help_zh"] == PUPPET_SENSE_HELP_ZH
                assert empty["puppet_sense"]["max_count"] == PUPPET_LOADOUT_MAX
                assert empty["puppet_sense"]["bands"]
                bag = next(p for p in empty["bag_puppets"] if p["item_uid"] == uid)
                assert bag["divine_sense_cost"] == 2
                assert bag["counts_toward_load"] is True

                filled = await eq.replace_puppet_loadout(char, item_uids=[uid])
                assert any(p["item_uid"] == uid for p in filled["puppet_loadout"])
                assert filled["puppet_sense"]["load"] == 2
                assert filled["puppet_sense"]["percent"] == 100
                await session.commit()

                from app.services.avatar_service import AvatarService

                panel_sense = await AvatarService(session).get_sense(char)
                assert panel_sense["load"] == 2
                assert panel_sense["capacity"] == filled["puppet_sense"]["capacity"]

                for _ in range(3):
                    await inv.add_item(
                        char.id,
                        item_type="puppet",
                        item_id="puppet_wood_v1",
                        quantity=1,
                    )
                await session.commit()
                all_rows = await inv.list_items(char.id)
                puppet_uids = [
                    str(r["item_uid"]) for r in all_rows if r["item_id"] == "puppet_wood_v1"
                ]
                assert len(puppet_uids) >= 4
                with pytest.raises(AppError) as rejected:
                    await eq.replace_puppet_loadout(char, item_uids=puppet_uids[:4])
                assert rejected.value.message == PUPPET_LOADOUT_MAX_ZH
                capped = await eq.replace_puppet_loadout(char, item_uids=puppet_uids[:3])
                assert len(capped["puppet_loadout"]) == 3
                await session.commit()

                cleared = await eq.replace_puppet_loadout(char, item_uids=[])
                assert not cleared["puppet_loadout"]
                assert cleared["puppet_sense"]["load"] == 0
                await session.commit()

    _run(_body())
