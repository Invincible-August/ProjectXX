"""
M4 神识领域：容量、占用、阶梯超载衰减与反噬表（M4-D03）。

纯函数；开战前与快照更新时调用 apply_overload_mult。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OverloadBand:
    """单一超载档。"""

    max_load_ratio: float | None
    combat_stat_mult: float
    zone: str


@dataclass(frozen=True)
class BacklashEntry:
    """单一反噬档。"""

    id: str
    when: str
    idle_mult: float
    set_flag: bool
    summary: str


def compute_capacity(
    *,
    base_capacity: int,
    per_realm_bonus: dict[str, int],
    character_major: str,
    bonus_from_gm: int = 0,
) -> int:
    """
    计算神识容量 = base + 境界加成 + GM 可调 bonus。

    参数:
        base_capacity: divine_sense.yaml 基础容量。
        per_realm_bonus: 各境界加成表。
        character_major: 角色大境界 key。
        bonus_from_gm: characters.divine_sense_capacity_bonus。

    返回:
        总容量。
    """
    realm_bonus = int(per_realm_bonus.get(character_major, 0))
    return max(0, int(base_capacity) + realm_bonus + int(bonus_from_gm))


def compute_load(
    *,
    avatar_count: int,
    pet_count: int,
    cost_avatar: int,
    cost_pet: int,
    pet_costs: Sequence[int] | None = None,
) -> int:
    """
    计算上阵占用（化身×cost + 灵宠占用）。

    参数:
        avatar_count: 上阵化身数。
        pet_count: 上阵灵宠数（无 pet_costs 时用默认 cost_pet）。
        cost_avatar: 每个化身占用。
        cost_pet: 默认每个灵宠占用。
        pet_costs: 可选；各宠实际占用（含物种覆盖）；优先于 pet_count×cost_pet。

    返回:
        总占用。
    """
    avatar_load = int(avatar_count) * int(cost_avatar)
    if pet_costs is not None:
        return avatar_load + sum(max(0, int(c)) for c in pet_costs)
    return avatar_load + int(pet_count) * int(cost_pet)


def soft_hard_caps(capacity: int, *, soft_ratio: float, hard_ratio: float) -> tuple[int, int]:
    """
    由容量推导舒适阈值与严重超载线。

    返回:
        (舒适阈值 soft_cap, 严重超载线 hard_cap)。
    """
    soft = max(0, int(capacity * soft_ratio))
    hard = max(soft, int(capacity * hard_ratio))
    return soft, hard


def load_ratio(load: int, capacity: int) -> float:
    """load / capacity；容量为 0 时 load>0 → 极大比值。"""
    if capacity <= 0:
        return 999.0 if load > 0 else 0.0
    return float(load) / float(capacity)


def resolve_overload_band(
    load: int,
    capacity: int,
    *,
    soft_cap: int,
    bands: Sequence[OverloadBand] | Sequence[Mapping[str, Any]],
    fallback_stat_mult: float = 0.7,
) -> OverloadBand:
    """
    解析当前超载档。

    规则:
        - load ≤ soft_cap → 舒适档（mult=1.0）
        - 否则按 load/capacity 匹配 bands（max_load_ratio 升序；None 兜底）
        - bands 空 → 兼容旧线性混成结果封装为单档
    """
    if load <= soft_cap:
        return OverloadBand(max_load_ratio=None, combat_stat_mult=1.0, zone="comfort")

    normalized: list[OverloadBand] = []
    for raw in bands:
        if isinstance(raw, OverloadBand):
            normalized.append(raw)
            continue
        max_r = raw.get("max_load_ratio")
        normalized.append(
            OverloadBand(
                max_load_ratio=None if max_r is None else float(max_r),
                combat_stat_mult=float(raw.get("combat_stat_mult", fallback_stat_mult)),
                zone=str(raw.get("zone") or "overload"),
            ),
        )

    if not normalized:
        # 旧线性占位：超出量/load 混成
        mult = overload_multiplier_legacy(
            load,
            capacity,
            overload_stat_mult=fallback_stat_mult,
        )
        return OverloadBand(max_load_ratio=None, combat_stat_mult=mult, zone="overload")

    # 有限阈值在前，None 兜底在后
    finite = sorted(
        [b for b in normalized if b.max_load_ratio is not None],
        key=lambda b: float(b.max_load_ratio or 0),
    )
    catch_all = [b for b in normalized if b.max_load_ratio is None]
    ratio = load_ratio(load, capacity)
    for band in finite:
        if ratio <= float(band.max_load_ratio or 0):
            return band
    if catch_all:
        return catch_all[-1]
    return finite[-1] if finite else OverloadBand(
        max_load_ratio=None,
        combat_stat_mult=fallback_stat_mult,
        zone="critical",
    )


def overload_multiplier_legacy(
    load: int,
    capacity: int,
    *,
    overload_stat_mult: float,
) -> float:
    """旧线性混成（无 bands 时兼容）。"""
    if load <= capacity or load <= 0:
        return 1.0
    overload_part = load - capacity
    ratio = min(1.0, overload_part / load)
    return 1.0 - ratio * (1.0 - overload_stat_mult)


def overload_multiplier(
    load: int,
    capacity: int,
    *,
    overload_stat_mult: float = 0.7,
    soft_cap: int | None = None,
    bands: Sequence[OverloadBand] | Sequence[Mapping[str, Any]] | None = None,
) -> float:
    """
    超载战斗属性乘区（M4-D03：优先阶梯表）。

    参数:
        load: 占用。
        capacity: 容量。
        overload_stat_mult: 无 bands 时的旧线性底。
        soft_cap: 舒适阈值；缺省=capacity。
        bands: 阶梯表。

    返回:
        乘区 ∈ (0, 1]。
    """
    soft = capacity if soft_cap is None else int(soft_cap)
    band = resolve_overload_band(
        load,
        capacity,
        soft_cap=soft,
        bands=bands or (),
        fallback_stat_mult=overload_stat_mult,
    )
    return float(band.combat_stat_mult)


def apply_overload_mult(stats: dict[str, Any], mult: float) -> dict[str, Any]:
    """
    对战斗面板施加神识超载衰减（atk/hp）。

    参数:
        stats: 含 atk/hp 的字典。
        mult: 乘区。

    返回:
        新面板（整数向下取整，至少 1）。
    """
    result = dict(stats)
    for key in ("atk", "hp"):
        if key in result:
            result[key] = max(1, int(float(result[key]) * mult))
    return result


def should_trigger_backlash(load: int, hard_cap: int) -> bool:
    """严重超载 → 触发反噬。"""
    return load > hard_cap


def resolve_backlash_entry(
    *,
    over_hard: bool,
    table: Sequence[BacklashEntry] | Sequence[Mapping[str, Any]],
    fallback_idle_mult: float = 0.5,
) -> BacklashEntry | None:
    """
    按条件取反噬档；未触发返回 None。

    参数:
        over_hard: load > hard_cap。
        table: 反噬表。
        fallback_idle_mult: 表空时的兼容乘区。
    """
    if not over_hard:
        return None
    for raw in table:
        if isinstance(raw, BacklashEntry):
            entry = raw
        else:
            entry = BacklashEntry(
                id=str(raw.get("id") or raw.get("when") or "over_hard"),
                when=str(raw.get("when") or "over_hard"),
                idle_mult=float(raw.get("idle_mult", fallback_idle_mult)),
                set_flag=bool(raw.get("set_flag", True)),
                summary=str(raw.get("summary") or ""),
            )
        if entry.when == "over_hard":
            return entry
    return BacklashEntry(
        id="over_hard",
        when="over_hard",
        idle_mult=float(fallback_idle_mult),
        set_flag=True,
        summary="严重超载·化身修炼减速",
    )


def backlash_idle_multiplier(
    has_backlash: bool,
    *,
    backlash_idle_mult: float = 0.5,
    entry: BacklashEntry | None = None,
) -> float:
    """反噬状态下化身挂机速率乘区。"""
    if not has_backlash:
        return 1.0
    if entry is not None:
        return float(entry.idle_mult)
    return float(backlash_idle_mult)
