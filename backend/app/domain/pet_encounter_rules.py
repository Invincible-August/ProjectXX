"""
M4-D04c 遭遇表匹配与加权抽取（纯函数）。
"""

from __future__ import annotations

import random
from typing import Any, Mapping, Sequence


def table_match_score(
    table: Mapping[str, Any],
    *,
    region_id: str,
    shichen: str,
    weather: str,
) -> int:
    """
    表行匹配分数；越高越优先。不匹配返回 -1。

    精确键得高分，``*`` 通配得低分。
    """
    t_region = str(table.get("region_id") or "*")
    t_shichen = str(table.get("shichen") or "*")
    t_weather = str(table.get("weather") or "*")
    if t_region not in ("*", region_id):
        return -1
    if t_shichen not in ("*", shichen):
        return -1
    if t_weather not in ("*", weather):
        return -1
    score = 0
    if t_region == region_id:
        score += 100
    if t_shichen == shichen:
        score += 10
    if t_weather == weather:
        score += 1
    return score


def pick_encounter_table(
    tables: Sequence[Mapping[str, Any]],
    *,
    region_id: str,
    shichen: str,
    weather: str,
) -> Mapping[str, Any] | None:
    """
    选取最佳遭遇表行。

    Returns:
        表行映射；无匹配则 None。
    """
    best: Mapping[str, Any] | None = None
    best_score = -1
    for row in tables:
        score = table_match_score(
            row,
            region_id=region_id,
            shichen=shichen,
            weather=weather,
        )
        if score > best_score:
            best_score = score
            best = row
    return best if best_score >= 0 else None


def weighted_pick_index(
    weights: Sequence[float | int],
    *,
    rng: random.Random,
) -> int | None:
    """按权重抽下标；全 ≤0 返回 None。"""
    pairs = [(i, float(w)) for i, w in enumerate(weights) if float(w) > 0]
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    pick = rng.random() * total
    acc = 0.0
    for idx, weight in pairs:
        acc += weight
        if pick <= acc:
            return idx
    return pairs[-1][0]


def pick_encounter_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    rng: random.Random,
) -> Mapping[str, Any] | None:
    """
    从 entries 加权抽取一条遭遇。

    Args:
        entries: 含 weight 的条目列表。
        rng: 随机源。
    """
    weights = [float(e.get("weight") or 0) for e in entries]
    idx = weighted_pick_index(weights, rng=rng)
    if idx is None:
        return None
    return entries[idx]


def pick_grade_from_weights(
    grade_weights: Mapping[int, int] | Mapping[str, int] | None,
    *,
    rng: random.Random,
    fallback: int = 1,
) -> int:
    """品阶权重抽取。"""
    raw = grade_weights or {fallback: 100}
    pairs: list[tuple[int, float]] = []
    for k, v in raw.items():
        g = int(k)
        w = float(v)
        if w > 0:
            pairs.append((g, w))
    if not pairs:
        return fallback
    total = sum(w for _, w in pairs)
    pick = rng.random() * total
    acc = 0.0
    for grade, weight in pairs:
        acc += weight
        if pick <= acc:
            return grade
    return pairs[-1][0]
