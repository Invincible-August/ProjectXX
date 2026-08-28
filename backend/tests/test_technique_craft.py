"""
功法自研 P1：协议常量、YAML 解析与灵根→元素映射。
"""

from __future__ import annotations

from app.constants.technique_craft import element_ids_from_spirit_root_tags
from app.services.realm_config import clear_game_config_cache, get_game_config


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
