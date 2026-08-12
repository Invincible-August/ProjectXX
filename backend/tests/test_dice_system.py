"""修为骰子系统单测：查表、修正、突破阈值、钳制。"""

from __future__ import annotations

import random

from app.domain.dice_rules import (
    DiceModContribution,
    breakthrough_success,
    breakthrough_threshold,
    clamp_bounds,
    lookup_realm_bounds,
    resolve_bounds,
    roll_int,
    technique_mod_for_level,
)
from app.services.realm_config import clear_game_config_cache, get_game_config


def setup_function() -> None:
    clear_game_config_cache()


def teardown_function() -> None:
    clear_game_config_cache()


def test_realm_bounds_differ_by_stage() -> None:
    """锻体 1 / 10 / 炼气 1 基础区间不同且与 YAML 一致。"""
    dice = get_game_config().dice
    b1 = lookup_realm_bounds(
        dice.realm_bounds,
        major_realm="body_tempering",
        stage=1,
        fallback_min=dice.fallback_min,
        fallback_max=dice.fallback_max,
    )
    b10 = lookup_realm_bounds(
        dice.realm_bounds,
        major_realm="body_tempering",
        stage=10,
        fallback_min=dice.fallback_min,
        fallback_max=dice.fallback_max,
    )
    q1 = lookup_realm_bounds(
        dice.realm_bounds,
        major_realm="qi_refining",
        stage=1,
        fallback_min=dice.fallback_min,
        fallback_max=dice.fallback_max,
    )
    assert b1 == (1, 10)
    assert b10 == (10, 10)
    assert q1 == (11, 20)
    assert b1[0] < b10[0]
    assert q1[0] > b10[1]


def test_technique_mod_raises_bounds() -> None:
    """功法 dice_mods 抬高实际上下限。"""
    dice = get_game_config().dice
    tech = get_game_config().techniques["basic_qi_art"]
    min_b, max_b = technique_mod_for_level(tech.dice_mods, 10)
    assert max_b >= 1
    base = resolve_bounds(
        purpose="generic",
        base_min=1,
        base_max=10,
        contributions=(),
        absolute_min=dice.absolute_min,
        absolute_max=dice.absolute_max,
    )
    boosted = resolve_bounds(
        purpose="generic",
        base_min=1,
        base_max=10,
        contributions=[
            DiceModContribution(
                source="technique",
                id="basic_qi_art",
                label="基础吐纳诀",
                min_bonus=min_b,
                max_bonus=max_b,
            ),
        ],
        absolute_min=dice.absolute_min,
        absolute_max=dice.absolute_max,
    )
    assert boosted.hi >= base.hi
    assert boosted.lo >= base.lo


def test_clamp_swaps_when_lo_gt_hi() -> None:
    """负修正导致 lo>hi 时钳制交换。"""
    lo, hi = clamp_bounds(15, 5, absolute_min=1, absolute_max=200)
    assert lo <= hi


def test_roll_int_respects_range() -> None:
    """出目落在闭区间内。"""
    rng = random.Random(42)
    for _ in range(50):
        v = roll_int(3, 7, rng=rng)
        assert 3 <= v <= 7


def test_breakthrough_threshold_maps_success_rate() -> None:
    """success_rate≈1 时阈值≈lo；≈0 时阈值≈hi。"""
    assert breakthrough_threshold(1, 10, 1.0) == 1
    assert breakthrough_threshold(1, 10, 0.0) == 10
    ok, th = breakthrough_success(10, 1, 10, 0.1)
    assert th >= 9
    assert ok is True
    ok2, _ = breakthrough_success(1, 1, 10, 0.1)
    assert ok2 is False


def test_dice_config_loaded() -> None:
    """dice.yaml 已解析进 GameConfigBundle。"""
    dice = get_game_config().dice
    assert "body_tempering" in dice.realm_bounds
    assert dice.channel_enabled("technique") is True
    assert dice.channel_enabled("equipment") is False
