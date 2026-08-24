"""符箓叠层与异常状态回合纯函数。"""

from __future__ import annotations

import random

from app.domain.status_effects import (
    CleanseTechnique,
    StatusInstance,
    offensive_talisman_allowed,
    resolve_status_turn,
    roll_offensive_talisman,
    wake_on_hit,
)
from app.domain.talisman_stack import (
    TalismanLayer,
    active_layers_for_group,
    current_magnitude,
    parse_talisman_layer,
    resolve_stack_groups,
)


def _layer(**kwargs) -> TalismanLayer:
    base = dict(
        inventory_item_id=1,
        effect_id="x",
        stack_group="atk_pct",
        magnitude=0.15,
        duration_kind="global",
        duration=0,
        attr="phys_atk",
        trigger="battle_start",
        label_zh="测",
        use_chance=0.0,
        hit_chance=1.0,
        kind="buff",
    )
    base.update(kwargs)
    return TalismanLayer(**base)


def test_same_group_picks_highest_and_keeps_fallback() -> None:
    rows = [
        _layer(inventory_item_id=1, magnitude=0.15, duration_kind="global"),
        _layer(inventory_item_id=2, magnitude=0.30, duration_kind="attacks", duration=3),
    ]
    grouped = resolve_stack_groups(rows)
    active = active_layers_for_group(grouped["atk_pct"])
    assert current_magnitude(active, attacks_used=0) == 0.30
    assert current_magnitude(active, attacks_used=3) == 0.15
    ids = {row.inventory_item_id for row in grouped["atk_pct"]}
    assert ids == {1, 2}


def test_global_not_lowered_by_weaker_rounds() -> None:
    rows = [
        _layer(inventory_item_id=1, magnitude=0.15, duration_kind="global"),
        _layer(inventory_item_id=2, magnitude=0.10, duration_kind="rounds", duration=3),
    ]
    active = active_layers_for_group(resolve_stack_groups(rows)["atk_pct"])
    assert current_magnitude(active, rounds_elapsed=0) == 0.15
    assert current_magnitude(active, rounds_elapsed=2) == 0.15


def test_parse_layer_from_effect_def() -> None:
    layer = parse_talisman_layer(
        {"inventory_item_id": 9, "effect_id": "atk_pct_global_30", "label_zh": "锐"},
        {
            "stack_group": "atk_pct",
            "magnitude": 0.3,
            "duration_kind": "global",
            "trigger": "battle_start",
            "kind": "buff",
        },
    )
    assert layer.stack_group == "atk_pct"
    assert layer.magnitude == 0.3


def test_coma_blocks_and_does_not_wake_on_hit() -> None:
    result = resolve_status_turn(
        StatusInstance(status_id="coma", remaining_rounds=2, wake_chance=0),
        rng=random.Random(0),
    )
    assert result.can_act is False
    assert result.max_ap_this_turn == 0
    assert wake_on_hit("coma") is False
    assert wake_on_hit("sleep") is True
    assert wake_on_hit("charm") is True


def test_cleanse_consumes_one_ap() -> None:
    rng = random.Random(0)

    class Always:
        def random(self) -> float:
            return 0.0

    result = resolve_status_turn(
        StatusInstance(status_id="poison", remaining_rounds=3, tick_damage=2),
        cleanse=CleanseTechnique(equipped=True, cast_chance=1.0, success_chance=1.0),
        rng=Always(),
    )
    assert result.cleansed is True
    assert result.consumed_ap == 1
    assert result.apply_tick is False


def test_sleep_wake_spends_all_ap() -> None:
    class Always:
        def random(self) -> float:
            return 0.0

    result = resolve_status_turn(
        StatusInstance(status_id="sleep", remaining_rounds=3, wake_chance=1.0),
        rng=Always(),
    )
    assert result.woke is True
    assert result.consumed_ap == -1
    assert result.prefer_not_attacked is False


def test_offensive_talisman_skips_move_and_obstacle() -> None:
    assert offensive_talisman_allowed(is_move=True, target_is_obstacle=False) is False
    assert offensive_talisman_allowed(is_move=False, target_is_obstacle=True) is False
    assert offensive_talisman_allowed(is_move=False, target_is_obstacle=False) is True
    used, hit = roll_offensive_talisman(use_chance=0.0, hit_chance=1.0, rng=random.Random(1))
    assert used is False
    assert hit is False


def test_ailment_and_curse_taxonomy() -> None:
    from app.constants.status import (
        STATUS_AILMENT,
        STATUS_ATK_DOWN,
        STATUS_CURSE,
        STATUS_DEF_DOWN,
        STATUS_DROWN,
        STATUS_PARALYZE,
        STATUS_POISON,
    )

    assert STATUS_POISON in STATUS_AILMENT
    assert STATUS_DROWN in STATUS_AILMENT
    assert STATUS_PARALYZE in STATUS_AILMENT
    assert STATUS_ATK_DOWN in STATUS_CURSE
    assert STATUS_DEF_DOWN in STATUS_CURSE
    assert STATUS_ATK_DOWN not in STATUS_AILMENT
    assert STATUS_POISON not in STATUS_CURSE
