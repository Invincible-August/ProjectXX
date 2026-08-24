"""
M8 R6 / AB1: official sample-table validator rejects bad ATTR keys.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config_source.validate_content import (
    ContentValidationError,
    assert_attr_stats,
    validate_constitution_tables,
    validate_startup,
    validate_talisman_effects_raw,
)
from app.constants.combat_attrs import CONSTITUTION_LEGACY_EFFECT_KEYS
from app.schemas.common import AppError
from app.services.admin_config_service import AdminConfigService
from app.services.realm_config import clear_game_config_cache, get_game_config


@pytest.fixture(autouse=True)
def _cfg() -> None:
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_current_yaml_samples_pass_validator() -> None:
    """Boot path and CLI share get_game_config; official tables must load."""
    bundle = validate_startup()
    assert "iron_sword_t1" in bundle.equipment.items
    assert "first_hit_ward" in bundle.talisman_effects
    assert "phys_edge" in bundle.research.affixes
    assert "sample_main_affix_iron" in bundle.constitution.items


def test_assert_attr_stats_rejects_unknown_key() -> None:
    with pytest.raises(ContentValidationError, match="unknown combat attr key"):
        assert_attr_stats("equipment.bad.stats", {"not_a_real_attr": 1}, {"phys_atk"})


def test_talisman_effects_require_label_and_trigger() -> None:
    with pytest.raises(ContentValidationError, match="缺少 label_zh"):
        validate_talisman_effects_raw({"ghost": {"trigger": "first_hit"}})
    with pytest.raises(ContentValidationError, match="trigger"):
        validate_talisman_effects_raw(
            {"ghost": {"label_zh": "鬼符", "trigger": "invented_trigger"}},
        )
    validate_talisman_effects_raw(
        {"first_hit_ward": {"label_zh": "护体残符", "trigger": "first_hit"}},
    )


def test_constitution_rejects_invented_effect_key() -> None:
    item = MagicMock()
    item.base_attrs = {"vitality": 1}
    item.effects = {"totally_fake_attr": 9}
    constitution = MagicMock()
    constitution.items = {"bad_word": item}
    with pytest.raises(ContentValidationError, match="unknown combat attr key"):
        validate_constitution_tables(constitution, attr_keys={"phys_atk", "hp"})
    item.effects = {"hp_bonus": 20}
    assert "hp_bonus" in CONSTITUTION_LEGACY_EFFECT_KEYS
    validate_constitution_tables(constitution, attr_keys={"phys_atk", "hp"})


def test_parse_equipment_rejects_unknown_stats() -> None:
    from app.services.realm_config import _parse_equipment

    cfg = get_game_config()
    with pytest.raises(ValueError, match="unknown combat attr key"):
        _parse_equipment(
            {
                "items": {
                    "bad_sword": {
                        "label_zh": "坏剑",
                        "slot": "weapon_1h",
                        "stats": {"not_a_real_attr": 3},
                    },
                },
            },
            combat_attrs=cfg.combat_attrs,
        )


def test_admin_probe_rejects_bad_equipment_and_talisman() -> None:
    """Publish path uses the same parser probe; bad overlay must not publish."""
    svc = AdminConfigService(MagicMock())
    with pytest.raises(AppError) as eq_exc:
        svc.validate_overlay(
            "equipment",
            {
                "items": {
                    "probe_bad_sword": {
                        "label_zh": "探测坏剑",
                        "help_zh": "校验器应拒绝",
                        "slot": "weapon_1h",
                        "stats": {"not_a_real_attr": 1},
                    },
                },
            },
        )
    assert eq_exc.value.code == 40050
    with pytest.raises(AppError) as fx_exc:
        svc.validate_overlay(
            "talisman_effects",
            {"probe_ghost": {"help_zh": "无中文名", "trigger": "first_hit"}},
        )
    assert fx_exc.value.code == 40050
    ok = svc.validate_overlay("talisman_effects", {})
    assert ok["ok"] is True
