"""
修为检定骰纯函数：查表、叠修正、钳制、掷骰与概率门面。

详见 ``骰子系统设计.md``。本模块不得依赖 FastAPI / SQLAlchemy。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DiceModContribution:
    """单条上下限修正贡献（用于面板拆解）。"""

    # 来源标识：realm_base / technique / body_track / fate_luck / item / equipment
    source: str
    # 来源实例 id（境界、功法 id 等）
    id: str
    # 展示名
    label: str
    # 对下限的加成（可为负）
    min_bonus: int
    # 对上限的加成（可为负）
    max_bonus: int


@dataclass(frozen=True)
class DiceBounds:
    """解析后的实际掷骰区间。"""

    # 实际下限（含）
    lo: int
    # 实际上限（含）
    hi: int
    # 查表得到的基础下限
    base_min: int
    # 查表得到的基础上限
    base_max: int
    # 用途（breakthrough / combat_damage 等）
    purpose: str
    # 修正拆解
    breakdown: tuple[DiceModContribution, ...] = field(default_factory=tuple)

    @property
    def mid(self) -> float:
        """区间中点（伤害 normalizer 用）。"""
        return (self.lo + self.hi) / 2.0

    @property
    def span(self) -> int:
        """区间宽度（含端点）。"""
        return max(1, self.hi - self.lo + 1)


def lookup_realm_bounds(
    realm_bounds: Mapping[str, Mapping[int | str, Mapping[str, Any]]],
    *,
    major_realm: str,
    stage: int,
    fallback_min: int = 1,
    fallback_max: int = 20,
) -> tuple[int, int]:
    """
    按大境界 + 小境界查表取默认上下限。

    参数:
        realm_bounds: dice.yaml 的 realm_bounds。
        major_realm: 大境界 id。
        stage: 小境界编号（层或期）。
        fallback_min / fallback_max: 缺键回落。

    返回:
        (base_min, base_max)。
    """
    major_table = realm_bounds.get(str(major_realm)) or {}
    # 兼容 YAML 键为 int 或 str
    entry = major_table.get(stage)
    if entry is None:
        entry = major_table.get(str(stage))
    if not isinstance(entry, Mapping):
        return int(fallback_min), int(fallback_max)
    return int(entry.get("min", fallback_min)), int(entry.get("max", fallback_max))


def technique_mod_for_level(
    dice_mods: Sequence[Mapping[str, Any]] | None,
    level: int,
) -> tuple[int, int]:
    """
    取功法第 level 级的骰子修正（level 从 1 起；列表下标 0 对应 1 级）。

    参数:
        dice_mods: 功法配置中的 dice_mods 列表。
        level: 当前功法等级。

    返回:
        (min_bonus, max_bonus)。
    """
    if not dice_mods or level <= 0:
        return 0, 0
    idx = min(len(dice_mods), level) - 1
    row = dice_mods[idx] or {}
    return int(row.get("min_bonus", 0)), int(row.get("max_bonus", 0))


def fate_luck_mod(
    tiers: Sequence[Mapping[str, Any]],
    fate_luck: int,
) -> tuple[int, int]:
    """
    按气运值查分档修正。

    参数:
        tiers: fate_luck_tiers 列表。
        fate_luck: 角色气运。

    返回:
        (min_bonus, max_bonus)。
    """
    luck = int(fate_luck)
    for tier in tiers:
        lo = int(tier.get("min_luck", 0))
        hi = int(tier.get("max_luck", 100))
        if lo <= luck <= hi:
            return int(tier.get("min_bonus", 0)), int(tier.get("max_bonus", 0))
    return 0, 0


def body_realm_mod(
    body_bonus_table: Mapping[str, Mapping[int | str, Mapping[str, Any]]],
    *,
    major_realm: str,
    stage: int,
) -> tuple[int, int]:
    """
    体修道小境界附加修正。

    参数:
        body_bonus_table: body_realm_bonus。
        major_realm: 大境界。
        stage: 小境界。

    返回:
        (min_bonus, max_bonus)。
    """
    major_table = body_bonus_table.get(str(major_realm)) or {}
    entry = major_table.get(stage)
    if entry is None:
        entry = major_table.get(str(stage))
    if not isinstance(entry, Mapping):
        return 0, 0
    return int(entry.get("min_bonus", 0)), int(entry.get("max_bonus", 0))


def clamp_bounds(
    lo: int,
    hi: int,
    *,
    absolute_min: int = 1,
    absolute_max: int = 200,
) -> tuple[int, int]:
    """
    钳制并保证 lo ≤ hi。

    参数:
        lo / hi: 原始区间。
        absolute_min / absolute_max: 全局钳制。

    返回:
        (lo, hi)。
    """
    lo_c = max(int(absolute_min), min(int(absolute_max), int(lo)))
    hi_c = max(int(absolute_min), min(int(absolute_max), int(hi)))
    if lo_c > hi_c:
        lo_c, hi_c = hi_c, lo_c
    return lo_c, hi_c


def resolve_bounds(
    *,
    purpose: str,
    base_min: int,
    base_max: int,
    contributions: Sequence[DiceModContribution] = (),
    absolute_min: int = 1,
    absolute_max: int = 200,
) -> DiceBounds:
    """
    将基础表与修正叠成实际区间。

    参数:
        purpose: 用途 id。
        base_min / base_max: 查表基础。
        contributions: 修正列表。
        absolute_min / absolute_max: 全局钳制。

    返回:
        DiceBounds。
    """
    delta_min = sum(c.min_bonus for c in contributions)
    delta_max = sum(c.max_bonus for c in contributions)
    lo, hi = clamp_bounds(
        int(base_min) + delta_min,
        int(base_max) + delta_max,
        absolute_min=absolute_min,
        absolute_max=absolute_max,
    )
    base_row = DiceModContribution(
        source="realm_base",
        id="base",
        label="境界基础",
        min_bonus=0,
        max_bonus=0,
    )
    # breakdown 首行标明 base；后续为各通道
    full = (base_row, *tuple(contributions))
    return DiceBounds(
        lo=lo,
        hi=hi,
        base_min=int(base_min),
        base_max=int(base_max),
        purpose=str(purpose),
        breakdown=full,
    )


def roll_int(lo: int, hi: int, *, rng: random.Random | None = None) -> int:
    """
    在闭区间 [lo, hi] 上均匀掷整数。

    参数:
        lo / hi: 区间。
        rng: 可选随机源。

    返回:
        出目。
    """
    a, b = clamp_bounds(lo, hi)
    r = rng or random
    return int(r.randint(a, b))


def roll_bounds(bounds: DiceBounds, *, rng: random.Random | None = None) -> int:
    """
    按 DiceBounds 掷骰。

    参数:
        bounds: 已解析区间。
        rng: 可选随机源。

    返回:
        出目。
    """
    return roll_int(bounds.lo, bounds.hi, rng=rng)


def breakthrough_threshold(lo: int, hi: int, success_rate: float) -> int:
    """
    将 success_rate 映射为「掷到此值及以上算成功」的阈值。

    参数:
        lo / hi: 区间。
        success_rate: [0,1] 目标成功率。

    返回:
        threshold（含）。
    """
    a, b = clamp_bounds(lo, hi)
    span = b - a + 1
    rate = max(0.0, min(1.0, float(success_rate)))
    success_count = max(1, int(round(rate * span)))
    success_count = min(span, success_count)
    return b - success_count + 1


def breakthrough_success(
    roll: int,
    lo: int,
    hi: int,
    success_rate: float,
) -> tuple[bool, int]:
    """
    突破成功判定。

    参数:
        roll: 出目。
        lo / hi: 区间。
        success_rate: 目标成功率。

    返回:
        (是否成功, 阈值)。
    """
    threshold = breakthrough_threshold(lo, hi, success_rate)
    return int(roll) >= threshold, threshold


def chance(probability: float, *, rng: random.Random | None = None) -> bool:
    """
    伯努利检定门面（制造失败、遮天等）。

    参数:
        probability: 成功/触发概率 [0,1]。
        rng: 可选随机源。

    返回:
        True 表示命中。
    """
    p = max(0.0, min(1.0, float(probability)))
    r = rng or random
    return r.random() < p


def weighted_pick(
    weights: Mapping[str, float | int],
    *,
    rng: random.Random | None = None,
) -> str | None:
    """
    权重抽取门面（品阶等）。

    参数:
        weights: id → 权重（≤0 忽略）。
        rng: 可选随机源。

    返回:
        抽中的 id；全空则 None。
    """
    pairs = [(str(k), float(v)) for k, v in weights.items() if float(v) > 0]
    if not pairs:
        return None
    r = rng or random
    total = sum(w for _, w in pairs)
    pick = r.random() * total
    acc = 0.0
    for key, weight in pairs:
        acc += weight
        if pick <= acc:
            return key
    return pairs[-1][0]


def damage_dice_factor(
    roll: int,
    bounds: DiceBounds,
    *,
    use_midpoint: bool = True,
    legacy_normalizer: float = 10.0,
) -> float:
    """
    伤害骰因子：默认 roll/mid；否则 roll/legacy_normalizer。

    参数:
        roll: 出目。
        bounds: 区间。
        use_midpoint: 是否用中点归一。
        legacy_normalizer: 旧 board.damage_dice_normalizer。

    返回:
        乘到攻击上的因子（>0）。
    """
    if use_midpoint:
        mid = max(1.0, float(bounds.mid))
        return float(roll) / mid
    return float(roll) / max(1.0, float(legacy_normalizer))
