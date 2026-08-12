"""
PET-D03 被动与种族天赋领域规则：池抽取、战斗域效果投影。

纯函数；与词条分表。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain.pet_rules import weighted_choice


def roll_independent_passive(
    *,
    empty_weight: int,
    weights: Mapping[str, int],
) -> str | None:
    """
    从被动池抽取 0～1 个独立被动。

    ``empty_weight`` > 0 时允许抽空（返回 None）。权重全 0 且 empty=0 时返回 None。

    Args:
        empty_weight: 「空」结果权重。
        weights: passive_id → 权重。

    Returns:
        抽中的 passive_id，或 None 表示未 roll 到。
    """
    items: list[str] = []
    wts: list[float] = []
    for pid, w in weights.items():
        if int(w) > 0:
            items.append(str(pid))
            wts.append(float(w))
    empty = max(0, int(empty_weight))
    if empty > 0:
        items.append("")
        wts.append(float(empty))
    if not items:
        return None
    picked = weighted_choice(items, wts)
    return picked or None


def collect_combat_passive_effects(
    passive_ids: Sequence[str],
    *,
    passives: Mapping[str, Any],
) -> dict[str, float]:
    """
    汇总 combat 域被动的 flat/pct 效果。

    Args:
        passive_ids: 被动 id 列表（种族天赋 + 独立被动）。
        passives: passive_id → 配置（含 effect_domain / effects）。

    Returns:
        键如 flat_atk / pct_hp；缺省 0。
    """
    out: dict[str, float] = {
        "flat_atk": 0.0,
        "flat_hp": 0.0,
        "flat_speed": 0.0,
        "pct_atk": 0.0,
        "pct_hp": 0.0,
        "pct_speed": 0.0,
    }
    for pid in passive_ids:
        if not pid:
            continue
        cfg = passives.get(pid)
        if cfg is None:
            continue
        domain = (
            str(cfg.get("effect_domain", ""))
            if isinstance(cfg, dict)
            else str(getattr(cfg, "effect_domain", "") or "")
        )
        if domain != "combat":
            continue
        effects = (
            dict(cfg.get("effects") or {})
            if isinstance(cfg, dict)
            else dict(getattr(cfg, "effects", None) or {})
        )
        for key, val in effects.items():
            k = str(key)
            if k in out:
                out[k] += float(val)
    return out


def resolve_affix_passive_ids(
    affixes: Sequence[Mapping[str, Any]],
    *,
    affix_types: Mapping[str, Any],
) -> list[str]:
    """
    从词条实例中收集 kind=passive_ref 引用的 passive_id。

    Args:
        affixes: 词条实例。
        affix_types: 词条类型表。

    Returns:
        passive_id 列表（可重复则去重保序）。
    """
    seen: set[str] = set()
    out: list[str] = []
    for affix in affixes:
        type_id = str(affix.get("affix_type_id") or "")
        type_cfg = affix_types.get(type_id)
        if type_cfg is None:
            continue
        kind = (
            str(type_cfg.get("kind", ""))
            if isinstance(type_cfg, dict)
            else str(getattr(type_cfg, "kind", "") or "")
        )
        if kind != "passive_ref":
            continue
        pid = (
            type_cfg.get("passive_id")
            if isinstance(type_cfg, dict)
            else getattr(type_cfg, "passive_id", None)
        )
        if not pid:
            continue
        sid = str(pid)
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out
