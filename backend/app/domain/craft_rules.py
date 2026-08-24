"""
M4 工坊领域：效率、完成时刻、失败掷骰、队列占用。

纯函数；CraftService 负责持久化。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from app.constants.m4 import CRAFT_ACTIVE_STATUSES, CraftActor, IdleDirection


def compute_efficiency(
    *,
    actor: str,
    character_idle_direction: str,
    avatar_idle_direction: str | None,
    main_crafting_bonus: float,
) -> float:
    """
    配方队列效率乘区（设计 D6）。

    - 本体队列且 idle_direction=crafting → main_crafting_bonus
    - 化身队列且 avatar idle_direction=crafting → 同样 bonus
    - 其它 → 1.0

    参数:
        actor: main 或 avatar。
        character_idle_direction: 本体挂机方向。
        avatar_idle_direction: 化身挂机方向（actor=avatar 时使用）。
        main_crafting_bonus: craft_recipes.yaml 配置的效率加成。

    返回:
        效率乘区（≥ 1.0 或配置值）。
    """
    if actor == CraftActor.MAIN and character_idle_direction == IdleDirection.CRAFTING:
        return main_crafting_bonus
    if actor == CraftActor.AVATAR and avatar_idle_direction == IdleDirection.CRAFTING:
        return main_crafting_bonus
    return 1.0


def compute_finish_at(
    started_at: datetime,
    duration_seconds: int,
    efficiency: float,
) -> datetime:
    """
    按效率计算权威完成时刻（efficiency 越高 finish 越早）。

    参数:
        started_at: 开工 UTC 时刻。
        duration_seconds: 配方基础耗时（秒）。
        efficiency: 效率乘区（≥ 0.01 防除零）。

    返回:
        权威 finish_at。
    """
    eff = max(0.01, efficiency)
    effective_duration = duration_seconds / eff
    return started_at + timedelta(seconds=effective_duration)


def roll_fail(fail_chance: float, *, rng: Any = None) -> bool:
    """
    失败掷骰占位（走修为骰子系统概率门面）。

    参数:
        fail_chance: [0, 1] 失败概率。
        rng: 可选随机源（测试注入）。

    返回:
        True 表示本次失败。
    """
    from app.domain.dice_rules import chance

    return chance(fail_chance, rng=rng)

def _job_field(job: Any, name: str) -> Any:
    """从 ORM 或 dict 读取字段（兼容历史调用）。"""
    if isinstance(job, dict):
        return job.get(name)
    return getattr(job, name, None)


def count_active_jobs(jobs: list[Any], actor: str, max_per_actor: int) -> bool:
    """
    队列是否已满。

    返回:
        True 表示已满（不可再开工）。
    """
    active = sum(
        1
        for j in jobs
        if _job_field(j, "actor") == actor
        and _job_field(j, "status") in CRAFT_ACTIVE_STATUSES
    )
    return active >= max_per_actor


def read_craft_levels(
    *,
    growth_attrs: Mapping[str, Any] | None,
    array_craft_level: int = 0,
) -> dict[str, int]:
    """
    读取五分支制造业等级。

    阵法以 ``characters.array_craft_level`` 为准；其余读 ``growth_attrs.craft_levels``。
    """
    from app.constants.character import (
        CRAFT_BRANCH_ARRAY,
        CRAFT_BRANCHES,
        GROWTH_ATTR_CRAFT_LEVELS_KEY,
    )

    raw = (growth_attrs or {}).get(GROWTH_ATTR_CRAFT_LEVELS_KEY) or {}
    if not isinstance(raw, dict):
        raw = {}
    out: dict[str, int] = {}
    for branch in CRAFT_BRANCHES:
        if branch == CRAFT_BRANCH_ARRAY:
            out[branch] = max(0, int(array_craft_level or 0))
            continue
        try:
            out[branch] = max(0, int(raw.get(branch, 0) or 0))
        except (TypeError, ValueError):
            out[branch] = 0
    return out


def serialize_craft_levels(
    *,
    growth_attrs: Mapping[str, Any] | None,
    array_craft_level: int = 0,
) -> list[dict[str, Any]]:
    """角色面板用：branch / label_zh / level。"""
    from app.constants.character import CRAFT_BRANCH_LEVEL_LABEL_ZH, CRAFT_BRANCHES

    levels = read_craft_levels(
        growth_attrs=growth_attrs,
        array_craft_level=array_craft_level,
    )
    return [
        {
            "branch": branch,
            "label_zh": CRAFT_BRANCH_LEVEL_LABEL_ZH.get(branch, branch),
            "level": levels[branch],
        }
        for branch in CRAFT_BRANCHES
    ]


def bump_craft_level(
    growth_attrs: dict[str, Any],
    *,
    branch: str,
    amount: int,
    array_craft_level: int = 0,
) -> tuple[dict[str, Any], int]:
    """
    提升非阵法分支制作等级，写回 growth_attrs.craft_levels。

    阵法等级仍走 characters.array_craft_level，本函数不改 array。

    Returns:
        (updated_growth_attrs, new_level_for_branch)
    """
    from app.constants.character import (
        CRAFT_BRANCH_ARRAY,
        GROWTH_ATTR_CRAFT_LEVELS_KEY,
    )

    if amount <= 0 or branch == CRAFT_BRANCH_ARRAY:
        return growth_attrs, int(array_craft_level or 0)
    levels = read_craft_levels(
        growth_attrs=growth_attrs,
        array_craft_level=array_craft_level,
    )
    levels[branch] = max(0, int(levels.get(branch, 0) or 0) + int(amount))
    next_attrs = dict(growth_attrs or {})
    stored = {
        key: int(val)
        for key, val in levels.items()
        if key != CRAFT_BRANCH_ARRAY
    }
    next_attrs[GROWTH_ATTR_CRAFT_LEVELS_KEY] = stored
    return next_attrs, levels[branch]
