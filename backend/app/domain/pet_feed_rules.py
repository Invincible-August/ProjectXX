"""
PET-D04 喂养领域规则：上限校验与效果汇总。

纯函数；扣药与写库由 PetService 负责。
"""

from __future__ import annotations

from typing import Any, Mapping


def total_feed_used(counts: Mapping[str, int]) -> int:
    """已喂养总次数（各丹药次数之和）。"""
    return sum(max(0, int(v)) for v in counts.values())


def resolve_total_feed_cap(
    *,
    grade: int,
    species_id: str,
    total_feed_cap: int,
    by_grade: Mapping[int, int] | None = None,
    by_species: Mapping[str, int] | None = None,
) -> int:
    """
    解析单宠总量上限。

    优先级：物种覆盖 > 品阶覆盖 > 默认 total_feed_cap。
    返回 0 表示不限总量。
    """
    if by_species and species_id in by_species:
        return max(0, int(by_species[species_id]))
    if by_grade and int(grade) in by_grade:
        return max(0, int(by_grade[int(grade)]))
    return max(0, int(total_feed_cap))


def accumulate_feed_effects(
    counts: Mapping[str, int],
    *,
    items: Mapping[str, Any],
) -> dict[str, float]:
    """
    按已喂次数 × 单次 effects 汇总 flat/pct。

    Args:
        counts: item_id → 已喂次数。
        items: feed item 配置（含 effects）。

    Returns:
        flat_atk / pct_hp 等键。
    """
    out: dict[str, float] = {
        "flat_atk": 0.0,
        "flat_hp": 0.0,
        "flat_speed": 0.0,
        "pct_atk": 0.0,
        "pct_hp": 0.0,
        "pct_speed": 0.0,
    }
    for item_id, times in counts.items():
        n = max(0, int(times))
        if n <= 0:
            continue
        cfg = items.get(item_id)
        if cfg is None:
            continue
        effects = (
            dict(cfg.get("effects") or {})
            if isinstance(cfg, dict)
            else dict(getattr(cfg, "effects", None) or {})
        )
        for key, val in effects.items():
            k = str(key)
            if k in out:
                out[k] += float(val) * n
    return out


def validate_feed_batch(
    *,
    item_id: str,
    quantity: int,
    counts: Mapping[str, int],
    item_cfg: Any,
    total_cap: int,
) -> None:
    """
    校验一次喂养是否合法。

    Raises:
        ValueError: 超单药上限 / 超总量 / 数量非法 / 未知药。
    """
    if quantity <= 0:
        raise ValueError("喂养数量须为正整数")
    if item_cfg is None:
        raise ValueError(f"未知兽丹：{item_id}")
    per_cap = int(
        item_cfg.get("per_item_cap", 0)
        if isinstance(item_cfg, dict)
        else getattr(item_cfg, "per_item_cap", 0)
    )
    already = int(counts.get(item_id, 0))
    if per_cap > 0 and already + quantity > per_cap:
        raise ValueError(
            f"该丹已达单药上限（{already}/{per_cap}，本次 {quantity}）",
        )
    if total_cap > 0:
        used = total_feed_used(counts)
        if used + quantity > total_cap:
            raise ValueError(
                f"喂养总量已达上限（{used}/{total_cap}，本次 {quantity}）",
            )
