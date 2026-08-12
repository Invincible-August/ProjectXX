"""
大道开道与道池纯规则（无 IO）。

加权抽 3、入池、锁定校验；禁止业务层裸 random。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DaoEntryDef:
    """单条道目录定义。"""

    dao_id: str
    label_zh: str
    category: str
    category_label: str
    rarity: str
    rarity_label: str
    weight: float
    description: str


@dataclass(frozen=True)
class DaoOpenRules:
    """开道门槛与会话规则。"""

    min_major_realm: str
    picks: int
    lock_per_run: bool
    deny_reroll: bool
    session_ttl_seconds: int


@dataclass(frozen=True)
class DaoResourceRules:
    """道值 / 道经验曲线。"""

    initial_dao_qi: int
    level_curve: tuple[int, ...]


@dataclass(frozen=True)
class DaoUsageBranch:
    """战斗或工坊运用占位。"""

    qi_cost: int
    dao_exp: int
    fail_exp_half: bool
    damage_mul: float = 1.0
    mitigation_mul: float = 1.0
    fail_rate_delta: float = 0.0
    bonus_affix_chance: float = 0.0


def build_candidate_weights(
    entries: Mapping[str, DaoEntryDef],
    *,
    owned_dao_ids: set[str],
) -> dict[str, float]:
    """
    生成开道加权池：排除已收藏道。

    Args:
        entries: 全量道目录。
        owned_dao_ids: 道池已有 dao_id。

    Returns:
        dao_id → weight（>0）。
    """
    result: dict[str, float] = {}
    for dao_id, entry in entries.items():
        if dao_id in owned_dao_ids:
            continue
        w = float(entry.weight)
        if w > 0:
            result[dao_id] = w
    return result


def backfill_candidates_if_short(
    weights: dict[str, float],
    entries: Mapping[str, DaoEntryDef],
    *,
    owned_dao_ids: set[str],
    need: int,
) -> dict[str, float]:
    """
    候选不足 ``need`` 时，从「未收藏全集」用原权重补足（设计 §3.2）。

    若仍不足则返回当前（调用方判 40095）。
    """
    if len(weights) >= need:
        return weights
    merged = dict(weights)
    for dao_id, entry in entries.items():
        if dao_id in owned_dao_ids or dao_id in merged:
            continue
        w = float(entry.weight)
        if w > 0:
            merged[dao_id] = w
        if len(merged) >= need:
            break
    return merged


def pick_unique_weighted(
    weights: Mapping[str, float],
    *,
    count: int,
    weighted_pick,
) -> list[str]:
    """
    无放回加权抽取 ``count`` 个 id。

    Args:
        weights: 权重表。
        count: 抽取数。
        weighted_pick: ``DiceService.weighted_pick`` 兼容可调用
            ``(weights, *, rng=None) -> str | None``。

    Returns:
        抽中的 dao_id 列表（长度可能 < count）。
    """
    remaining = {k: float(v) for k, v in weights.items() if float(v) > 0}
    picked: list[str] = []
    for _ in range(count):
        if not remaining:
            break
        choice = weighted_pick(remaining)
        if choice is None:
            break
        picked.append(str(choice))
        remaining.pop(str(choice), None)
    return picked


def resolve_dao_level(total_exp: int, level_curve: Sequence[int]) -> tuple[int, int, int | None]:
    """
    由累计道经验解析等级。

    Args:
        total_exp: 累计道经验。
        level_curve: 升到各等级所需累计经验；index0 通常为 0。

    Returns:
        (level, exp_into_level, exp_to_next)；满级时 exp_to_next=None。
    """
    curve = list(level_curve) if level_curve else [0]
    if not curve:
        curve = [0]
    level = 1
    for idx in range(1, len(curve)):
        if total_exp >= int(curve[idx]):
            level = idx + 1
        else:
            break
    # level 对应 curve[level-1] 门槛
    floor = int(curve[level - 1]) if level - 1 < len(curve) else int(curve[-1])
    exp_into = max(0, int(total_exp) - floor)
    if level >= len(curve):
        return level, exp_into, None
    next_need = int(curve[level]) - int(total_exp)
    return level, exp_into, max(0, next_need)


def is_valid_open_choice(
    *,
    chosen_dao_id: str,
    offer_ids: Sequence[str],
    allow_pool_pick: bool,
    pool_ids: set[str],
) -> bool:
    """
    校验 choose 合法性：须在本次三选项内，或（再开）道池自选。

    Args:
        chosen_dao_id: 玩家选择。
        offer_ids: 本次 roll 的 3 道。
        allow_pool_pick: 是否允许选旧藏。
        pool_ids: 道池 id 集合。

    Returns:
        是否合法。
    """
    if chosen_dao_id in offer_ids:
        return True
    if allow_pool_pick and chosen_dao_id in pool_ids:
        return True
    return False


def catalog_entry_public(entry: DaoEntryDef, *, owned: bool) -> dict[str, Any]:
    """目录条目玩家可见 dict（中文）。"""
    return {
        "dao_id": entry.dao_id,
        "label": entry.label_zh,
        "category": entry.category,
        "category_label": entry.category_label,
        "rarity": entry.rarity,
        "rarity_label": entry.rarity_label,
        "owned": owned,
        "description": entry.description,
    }
