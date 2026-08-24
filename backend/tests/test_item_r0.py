"""
M8 R0 item factory / four laws / elixir duration schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.constants.equipment import (
    EQUIPMENT_POINTER_SLOTS,
    EQUIPMENT_SLOT_PET,
    canonical_equipment_slot,
)
from app.constants.inventory import (
    ERR_ITEM_OCCUPIED,
    ERR_ITEM_USE_EFFECT,
    BagTab,
    Occupancy,
    bag_tab_for,
)
from app.game.item import (
    ConsumableItem,
    EquipmentItem,
    MaterialItem,
    PetEggItem,
    PetItem,
    PuppetItem,
    item_from_mapping,
)
from app.game.item.laws import can_stack_with, can_trade
from app.game.item.use_effect import UseEffectError, validate_use_effect
from app.schemas.common import AppError
from tests.async_db import open_test_session_factory, run_async as _run


def test_bag_tab_mapping() -> None:
    """item_type maps onto the four bag tabs."""
    assert bag_tab_for("equipment") == BagTab.GEAR
    assert bag_tab_for("puppet") == BagTab.GEAR
    assert bag_tab_for("pet") == BagTab.GEAR
    assert bag_tab_for("pet_egg") == BagTab.GEAR
    assert bag_tab_for("consumable") == BagTab.ELIXIR
    assert bag_tab_for("talisman") == BagTab.ELIXIR
    assert bag_tab_for("material") == BagTab.MATERIAL
    assert bag_tab_for("manual") == BagTab.MANUAL
    assert bag_tab_for("skill_book") == BagTab.MANUAL


def test_factory_dispatches_subclasses() -> None:
    """Factory picks a concrete Item subclass from item_type."""
    assert isinstance(item_from_mapping("ore_iron_raw", {"item_type": "material"}), MaterialItem)
    assert isinstance(
        item_from_mapping("stamina_pill_minor", {"item_type": "consumable"}),
        ConsumableItem,
    )
    assert isinstance(item_from_mapping("iron_sword_t1", {"item_type": "equipment"}), EquipmentItem)
    assert isinstance(item_from_mapping("puppet_wood_v1", {"item_type": "puppet"}), PuppetItem)
    assert isinstance(item_from_mapping("egg_fox_trial", {"item_type": "pet_egg"}), PetEggItem)
    assert isinstance(item_from_mapping("pet_fox_1", {"item_type": "pet"}), PetItem)


def test_four_laws_bound_blocks_trade() -> None:
    """Bound or occupied rows cannot trade."""
    bound = item_from_mapping(
        "bound_spirit_token",
        {"item_type": "consumable", "bound": True, "tradable": False},
    )
    assert bound.get_stack_rules()["bound"] is True
    assert can_trade(bound) is False

    idle = item_from_mapping(
        "stamina_pill_minor",
        {"item_type": "consumable", "bound": False, "tradable": True},
        occupancy=Occupancy.NONE,
    )
    assert can_trade(idle) is True

    worn = item_from_mapping(
        "iron_sword_t1",
        {"item_type": "equipment", "tradable": True, "bound": False},
        occupancy=Occupancy.EQUIPPED,
    )
    assert can_trade(worn) is False


def test_occupied_items_cannot_stack() -> None:
    """Occupied rows do not stack with idle copies."""
    a = item_from_mapping(
        "stamina_pill_minor",
        {"item_type": "consumable", "max_stack": 99},
        occupancy=Occupancy.NONE,
        quantity=1,
    )
    b = item_from_mapping(
        "stamina_pill_minor",
        {"item_type": "consumable", "max_stack": 99},
        occupancy=Occupancy.NONE,
        quantity=1,
    )
    busy = item_from_mapping(
        "stamina_pill_minor",
        {"item_type": "consumable", "max_stack": 99},
        occupancy=Occupancy.DEPLOYED,
        quantity=1,
    )
    assert can_stack_with(a, b) is True
    assert can_stack_with(a, busy) is False


def test_pointer_slots_include_pet_not_puppet() -> None:
    """Pet is a single pointer slot; puppet is a loadout board, not a slot."""
    from app.constants.equipment import EQUIPMENT_SLOTS

    assert EQUIPMENT_SLOT_PET in EQUIPMENT_POINTER_SLOTS
    assert EQUIPMENT_SLOT_PET in EQUIPMENT_SLOTS
    assert "puppet" not in EQUIPMENT_POINTER_SLOTS
    assert "weapon" not in EQUIPMENT_SLOTS
    assert "weapon_1" in EQUIPMENT_SLOTS
    assert canonical_equipment_slot("weapon") == "weapon_1"
    assert canonical_equipment_slot("armor") == "armor_chest"
    assert canonical_equipment_slot("fabao") == "fabao_1"


def test_use_effect_stamina_ok() -> None:
    """Instant stamina kind is on the whitelist."""
    parsed = validate_use_effect({"kind": "stamina", "amount": 20})
    assert parsed[0]["kind"] == "stamina"
    assert parsed[0]["instant"] is True


def test_use_effect_unknown_kind_rejected() -> None:
    """Unknown kind is rejected before consume."""
    with pytest.raises(UseEffectError):
        validate_use_effect({"kind": "not_a_real_kind", "amount": 1})


def test_use_effect_bare_duration_rejected() -> None:
    """A unit-less duration integer is forbidden."""
    with pytest.raises(UseEffectError):
        validate_use_effect({"kind": "attr_mod", "stats": {"phys_atk": 1}, "duration": 30})


def test_use_effect_multi_track_clocks_ok() -> None:
    """wall / battle / round clocks are accepted."""
    parsed = validate_use_effect(
        {
            "kind": "attr_mod",
            "stats": {"phys_atk": 8},
            "duration": {
                "expire": "any",
                "tracks": [
                    {"clock": "battle", "count": 3},
                    {"clock": "wall", "seconds": 3600},
                ],
            },
        },
    )
    assert parsed[0]["instant"] is False
    clocks = {t["clock"] for t in parsed[0]["tracks"]}
    assert clocks == {"battle", "wall"}

    round_fx = validate_use_effect(
        {
            "kind": "attr_mod",
            "stats": {"phys_atk": 2},
            "duration": {"clock": "round", "count": 5},
        },
    )
    assert round_fx[0]["tracks"][0]["clock"] == "round"


def test_consumable_on_use_occupied_raises() -> None:
    """Occupied consumables cannot be used."""
    pill = item_from_mapping(
        "stamina_pill_minor",
        {"item_type": "consumable", "use_effect": {"kind": "stamina", "amount": 20}},
        occupancy=Occupancy.EQUIPPED,
    )
    with pytest.raises(AppError) as exc:
        pill.on_use({"quantity": 1})
    assert exc.value.code == ERR_ITEM_OCCUPIED


def test_consumable_unknown_kind_does_not_claim_success() -> None:
    """Unknown kind surfaces the use-effect error code."""
    pill = item_from_mapping(
        "mystery_pill",
        {"item_type": "consumable", "use_effect": {"kind": "explode_server"}},
        occupancy=Occupancy.NONE,
    )
    with pytest.raises(AppError) as exc:
        pill.on_use({"quantity": 1})
    assert exc.value.code == ERR_ITEM_USE_EFFECT


def test_inventory_list_bag_tab_and_occupancy(tmp_path: Path) -> None:
    """GET-style list_items exposes bag_tab; worn gear is occupied not hidden."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "item_r0.db") as factory:
            async with factory() as session:
                from sqlalchemy import select

                from app.core.config import get_settings
                from app.db.models import User
                from app.schemas.auth import RegisterRequest
                from app.schemas.character import CreateCharacterRequest
                from app.services import auth_service, character_service
                from app.services.equipment_service import EquipmentService
                from app.services.inventory_service import InventoryService
                from app.services.realm_config import clear_game_config_cache

                settings = get_settings()
                settings.debug = True
                settings.register_require_phone = False
                settings.register_require_real_name = False
                settings.register_require_email_code = False
                settings.app_env = "development"
                clear_game_config_cache()

                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="r0bag@test.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "r0bag@test.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="R0甲", gender="male"),
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
                await inv.add_item(
                    character.id,
                    item_type="consumable",
                    item_id="stamina_pill_minor",
                    quantity=2,
                )
                await session.commit()
                rows = await inv.list_items(character.id)
                pill = next(r for r in rows if r["item_id"] == "stamina_pill_minor")
                sword = next(r for r in rows if r["item_id"] == "iron_sword_t1")
                assert pill["bag_tab"] == "elixir"
                assert sword["bag_tab"] == "gear"
                assert sword["occupancy"] == "none"
                await EquipmentService(session).equip_item(
                    character,
                    slot="weapon_1",
                    item_uid=str(sword["item_uid"]),
                )
                await session.commit()
                rows = await inv.list_items(character.id)
                sword = next(r for r in rows if r["item_id"] == "iron_sword_t1")
                assert sword["occupancy"] == "equipped"
                assert sword["occupancy_label_zh"] == "已装备"
                used = await inv.use_item(
                    character,
                    item_uid=str(pill["item_uid"]),
                    quantity=1,
                )
                assert used["stamina_gained"] == 20

    _run(_body())
