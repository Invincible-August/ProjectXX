"""
N4/PET-D01 灵宠领域：持有上限、等级战力、捕获加权、词条 roll / 洗炼。

纯函数；PetService 负责数据库与扣费。
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence


def can_hold_more(current_count: int, hold_cap: int) -> tuple[bool, int | None]:
    """
    持有上限校验。

    返回:
        (是否可再持有, 错误码或 None)。
    """
    if current_count >= hold_cap:
        return False, 40057
    return True, None


def species_base_dict(species: Any) -> dict[str, Any]:
    """
    将 YAML/配置物种对象规范为 combat_stats_from_level 所需字典。

    参数:
        species: 含 base_atk / base_hp / base_speed 的配置对象或 dict。
    """
    if isinstance(species, dict):
        return {
            "base_atk": int(species["base_atk"]),
            "base_hp": int(species["base_hp"]),
            "base_speed": int(species.get("base_speed", 10)),
        }
    return {
        "base_atk": int(species.base_atk),
        "base_hp": int(species.base_hp),
        "base_speed": int(getattr(species, "base_speed", 10)),
    }


def _affix_kind(type_cfg: Any, affix: Mapping[str, Any]) -> str:
    """从类型配置或词条实例解析 kind。"""
    if type_cfg is not None:
        if isinstance(type_cfg, dict):
            return str(type_cfg.get("kind") or "")
        return str(getattr(type_cfg, "kind", "") or "")
    return str(affix.get("kind") or "")


def combat_stats_from_level(
    species: dict[str, Any],
    level: int,
    *,
    level_stat_bonus: float,
    grade_base_mult: float = 1.0,
    affixes: Sequence[Mapping[str, Any]] | None = None,
    affix_types: Mapping[str, Any] | None = None,
    passive_combat_effects: Mapping[str, float] | None = None,
) -> dict[str, int]:
    """
    按等级与品阶乘区计算灵宠战斗面板，并叠加 flat/pct 词条与 combat 被动。

    公式：base * grade_mult * (1 + bonus * (level-1))，再 +flat，再 ×(1+pct/100)。
    ``passive_ref`` 词条本身不直接改面板；其引用的 combat 被动经
    ``passive_combat_effects`` 传入（PET-D03）。

    参数:
        species: pets.yaml 中 species 条目（或 species_base_dict 结果）。
        level: 当前等级（≥1）。
        level_stat_bonus: 每级加成比例。
        grade_base_mult: 个体品阶基础属性乘区（默认 1.0）。
        affixes: 词条实例列表。
        affix_types: affix_type_id → 配置（含 ``kind``）。
        passive_combat_effects: 已汇总的 combat 被动 flat/pct（PET-D03）。

    返回:
        atk / hp / speed 字典。
    """
    lvl = max(1, level)
    mult = float(grade_base_mult) * (1.0 + level_stat_bonus * (lvl - 1))
    atk = float(int(species["base_atk"]) * mult)
    hp = float(int(species["base_hp"]) * mult)
    # 速度：等级不加，仅品阶乘区 + 词条/被动
    speed = float(int(species.get("base_speed", 10)) * float(grade_base_mult))

    flat = {"atk": 0.0, "hp": 0.0, "speed": 0.0}
    pct = {"atk": 0.0, "hp": 0.0, "speed": 0.0}
    type_map = affix_types or {}
    for affix in affixes or ():
        type_id = str(affix.get("affix_type_id") or "")
        kind = _affix_kind(type_map.get(type_id), affix)
        value = float(affix.get("rolled_value") or 0)
        if kind == "flat_atk":
            flat["atk"] += value
        elif kind == "flat_hp":
            flat["hp"] += value
        elif kind == "flat_speed":
            flat["speed"] += value
        elif kind == "pct_atk":
            pct["atk"] += value
        elif kind == "pct_hp":
            pct["hp"] += value
        elif kind == "pct_speed":
            pct["speed"] += value
        # passive_ref / 未知 kind：跳过；被动效果由 passive_combat_effects 注入

    # PET-D03：种族天赋 + 独立被动 + 词条引用的 combat 被动
    pe = passive_combat_effects or {}
    flat["atk"] += float(pe.get("flat_atk", 0))
    flat["hp"] += float(pe.get("flat_hp", 0))
    flat["speed"] += float(pe.get("flat_speed", 0))
    pct["atk"] += float(pe.get("pct_atk", 0))
    pct["hp"] += float(pe.get("pct_hp", 0))
    pct["speed"] += float(pe.get("pct_speed", 0))

    atk = (atk + flat["atk"]) * (1.0 + pct["atk"] / 100.0)
    hp = (hp + flat["hp"]) * (1.0 + pct["hp"] / 100.0)
    speed = (speed + flat["speed"]) * (1.0 + pct["speed"] / 100.0)
    return {
        "atk": max(1, math.floor(atk)),
        "hp": max(1, math.floor(hp)),
        "speed": max(1, int(round(speed))),
    }


def weighted_choice(items: Sequence[str], weights: Sequence[float]) -> str:
    """按权重抽取一个 id；权重全 0 时均匀抽。"""
    if not items:
        raise ValueError("weighted_choice requires non-empty items")
    cleaned = [max(0.0, float(w)) for w in weights]
    if sum(cleaned) <= 0:
        return random.choice(list(items))
    return random.choices(list(items), weights=cleaned, k=1)[0]


def pick_capture_test_species(
    species_map: dict[str, Any],
    rarity_weights: dict[str, int],
    *,
    acquire_tag: str = "capture_test",
) -> str:
    """
    从带指定 acquire_tag 的物种中按稀有度权重抽取。

    Raises:
        ValueError: 无可抽物种。
    """
    pool: list[str] = []
    weights: list[float] = []
    for sid, sp in species_map.items():
        tags = getattr(sp, "acquire_tags", ()) or ()
        if acquire_tag not in tags:
            continue
        rarity = str(getattr(sp, "rarity", "common"))
        pool.append(sid)
        weights.append(float(rarity_weights.get(rarity, 0)))
    if not pool:
        raise ValueError(f"no species with acquire_tag={acquire_tag}")
    return weighted_choice(pool, weights)


def pick_capture_test_grade(grade_weights: dict[int, int]) -> int:
    """按配置权重抽取个体品阶。"""
    if not grade_weights:
        return 1
    keys = list(grade_weights.keys())
    weights = [float(grade_weights[k]) for k in keys]
    picked = weighted_choice([str(k) for k in keys], weights)
    return int(picked)


def _pick_affix_type_id(type_weights: Mapping[str, int]) -> str:
    """按类型权重抽 affix_type_id。"""
    items = [str(k) for k, w in type_weights.items() if int(w) > 0]
    weights = [float(type_weights[k]) for k in items]
    if not items:
        raise ValueError("pet_affixes.type_weights has no positive weights")
    return weighted_choice(items, weights)


def _pick_affix_tier(tier_weights: Mapping[str, int]) -> str:
    """按品级权重抽 affix_tier。"""
    items = [str(k) for k, w in tier_weights.items() if int(w) > 0]
    weights = [float(tier_weights[k]) for k in items]
    if not items:
        return "common"
    return weighted_choice(items, weights)


def roll_affix_value(min_value: float, max_value: float, *, kind: str) -> float | int:
    """
    在闭区间内重 roll 数值。

    flat_* 返回 int；pct_* / 其它返回保留 1 位小数的 float。
    """
    lo = float(min_value)
    hi = float(max_value)
    if hi < lo:
        lo, hi = hi, lo
    if kind.startswith("flat_"):
        return int(random.randint(int(math.floor(lo)), int(math.floor(hi))))
    if lo == hi and float(lo).is_integer():
        return int(lo)
    return round(random.uniform(lo, hi), 1)


def roll_one_affix(
    slot_index: int,
    *,
    types: Mapping[str, Any],
    type_weights: Mapping[str, int],
    tier_weights: Mapping[str, int],
) -> dict[str, Any]:
    """
    随机生成一条词条实例（类型 + 品级 + 数值）。

    Raises:
        ValueError: 类型库空或区间缺失。
    """
    type_id = _pick_affix_type_id(type_weights)
    type_cfg = types[type_id]
    kind = str(getattr(type_cfg, "kind", ""))
    tier = _pick_affix_tier(tier_weights)
    ranges = getattr(type_cfg, "tier_ranges", {}) or {}
    rng = ranges.get(tier)
    if rng is None:
        rng = ranges.get("common") or next(iter(ranges.values()), None)
    if rng is None:
        raise ValueError(f"affix type {type_id} has no tier_ranges")
    min_v = float(getattr(rng, "min_value", getattr(rng, "min", 0)))
    max_v = float(getattr(rng, "max_value", getattr(rng, "max", min_v)))
    value = roll_affix_value(min_v, max_v, kind=kind)
    return {
        "slot_index": int(slot_index),
        "affix_type_id": type_id,
        "affix_tier": tier,
        "rolled_value": value,
        "locked": False,
    }


def fill_affix_slots(
    slot_count: int,
    *,
    types: Mapping[str, Any],
    type_weights: Mapping[str, int],
    tier_weights: Mapping[str, int],
) -> list[dict[str, Any]]:
    """
    按品阶槽上限填满词条（捕获用）。

    参数:
        slot_count: 目标槽位数（= grades[g].affix_slots）。
    """
    count = max(0, int(slot_count))
    return [
        roll_one_affix(
            i,
            types=types,
            type_weights=type_weights,
            tier_weights=tier_weights,
        )
        for i in range(count)
    ]


def append_affix_on_grade_up(
    existing: Sequence[Mapping[str, Any]],
    *,
    types: Mapping[str, Any],
    type_weights: Mapping[str, int],
    tier_weights: Mapping[str, int],
) -> list[dict[str, Any]]:
    """
    升阶：保留旧词条，追加 1 条新随机类型词条。

    返回:
        新的完整词条列表（含拷贝旧槽）。
    """
    out: list[dict[str, Any]] = [dict(a) for a in existing]
    new_slot = len(out)
    out.append(
        roll_one_affix(
            new_slot,
            types=types,
            type_weights=type_weights,
            tier_weights=tier_weights,
        ),
    )
    return out


def reroll_affix_value_only(
    affixes: Sequence[Mapping[str, Any]],
    slot_index: int,
    *,
    types: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    数值-only 洗炼：保持 affix_type_id 与 affix_tier，仅重 roll rolled_value。

    Raises:
        ValueError: 槽不存在或类型配置缺失。
    """
    out: list[dict[str, Any]] = [dict(a) for a in affixes]
    target: dict[str, Any] | None = None
    for item in out:
        if int(item.get("slot_index", -1)) == int(slot_index):
            target = item
            break
    if target is None:
        raise ValueError(f"affix slot {slot_index} not found")
    type_id = str(target.get("affix_type_id") or "")
    tier = str(target.get("affix_tier") or "common")
    type_cfg = types.get(type_id)
    if type_cfg is None:
        raise ValueError(f"unknown affix type {type_id}")
    kind = str(getattr(type_cfg, "kind", ""))
    ranges = getattr(type_cfg, "tier_ranges", {}) or {}
    rng = ranges.get(tier) or ranges.get("common")
    if rng is None:
        raise ValueError(f"no range for type={type_id} tier={tier}")
    min_v = float(getattr(rng, "min_value", 0))
    max_v = float(getattr(rng, "max_value", min_v))
    # 禁止改类型/品级：仅写数值
    target["rolled_value"] = roll_affix_value(min_v, max_v, kind=kind)
    return out


def value_reroll_cost(*, base: float, grow: float, times_already: int) -> int:
    """
    第 (times_already+1) 次数值洗炼费用。

    公式: cost = base * (1+grow)^times_already；向上取整。
    """
    k = max(0, int(times_already))
    cost = float(base) * ((1.0 + float(grow)) ** k)
    return max(1, int(math.ceil(cost)))


def grade_up_spirit_cost(*, base: float, grow: float, target_grade: int) -> int:
    """
    升到 target_grade 的灵石费用。

    公式: base * (1+grow)^(target_grade-2)；升到 2 时为 base。
    """
    exponent = max(0, int(target_grade) - 2)
    cost = float(base) * ((1.0 + float(grow)) ** exponent)
    return max(1, int(math.ceil(cost)))


def type_reroll_cost(
    *,
    base_1: float,
    grow: float,
    slot_ordinal_1based: int,
    times_already: int,
) -> int:
    """
    灵兽宗改词条类型费用（PET-D06）。

    公式:
        base_i = base_1 * i
        cost_{i,k} = base_i * (1+grow)^{k-1}
    其中 i = slot_ordinal_1based（从 1 起），k-1 = times_already（该槽已改次数）。

    Args:
        base_1: 第 1 个可改类型槽的首次费用。
        grow: 同槽递增系数（如 0.1）。
        slot_ordinal_1based: 可改类型槽序号（通常 = slot_index + 1）。
        times_already: 该槽已完成的改类型次数。

    Returns:
        向上取整后的灵石费用（至少 1）。
    """
    ordinal = max(1, int(slot_ordinal_1based))
    already = max(0, int(times_already))
    base_i = float(base_1) * float(ordinal)
    # round 消浮点尘埃后再 ceil，保证 100*(1.1)=110 而非 111
    cost = round(base_i * ((1.0 + float(grow)) ** already), 6)
    return max(1, int(math.ceil(cost)))


def reroll_affix_type(
    affixes: Sequence[Mapping[str, Any]],
    slot_index: int,
    *,
    types: Mapping[str, Any],
    type_weights: Mapping[str, int],
    tier_weights: Mapping[str, int],
) -> list[dict[str, Any]]:
    """
    改词条类型：重 roll 该槽的类型 + 品级 + 数值；其它槽不变。

    Raises:
        ValueError: 目标槽不存在。
    """
    out: list[dict[str, Any]] = [dict(a) for a in affixes]
    found = False
    for idx, item in enumerate(out):
        if int(item.get("slot_index", -1)) == int(slot_index):
            # 整槽替换为新随机实例（类型/品级/数值一并重 roll）
            out[idx] = roll_one_affix(
                int(slot_index),
                types=types,
                type_weights=type_weights,
                tier_weights=tier_weights,
            )
            found = True
            break
    if not found:
        raise ValueError(f"affix slot {slot_index} not found")
    return out
