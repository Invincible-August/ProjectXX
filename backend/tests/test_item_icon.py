"""Item icon key resolution (§0.0.4)."""

from __future__ import annotations

from app.domain.item_icon import resolve_item_icon
from app.game.item.factory import item_from_mapping
from app.services.realm_config import clear_game_config_cache, get_game_config


def test_resolve_item_icon_defaults_to_def_id() -> None:
    assert resolve_item_icon(None, "iron_sword_t1") == "iron_sword_t1"
    assert resolve_item_icon("", "herb_spirit_grass") == "herb_spirit_grass"
    assert resolve_item_icon("custom_sword", "iron_sword_t1") == "custom_sword"


def test_inventory_and_equipment_defs_have_icon() -> None:
    clear_game_config_cache()
    cfg = get_game_config()
    inv = cfg.inventory.items["iron_sword_t1"]
    eq = cfg.equipment.items["iron_sword_t1"]
    assert inv.icon == "iron_sword_t1"
    assert eq.icon == "iron_sword_t1"
    tech = next(iter(cfg.techniques.values()))
    assert tech.icon == tech.technique_id


def test_item_factory_exposes_get_icon() -> None:
    item = item_from_mapping(
        "iron_sword_t1",
        {"item_type": "equipment", "name": "玄铁剑", "icon": "iron_sword_t1"},
    )
    assert item.get_icon() == "iron_sword_t1"
