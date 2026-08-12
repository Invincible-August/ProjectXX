"""
轮回保留表应用纯函数（M5 D9 / D11 + 轮回强化）。

调用方负责事务与 ORM 写回；本模块只计算目标状态与日志摘要。
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.domain.dice_rules import weighted_pick

# 大境界从低到高（用于 peak / require 比较）
_DEFAULT_MAJOR_ORDER: tuple[str, ...] = (
    "body_tempering",
    "qi_refining",
    "foundation",
    "jindan",
    "yuanying",
    "huashen",
    "true_immortal",
)


@dataclass(frozen=True)
class PermanentBonusDelta:
    """一次轮回结算或商店升级产生的永久加成增量。"""

    initial_attr: float = 0.0
    minor_growth: float = 0.0
    major_growth: float = 0.0
    break_rate: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Serialize to plain dict."""
        return {
            "initial_attr": float(self.initial_attr),
            "minor_growth": float(self.minor_growth),
            "major_growth": float(self.major_growth),
            "break_rate": float(self.break_rate),
        }


@dataclass
class ReincarnationPlan:
    """轮回结算计划（事务内应用到角色与副作用；本值对象无 IO）。"""

    major_realm: str
    realm_stage: int
    realm_stage_label: str
    realm_progress: int
    cultivation_points: int
    body_tempering_points: int
    crafting_exp: int
    spirit_stones: int
    status: str
    idle_direction: str
    ferry_deadline_at: None
    reincarnation_points_delta: int
    growth_attrs: dict[str, Any]
    story_flags: dict[str, Any]
    dissolve_avatar: bool
    invalidate_snapshots: bool
    path: str
    permanent_delta: PermanentBonusDelta = field(
        default_factory=PermanentBonusDelta,
    )
    clear_normal_bag: bool = True
    unequip_excess_constitution: bool = True
    summary: dict[str, Any] = field(default_factory=dict)


def parse_story_flags(raw: str | None) -> dict[str, Any]:
    """
    Parse ``story_flags_json`` into a dict with ``experienced_nodes`` list.

    Args:
        raw: JSON text or None.

    Returns:
        dict: Normalized story flags.
    """
    if not raw:
        return {"experienced_nodes": [], "first_tribulation_done": False}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"experienced_nodes": [], "first_tribulation_done": False}
    if not isinstance(data, dict):
        return {"experienced_nodes": [], "first_tribulation_done": False}
    nodes = data.get("experienced_nodes") or []
    if not isinstance(nodes, list):
        nodes = []
    return {
        "experienced_nodes": [str(x) for x in nodes],
        "first_tribulation_done": bool(data.get("first_tribulation_done", False)),
        **{
            k: v
            for k, v in data.items()
            if k not in ("experienced_nodes", "first_tribulation_done")
        },
    }


def dump_story_flags(flags: Mapping[str, Any]) -> str:
    """Serialize story flags to JSON text."""
    return json.dumps(dict(flags), ensure_ascii=False)


def parse_growth_attrs(raw: str | None) -> dict[str, Any]:
    """Parse growth_attrs_json (兼容占位)."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_legacy_items_json(raw: str | None) -> list[str]:
    """
    Parse ``legacy_items_json`` into a list of legacy catalog ids.

    Args:
        raw: JSON text (list of strings) or None.

    Returns:
        list[str]: Legacy item ids; empty on missing/invalid JSON.
    """
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def dump_legacy_items(items: list[str]) -> str:
    """
    Serialize legacy item ids to JSON text.

    Args:
        items: Legacy catalog ids.

    Returns:
        str: JSON array text.
    """
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def parse_shop_offers_json(raw: str | None) -> list[str]:
    """
    Parse random shop offer ids from JSON.

    Args:
        raw: JSON list text or None.

    Returns:
        list[str]: Offer pool item ids currently on shelf.
    """
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def dump_shop_offers(offer_ids: Sequence[str]) -> str:
    """Serialize random shop offer ids."""
    return json.dumps([str(x) for x in offer_ids], ensure_ascii=False)


# 新生 / 商店错误码（与 activity 40074+ 错开）
ERR_NEWBORN_STATUS = 40078
ERR_NEWBORN_SELECTION = 40079
ERR_SHOP_ITEM = 40080
ERR_SHOP_POINTS = 40081
ERR_SHOP_FATE = 40082
ERR_SHOP_REFRESH = 40083
ERR_SLOT_CAP = 40084
ERR_BAG_MOVE = 40085


def mark_story_node(flags: dict[str, Any], node_id: str) -> dict[str, Any]:
    """
    Append an experienced story node id (idempotent).

    Args:
        flags: Mutable story flags.
        node_id: Node identifier.

    Returns:
        dict: Updated flags (same object).
    """
    nodes = list(flags.get("experienced_nodes") or [])
    if node_id not in nodes:
        nodes.append(str(node_id))
    flags["experienced_nodes"] = nodes
    return flags


def major_rank(
    major_id: str,
    order: Sequence[str] | None = None,
) -> int:
    """
    Rank of a major realm (higher = stronger). Unknown → -1.

    Args:
        major_id: Major realm id.
        order: Ordered major ids low→high.

    Returns:
        int: Rank index.
    """
    seq = tuple(order) if order else _DEFAULT_MAJOR_ORDER
    try:
        return seq.index(str(major_id))
    except ValueError:
        return -1


def meets_min_major_realm(
    character_major: str,
    min_major: str,
    order: Sequence[str] | None = None,
) -> bool:
    """
    Whether ``character_major`` is at or above ``min_major``.

    Args:
        character_major: Current major realm id.
        min_major: Required minimum major realm id.
        order: Optional low→high order (defaults to built-in chain).

    Returns:
        bool: True when unlocked.
    """
    need = str(min_major or "").strip()
    if not need:
        return True
    return major_rank(character_major, order) >= major_rank(need, order)


def resolve_peak_major(
    current_major: str,
    stored_peak: str | None,
    order: Sequence[str] | None = None,
) -> str:
    """
    Pick the higher of current vs stored peak.

    Args:
        current_major: Current major realm.
        stored_peak: Persisted peak or None.
        order: Major order.

    Returns:
        str: Peak major id.
    """
    peak = (stored_peak or "").strip() or current_major
    if major_rank(current_major, order) >= major_rank(peak, order):
        return current_major
    return peak


def normalize_points_path(path: str) -> str:
    """
    Map path aliases to points multiplier keys.

    Args:
        path: ``forced`` / ``self`` / ``voluntary_ferry`` / ``altar``.

    Returns:
        str: Key in ``path_multipliers``.
    """
    raw = (path or "forced").strip().lower()
    if raw in ("self", "voluntary", "voluntary_ferry", "ferry"):
        return "self"
    if raw == "altar":
        return "altar"
    return "forced"


def compute_reincarnation_points(
    peak_major: str,
    path: str,
    points_cfg: Mapping[str, Any],
) -> int:
    """
    Compute reincarnation points: base(peak) × path multiplier.

    Args:
        peak_major: Historical peak major before reset.
        path: Entry path (forced/self/altar/...).
        points_cfg: Config ``points`` section.

    Returns:
        int: Points to add (floored, non-negative).
    """
    base_table = points_cfg.get("base_per_peak_major") or points_cfg.get(
        "per_peak_major",
    ) or {}
    base = int(base_table.get(peak_major, 0))
    mult_table = points_cfg.get("path_multipliers") or {}
    path_key = normalize_points_path(path)
    mult = float(mult_table.get(path_key, 1.0))
    return max(0, int(math.floor(base * mult)))


def compute_settle_permanent_delta(
    peak_major: str,
    bonus_cfg: Mapping[str, Any],
) -> PermanentBonusDelta:
    """
    Permanent bonus granted on each reincarnation settle by peak major.

    Args:
        peak_major: Peak major before reset.
        bonus_cfg: ``permanent_bonus_on_settle`` section.

    Returns:
        PermanentBonusDelta: Four-axis increment.
    """
    table = bonus_cfg.get("per_peak_major") or {}
    row = table.get(peak_major) or {}
    if not isinstance(row, dict):
        row = {}
    return PermanentBonusDelta(
        initial_attr=float(row.get("initial_attr", 0.0)),
        minor_growth=float(row.get("minor_growth", 0.0)),
        major_growth=float(row.get("major_growth", 0.0)),
        break_rate=float(row.get("break_rate", 0.0)),
    )


def free_slots_from_count(
    reincarnation_count: int,
    free_by_count: Mapping[Any, Any],
    initial: int,
) -> int:
    """
    Resolve free slot count from reincarnation milestones.

    Args:
        reincarnation_count: Completed reincarnations (after settle).
        free_by_count: Mapping count→free slots.
        initial: Starting free slots.

    Returns:
        int: Free slots (max of initial and all unlocked milestones).
    """
    best = int(initial)
    for key, value in (free_by_count or {}).items():
        try:
            need = int(key)
            unlocked = int(value)
        except (TypeError, ValueError):
            continue
        if int(reincarnation_count) >= need:
            best = max(best, unlocked)
    return best


def compute_slot_cap(
    *,
    reincarnation_count: int,
    bought: int,
    slots_kind_cfg: Mapping[str, Any],
) -> int:
    """
    Equippable / selectable slot cap for constitution or spirit_root.

    Formula: min(total_max, free_by_count + bought).

    Args:
        reincarnation_count: Character reincarnation_count.
        bought: Shop-purchased slots.
        slots_kind_cfg: One of ``slots.constitution`` / ``slots.spirit_root``.

    Returns:
        int: Cap (>=0).
    """
    initial = int(slots_kind_cfg.get("initial", 1))
    free_by = slots_kind_cfg.get("free_by_count") or {}
    free = free_slots_from_count(reincarnation_count, free_by, initial)
    total_max = int(slots_kind_cfg.get("total_max", free + int(bought)))
    shop_max = int(slots_kind_cfg.get("shop_max_buy", 99))
    bought_clamped = max(0, min(int(bought), shop_max))
    return max(0, min(total_max, free + bought_clamped))


def compute_reincarnation_bag_slots(
    reincarnation_count: int,
    bags_cfg: Mapping[str, Any],
) -> int:
    """
    Reincarnation bag capacity by reincarnation count.

    Args:
        reincarnation_count: Completed reincarnations.
        bags_cfg: ``bags`` section.

    Returns:
        int: Max stack-rows in reincarnation bag.
    """
    rein = bags_cfg.get("reincarnation") or {}
    base = int(rein.get("base_slots", 4))
    per = int(rein.get("slots_per_count", 1))
    cap = int(rein.get("max_slots", 24))
    return max(0, min(cap, base + per * max(0, int(reincarnation_count))))


def clamp_break_success_rate(
    base_rate: float,
    break_rate_bonus: float,
    clamp_cfg: Mapping[str, Any] | None,
) -> float:
    """
    Apply permanent break_rate bonus then clamp.

    Args:
        base_rate: YAML breakthrough success_rate.
        break_rate_bonus: Permanent additive bonus.
        clamp_cfg: ``{min, max}`` from breakthrough or reincarnation yaml.

    Returns:
        float: Final success rate in [min, max].
    """
    lo = float((clamp_cfg or {}).get("min", 0.05))
    hi = float((clamp_cfg or {}).get("max", 0.95))
    raw = float(base_rate) + float(break_rate_bonus)
    return max(lo, min(hi, raw))


def combat_attr_multiplier(
    initial_attr_bonus: float,
    lifetime_applied_growth: float,
) -> float:
    """
    Multiplier applied to realm stage base atk/hp.

    Args:
        initial_attr_bonus: Permanent initial attr.
        lifetime_applied_growth: This-life applied growth.

    Returns:
        float: ``1 + initial + applied`` (floored at 0).
    """
    return max(0.0, 1.0 + float(initial_attr_bonus) + float(lifetime_applied_growth))


def filter_random_pool(
    pool: Mapping[str, Any],
    *,
    reincarnation_count: int,
    peak_major: str,
    major_order: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Filter shop random pool by require conditions.

    Args:
        pool: ``shop.random.pool`` mapping.
        reincarnation_count: Character count.
        peak_major: Peak major realm.
        major_order: Order for min_peak_major checks.

    Returns:
        dict: Eligible pool entries (id → meta).
    """
    eligible: dict[str, Any] = {}
    peak_rank = major_rank(peak_major, major_order)
    for item_id, meta in (pool or {}).items():
        if not isinstance(meta, dict):
            continue
        require = meta.get("require") or {}
        if not isinstance(require, dict):
            require = {}
        min_count = int(require.get("min_reincarnation_count", 0))
        if int(reincarnation_count) < min_count:
            continue
        min_peak = require.get("min_peak_major")
        if min_peak:
            if peak_rank < major_rank(str(min_peak), major_order):
                continue
        eligible[str(item_id)] = meta
    return eligible


def roll_shop_offers(
    eligible_pool: Mapping[str, Any],
    offer_count: int,
    *,
    rng: random.Random | None = None,
) -> list[str]:
    """
    Weighted roll of distinct random shop offers (dice weighted_pick).

    Args:
        eligible_pool: Filtered pool.
        offer_count: Number of offers.
        rng: Optional RNG (tests inject).

    Returns:
        list[str]: Offer item ids (may be fewer if pool small).
    """
    if offer_count <= 0 or not eligible_pool:
        return []
    remaining = dict(eligible_pool)
    picked: list[str] = []
    for _ in range(int(offer_count)):
        if not remaining:
            break
        weights = {
            item_id: float(meta.get("weight", 1) or 1)
            for item_id, meta in remaining.items()
        }
        choice = weighted_pick(weights, rng=rng)
        if choice is None:
            break
        picked.append(str(choice))
        remaining.pop(str(choice), None)
    return picked


def shop_fixed_catalog(shop_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """
    Resolve fixed shop items (``fixed_items`` with fallback to ``items``).

    Args:
        shop_cfg: ``shop`` section.

    Returns:
        dict: item_id → meta.
    """
    fixed = shop_cfg.get("fixed_items") or {}
    legacy = shop_cfg.get("items") or {}
    merged: dict[str, Any] = {}
    if isinstance(legacy, dict):
        merged.update(legacy)
    if isinstance(fixed, dict):
        merged.update(fixed)
    return merged


def build_reincarnation_plan(
    *,
    path: str,
    major_realm: str,
    peak_major: str,
    spirit_stones: int,
    growth_attrs_json: str | None,
    story_flags_json: str | None,
    reincarnation_points: int,
    carry_cfg: Mapping[str, Any],
    points_cfg: Mapping[str, Any],
    story_cfg: Mapping[str, Any],
    permanent_bonus_cfg: Mapping[str, Any] | None = None,
    bags_cfg: Mapping[str, Any] | None = None,
    growth_attr_gain: int = 1,
    stage_label_for_reset: str = "layer_1",
) -> ReincarnationPlan:
    """
    Build a reincarnation plan: reset realm, points, permanent delta, flags.

    Args:
        path: ``forced`` / ``self`` / ``altar`` / ``voluntary_ferry``.
        major_realm: Current major before reset (legacy preview).
        peak_major: Historical peak used for points/bonus.
        spirit_stones: Current stones.
        growth_attrs_json: Existing growth attrs JSON.
        story_flags_json: Existing story flags JSON.
        reincarnation_points: Current points.
        carry_cfg: ``reincarnation.yaml`` carry section.
        points_cfg: Points section.
        story_cfg: Story section.
        permanent_bonus_cfg: ``permanent_bonus_on_settle`` section.
        bags_cfg: ``bags`` section.
        growth_attr_gain: Placeholder growth attr increment.
        stage_label_for_reset: Label for stage 1 body_tempering.

    Returns:
        ReincarnationPlan: Values to apply transactionally.
    """
    reset = carry_cfg.get("realm_reset") or {}
    target_major = str(reset.get("major", "body_tempering"))
    target_stage = int(reset.get("stage", 1))

    ratio = float(carry_cfg.get("clear_spirit_stones_ratio", 1.0))
    new_stones = int(spirit_stones * (1.0 - min(1.0, max(0.0, ratio))))

    growth = parse_growth_attrs(growth_attrs_json)
    growth["placeholder"] = int(growth.get("placeholder", 0)) + int(growth_attr_gain)

    flags = parse_story_flags(story_flags_json)
    if not story_cfg.get("keep_experienced_nodes", True):
        flags["experienced_nodes"] = []
    if story_cfg.get("clear_first_tribulation_done", True):
        flags["first_tribulation_done"] = False

    delta = compute_reincarnation_points(peak_major, path, points_cfg)
    permanent_delta = compute_settle_permanent_delta(
        peak_major,
        permanent_bonus_cfg or {},
    )

    clear_pools = bool(carry_cfg.get("clear_pools", True))
    dissolve = str(carry_cfg.get("avatar", "dissolve")) == "dissolve"
    clear_normal = bool((bags_cfg or {}).get("normal", {}).get("clear_on_reincarnate", True))

    return ReincarnationPlan(
        major_realm=target_major,
        realm_stage=target_stage,
        realm_stage_label=stage_label_for_reset,
        realm_progress=0,
        cultivation_points=0 if clear_pools else 0,
        body_tempering_points=0 if clear_pools else 0,
        crafting_exp=0 if clear_pools else 0,
        spirit_stones=new_stones,
        status="reincarnating",
        idle_direction="none",
        ferry_deadline_at=None,
        reincarnation_points_delta=delta,
        growth_attrs=growth,
        story_flags=flags,
        dissolve_avatar=dissolve,
        invalidate_snapshots=True,
        path=path,
        permanent_delta=permanent_delta,
        clear_normal_bag=clear_normal,
        unequip_excess_constitution=True,
        summary={
            "from_major": major_realm,
            "peak_major": peak_major,
            "to_major": target_major,
            "points_gained": delta,
            "points_after": int(reincarnation_points) + delta,
            "path": path,
            "path_key": normalize_points_path(path),
            "permanent_delta": permanent_delta.to_dict(),
            "needs_newborn_setup": True,
        },
    )
