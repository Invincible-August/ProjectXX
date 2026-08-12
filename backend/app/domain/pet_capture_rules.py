"""
M4-D04c 捕获成功率全因子（纯函数）；与 DiceService.chance 配合。
"""

from __future__ import annotations

import random
from typing import Any, Mapping, Sequence


_TIER_RANK = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "mythic": 5,
}


def tier_at_least(tier: str, min_tier: str) -> bool:
    """词条品级是否 ≥ 门槛。"""
    return _TIER_RANK.get(str(tier).lower(), 0) >= _TIER_RANK.get(str(min_tier).lower(), 0)


def count_special_affixes(
    affixes: Sequence[Mapping[str, Any]],
    *,
    min_tier: str,
) -> int:
    """统计特殊词条条数。"""
    n = 0
    for item in affixes:
        if tier_at_least(str(item.get("affix_tier") or "common"), min_tier):
            n += 1
    return n


def estimate_special_affix_count(
    *,
    slots: int,
    tier_weights: Mapping[str, int],
    min_tier: str,
    rng: random.Random,
) -> int:
    """
    按槽位独立抽品级，估计遭遇体特殊词条数（可审计）。

    不生成完整词条，仅计 rare+ 次数。
    """
    if slots <= 0:
        return 0
    pairs = [(str(k), float(v)) for k, v in tier_weights.items() if float(v) > 0]
    if not pairs:
        return 0
    total = sum(w for _, w in pairs)
    n = 0
    for _ in range(slots):
        pick = rng.random() * total
        acc = 0.0
        chosen = pairs[-1][0]
        for tier, weight in pairs:
            acc += weight
            if pick <= acc:
                chosen = tier
                break
        if tier_at_least(chosen, min_tier):
            n += 1
    return n


def player_realm_index(
    *,
    major_order: Sequence[str],
    major_realm: str,
    realm_stage: int,
    stages_per_major: int = 10,
) -> int:
    """
    玩家修为序数（大境链 × 层）。

    Args:
        major_order: 大境界 id 有序列表。
        major_realm: 当前大境。
        realm_stage: 小层。
        stages_per_major: 每境折合层数上限。
    """
    try:
        mi = list(major_order).index(str(major_realm))
    except ValueError:
        mi = 0
    stage = max(1, int(realm_stage))
    return mi * int(stages_per_major) + stage


def beast_realm_index(*, grade: int, stages_per_grade: int) -> int:
    """灵兽品阶折合修为序数。"""
    return max(1, int(grade)) * max(1, int(stages_per_grade))


def compute_capture_probability(
    *,
    p_race: float,
    p_taming_tech: float = 0.0,
    p_realm_diff: float = 0.0,
    p_root_affinity: float = 0.0,
    n_special_affix: int = 0,
    pen_affix: float = 0.05,
    pen_grade: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """
    计算捕获成功率并返回分项审计。

    Returns:
        (clamp 后的 p, factors 字典)。
    """
    pen_affix_total = max(0, int(n_special_affix)) * float(pen_affix)
    raw = (
        float(p_race)
        + float(p_taming_tech)
        + float(p_realm_diff)
        + float(p_root_affinity)
        - pen_affix_total
        - float(pen_grade)
    )
    p = max(0.0, min(1.0, raw))
    factors = {
        "p_race": float(p_race),
        "p_taming_tech": float(p_taming_tech),
        "p_realm_diff": float(p_realm_diff),
        "p_root_affinity": float(p_root_affinity),
        "pen_affix": float(pen_affix_total),
        "pen_grade": float(pen_grade),
        "n_special_affix": float(n_special_affix),
        "raw": float(raw),
        "p": float(p),
    }
    return p, factors


def realm_diff_bonus(
    *,
    player_index: int,
    beast_index: int,
    per_stage: float,
    clamp_min: float,
    clamp_max: float,
) -> float:
    """修为差加成（可负）。"""
    diff = int(player_index) - int(beast_index)
    bonus = diff * float(per_stage)
    return max(float(clamp_min), min(float(clamp_max), bonus))
