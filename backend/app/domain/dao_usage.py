"""
道值运用与经验升级纯规则（无 IO）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.dao_rules import DaoResourceRules, DaoUsageBranch, resolve_dao_level


@dataclass(frozen=True)
class DaoUsageResult:
    """一次运用结算结果（供服务层写库）。"""

    qi_cost: int
    qi_after: int
    exp_gain: int
    exp_after: int
    level_before: int
    level_after: int
    leveled_up: bool
    damage_mul: float
    mitigation_mul: float
    fail_rate_delta: float
    bonus_affix_chance: float


def apply_usage(
    *,
    qi: int,
    total_exp: int,
    resources: DaoResourceRules,
    branch: DaoUsageBranch,
    success: bool,
) -> DaoUsageResult:
    """
    扣道值并结算经验（成功全额；失败可减半）。

    Args:
        qi: 当前道值。
        total_exp: 累计道经验。
        resources: 曲线配置。
        branch: 战斗/工坊分支。
        success: 本次运用是否成功（战斗胜/工坊成功）。

    Returns:
        DaoUsageResult。

    Raises:
        ValueError: 道值不足（调用方映 40084）。
    """
    cost = int(branch.qi_cost)
    if int(qi) < cost:
        raise ValueError("dao_qi_insufficient")
    qi_after = int(qi) - cost
    raw_exp = int(branch.dao_exp)
    if not success and branch.fail_exp_half:
        exp_gain = raw_exp // 2
    elif not success:
        exp_gain = 0
    else:
        exp_gain = raw_exp
    exp_after = int(total_exp) + exp_gain
    level_before, _, _ = resolve_dao_level(int(total_exp), resources.level_curve)
    level_after, _, _ = resolve_dao_level(exp_after, resources.level_curve)
    return DaoUsageResult(
        qi_cost=cost,
        qi_after=qi_after,
        exp_gain=exp_gain,
        exp_after=exp_after,
        level_before=level_before,
        level_after=level_after,
        leveled_up=level_after > level_before,
        damage_mul=float(branch.damage_mul),
        mitigation_mul=float(branch.mitigation_mul),
        fail_rate_delta=float(branch.fail_rate_delta),
        bonus_affix_chance=float(branch.bonus_affix_chance),
    )
