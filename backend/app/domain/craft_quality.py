"""工坊造物品阶掷骰：高等级做低门槛图纸时高品阶权重大幅提高。

品阶与 §0.0.3 物品稀有度统一为粗糙～太古（gray…red）。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.constants.craft import (
    CRAFT_QUALITIES,
    CRAFT_QUALITY_DEFAULT,
    CRAFT_QUALITY_LABEL_ZH,
    LEGACY_CRAFT_QUALITY_MAP,
)


def normalize_craft_quality(raw: str | None) -> str:
    """
    Normalize craft quality / legacy aliases to a canonical seven-tier id.

    Args:
        raw: Machine id, Chinese label, or legacy common/fine/rare/superb.

    Returns:
        One of ``CRAFT_QUALITIES``; unknown → ``white``（普通）.
    """
    text = str(raw or "").strip()
    if not text:
        return CRAFT_QUALITY_DEFAULT
    lower = text.lower()
    if lower in CRAFT_QUALITIES:
        return lower
    if text in CRAFT_QUALITIES:
        return text
    if lower in LEGACY_CRAFT_QUALITY_MAP:
        return LEGACY_CRAFT_QUALITY_MAP[lower]
    if text in LEGACY_CRAFT_QUALITY_MAP:
        return LEGACY_CRAFT_QUALITY_MAP[text]
    for qid, label in CRAFT_QUALITY_LABEL_ZH.items():
        if text == label:
            return qid
    return CRAFT_QUALITY_DEFAULT


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
        quality_id → 正整数权重。缺省普通 1。旧键 common/fine… 会归一到七档。
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
        for key, val in raw.items():
            qid = normalize_craft_quality(str(key))
            try:
                weight = int(val or 0)
            except (TypeError, ValueError):
                weight = 0
            if weight > 0 and qid in CRAFT_QUALITIES:
                out[qid] = out.get(qid, 0) + weight
    if not out:
        out[CRAFT_QUALITY_DEFAULT] = 1
    return out


def roll_craft_quality(
    level_delta: int,
    bands: Sequence[Mapping[str, Any]],
    *,
    rng: Any = None,
) -> str:
    """
    按档位权重掷一次造物品阶。

    Args:
        level_delta: 制作者超出图纸门槛的等级差。
        bands: craft_recipes.yaml quality_by_level_delta。
        rng: 可选随机源（测试注入；需有 choices 或 random）。

    Returns:
        品阶 id（gray/white/green/blue/purple/orange/red）。
    """
    weights = resolve_quality_weights(level_delta, bands)
    keys = list(weights.keys())
    vals = [weights[k] for k in keys]
    picker = rng if rng is not None else __import__("random")
    if hasattr(picker, "choices"):
        return str(picker.choices(keys, weights=vals, k=1)[0])
    return keys[0]
