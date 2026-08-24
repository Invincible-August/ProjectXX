"""工坊品质掷骰：高等级做低门槛图纸时高品质权重大幅提高。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.constants.craft import CRAFT_QUALITIES, CRAFT_QUALITY_COMMON


def resolve_quality_weights(
    level_delta: int,
    bands: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """
    按「制作者等级 - 图纸所需等级」取最高已达档的权重表。

    Args:
        level_delta: crafter_level - required_craft_level（负值按 0）。
        bands: 已按 min_delta 升序的档；每档含 min_delta 与 weights。

    Returns:
        quality_id → 正整数权重。缺省凡品 1。
    """
    delta = max(0, int(level_delta))
    chosen: Mapping[str, Any] | None = None
    for band in bands:
        try:
            min_delta = int(band.get("min_delta", 0) or 0)
        except (TypeError, ValueError):
            continue
        if delta >= min_delta:
            chosen = band
    raw = (chosen or {}).get("weights") or {}
    out: dict[str, int] = {}
    if isinstance(raw, Mapping):
        for key in CRAFT_QUALITIES:
            try:
                weight = int(raw.get(key, 0) or 0)
            except (TypeError, ValueError):
                weight = 0
            if weight > 0:
                out[key] = weight
    if not out:
        out[CRAFT_QUALITY_COMMON] = 1
    return out


def roll_craft_quality(
    level_delta: int,
    bands: Sequence[Mapping[str, Any]],
    *,
    rng: Any = None,
) -> str:
    """
    按档位权重掷一次品质。

    Args:
        level_delta: 制作者超出图纸门槛的等级差。
        bands: craft_recipes.yaml quality_by_level_delta。
        rng: 可选随机源（测试注入；需有 choices 或 random）。

    Returns:
        品质 id（common/fine/rare/superb）。
    """
    weights = resolve_quality_weights(level_delta, bands)
    keys = list(weights.keys())
    vals = [weights[k] for k in keys]
    picker = rng if rng is not None else __import__("random")
    if hasattr(picker, "choices"):
        return str(picker.choices(keys, weights=vals, k=1)[0])
    return keys[0]
