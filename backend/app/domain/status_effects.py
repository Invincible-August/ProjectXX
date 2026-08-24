"""异常状态回合流程纯函数（设计冻结；完整功法链仍挂 M3-D03）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.constants.status import (
    STATUS_CC,
    STATUS_CHARM,
    STATUS_COMA,
    STATUS_DOT,
    STATUS_SLEEP,
    STATUS_STAT_MOD,
    STATUS_STUN,
    STATUS_WAKE_ON_HIT,
)


@dataclass(frozen=True)
class StatusInstance:
    """单位身上一条异常。"""

    status_id: str
    remaining_rounds: int
    tick_damage: int = 0
    stat_mult: float = 1.0
    wake_chance: float = 0.0


@dataclass(frozen=True)
class CleanseTechnique:
    """装备的「解除异常」功法。"""

    equipped: bool
    cast_chance: float
    success_chance: float


@dataclass(frozen=True)
class StatusTurnResult:
    """行动回合开始时对单条异常的结算。"""

    expired: bool
    cleansed: bool
    consumed_ap: int  # 0、1，或 -1 表示耗尽本回合全部行动
    apply_tick: bool
    woke: bool
    remaining_rounds: int
    can_act: bool
    max_ap_this_turn: int | None  # None=不改；眩晕=1
    charm_attack_allies: bool
    allies_cannot_target: bool
    taunt_aura_disabled: bool
    prefer_not_attacked: bool  # 睡眠：敌方不优先打


def resolve_status_turn(
    instance: StatusInstance,
    *,
    cleanse: CleanseTechnique | None = None,
    rng: Any = None,
) -> StatusTurnResult:
    """
    行动回合开始：先判断是否到期；未到期再判解除功法；否则结算异常效果。

    解除成功消耗一次行动机会；未触发功法则不消耗 AP，但结算异常效果。
    昏迷/眩晕/睡眠/魅惑苏醒则解除并耗尽本回合全部行动机会。
    """
    remaining = int(instance.remaining_rounds)
    if remaining <= 0:
        return StatusTurnResult(
            expired=True,
            cleansed=False,
            consumed_ap=0,
            apply_tick=False,
            woke=False,
            remaining_rounds=0,
            can_act=True,
            max_ap_this_turn=None,
            charm_attack_allies=False,
            allies_cannot_target=False,
            taunt_aura_disabled=False,
            prefer_not_attacked=False,
        )

    if cleanse is not None and cleanse.equipped:
        if _chance(cleanse.cast_chance, rng=rng) and _chance(cleanse.success_chance, rng=rng):
            return StatusTurnResult(
                expired=False,
                cleansed=True,
                consumed_ap=1,
                apply_tick=False,
                woke=False,
                remaining_rounds=0,
                can_act=True,
                max_ap_this_turn=None,
                charm_attack_allies=False,
                allies_cannot_target=False,
                taunt_aura_disabled=False,
                prefer_not_attacked=False,
            )

    status_id = instance.status_id
    if status_id in STATUS_CC and _chance(instance.wake_chance, rng=rng):
        return StatusTurnResult(
            expired=False,
            cleansed=False,
            consumed_ap=-1,
            apply_tick=False,
            woke=True,
            remaining_rounds=0,
            can_act=False,
            max_ap_this_turn=0,
            charm_attack_allies=False,
            allies_cannot_target=False,
            taunt_aura_disabled=False,
            prefer_not_attacked=False,
        )

    apply_tick = status_id in STATUS_DOT or status_id in STATUS_STAT_MOD
    can_act = True
    max_ap: int | None = None
    charm = False
    allies_block = False
    taunt_off = False
    prefer_not = False
    if status_id == STATUS_COMA:
        can_act = False
        max_ap = 0
    elif status_id == STATUS_STUN:
        max_ap = 1
    elif status_id == STATUS_SLEEP:
        can_act = False
        max_ap = 0
        taunt_off = True
        prefer_not = True
    elif status_id == STATUS_CHARM:
        charm = True
        allies_block = True
        taunt_off = True

    return StatusTurnResult(
        expired=False,
        cleansed=False,
        consumed_ap=0,
        apply_tick=apply_tick,
        woke=False,
        remaining_rounds=remaining,
        can_act=can_act,
        max_ap_this_turn=max_ap,
        charm_attack_allies=charm,
        allies_cannot_target=allies_block,
        taunt_aura_disabled=taunt_off,
        prefer_not_attacked=prefer_not,
    )


def wake_on_hit(status_id: str) -> bool:
    """被攻击是否解除该异常。"""
    return bool(STATUS_WAKE_ON_HIT.get(status_id, False))


def offensive_talisman_allowed(*, is_move: bool, target_is_obstacle: bool) -> bool:
    """攻击性符箓只在攻击行动且目标非障碍时掷骰。"""
    return (not is_move) and (not target_is_obstacle)


def roll_offensive_talisman(
    *,
    use_chance: float,
    hit_chance: float,
    rng: Any = None,
) -> tuple[bool, bool]:
    """
    攻击回合：先是否使用符箓，再用是否命中。

    Returns:
        (used, hit)。未使用则 hit 恒为 False。
    """
    if not _chance(use_chance, rng=rng):
        return False, False
    return True, _chance(hit_chance, rng=rng)


def _chance(prob: float, *, rng: Any = None) -> bool:
    from app.domain.dice_rules import chance

    return chance(float(prob), rng=rng)
