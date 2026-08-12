"""
雷劫双维与批次伤害纯函数（M5 D6 / D14 / D16）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Mapping, Sequence

# 威力档降序：遮天 / 护主降档用
POWER_TIER_ORDER: tuple[str, ...] = ("apocalypse", "jealousy", "normal", "mercy")


@dataclass(frozen=True)
class TribulationDims:
    """雷劫双维：威力品阶 × 次数档（由突破品阶或层进阶表映射）。"""

    power_tier: str  # apocalypse/jealousy/normal/mercy
    count_tier: str  # nine/eighty_one/thousand/myriad


def map_grade_to_tribulation(
    grade_id: str | None,
    grade_table: Mapping[str, Mapping[str, str]],
    *,
    default_power: str = "mercy",
    default_count: str = "nine",
) -> TribulationDims:
    """
    Map a projected breakthrough grade to tribulation dimensions.

    Args:
        grade_id: Grade id (inferior～heavenly) or None.
        grade_table: Config ``grade_to_tribulation``.
        default_power: Fallback power tier.
        default_count: Fallback count tier.

    Returns:
        TribulationDims: Power and count tier ids.
    """
    if grade_id and grade_id in grade_table:
        body = grade_table[grade_id]
        return TribulationDims(
            power_tier=str(body.get("power", default_power)),
            count_tier=str(body.get("count", default_count)),
        )
    return TribulationDims(power_tier=default_power, count_tier=default_count)


def map_layer_tribulation(
    target_major: str,
    layer_mapping: Mapping[str, Mapping[str, str]],
) -> TribulationDims:
    """
    Map a non-cross-major layer advance to tribulation dimensions.

    Args:
        target_major: Target major realm key.
        layer_mapping: Config ``layer_mapping`` (per-major or ``default``).

    Returns:
        TribulationDims: Power and count tiers.
    """
    body = layer_mapping.get(target_major) or layer_mapping.get("default") or {}
    return TribulationDims(
        power_tier=str(body.get("power", "mercy")),
        count_tier=str(body.get("count", "nine")),
    )


def lower_power_tier(power_tier: str) -> str:
    """
    Lower power tier by one step (apocalypse→…→mercy).

    Args:
        power_tier: Current tier id.

    Returns:
        str: Lowered tier; already ``mercy`` stays ``mercy``.
    """
    if power_tier not in POWER_TIER_ORDER:
        return "mercy"
    index = POWER_TIER_ORDER.index(power_tier)
    if index >= len(POWER_TIER_ORDER) - 1:
        return "mercy"
    return POWER_TIER_ORDER[index + 1]


def raise_power_tier(power_tier: str) -> str:
    """
    Raise power tier by one step (veil failure placeholder).

    Args:
        power_tier: Current tier id.

    Returns:
        str: Raised tier; already ``apocalypse`` stays.
    """
    if power_tier not in POWER_TIER_ORDER:
        return power_tier
    index = POWER_TIER_ORDER.index(power_tier)
    if index <= 0:
        return "apocalypse"
    return POWER_TIER_ORDER[index - 1]


def fate_luck_band(fate_luck: int) -> str:
    """
    Map fate_luck integer to low/mid/high band.

    Args:
        fate_luck: Character fate luck placeholder (-100～100 typical).

    Returns:
        str: ``low`` / ``mid`` / ``high``.
    """
    if fate_luck < 0:
        return "low"
    if fate_luck > 50:
        return "high"
    return "mid"


def demonic_nature_band(demonic_nature: int) -> str:
    """
    Map demonic_nature integer to low/mid/high band.

    Args:
        demonic_nature: Character demonic nature placeholder.

    Returns:
        str: ``low`` / ``mid`` / ``high``.
    """
    if demonic_nature <= 0:
        return "low"
    if demonic_nature >= 60:
        return "high"
    return "mid"


def compute_strike_nominal(
    *,
    power_base_weight: float,
    realm_scale: float,
    strike_count: int,
    env_mult: float,
    in_cloud_double: bool,
    cloud_double_mult: float = 2.0,
    axis_a_mult: float = 1.0,
    mercy_damage_mult: float = 1.0,
) -> float:
    """
    Compute per-strike nominal damage before axis-B mitigation.

    Args:
        power_base_weight: Tier base weight.
        realm_scale: Target realm HP-scale placeholder.
        strike_count: Total strikes in this tribulation.
        env_mult: Locked weather×shichen pressure (already clamped).
        in_cloud_double: Whether opening inside existing cloud.
        cloud_double_mult: Extra multiplier when ``in_cloud_double``.
        axis_a_mult: Formation / fate / demonic product.
        mercy_damage_mult: Extra mult after guardian at mercy (e.g. 0.01).

    Returns:
        float: Damage before axis B.
    """
    count = max(1, int(strike_count))
    base = float(power_base_weight) * float(realm_scale)
    env = float(env_mult)
    if in_cloud_double:
        env *= float(cloud_double_mult)
    total = base * env * float(axis_a_mult) * float(mercy_damage_mult)
    return total / float(count)


def apply_axis_b_mitigation(
    raw_damage: float,
    *,
    prep_mitigation: float = 0.0,
    passive_resist: float = 0.0,
) -> float:
    """
    Apply axis-B mitigation (prep item + passive resist).

    Args:
        raw_damage: Nominal strike damage.
        prep_mitigation: Fraction reduced by next prep slot (0～1).
        passive_resist: Passive resist fraction (0～1).

    Returns:
        float: Mitigated damage (non-negative).
    """
    reduction = min(0.95, max(0.0, float(prep_mitigation) + float(passive_resist)))
    return max(0.0, float(raw_damage) * (1.0 - reduction))


@dataclass(frozen=True)
class GuardianResult:
    """灵宝护主检定结果（准备格耗尽且将死时概率触发）。"""

    triggered: bool  # 是否触发护主
    destroyed_artifact_id: str | None  # 被毁灵宝 id；未触发为 None
    hp_after: float  # 护主后 HP（通常回满 max 的 restore_ratio）
    new_power_tier: str  # 降档后的威力品阶
    mercy_damage_mult: float  # 怜悯档后续伤害乘区（可降至 0.01）


def try_guardian_proc(
    *,
    hp_current: float,
    hp_max: float,
    incoming_damage: float,
    prep_exhausted: bool,
    guardian_already_used: bool,
    available_artifact_ids: Sequence[str],
    proc_chance: float,
    restore_ratio: float,
    current_power_tier: str,
    mercy_damage_mult: float,
    rng: random.Random,
) -> GuardianResult:
    """
    Attempt 灵宝护主 when a lethal strike would land and prep is exhausted.

    Args:
        hp_current: Current tribulation HP.
        hp_max: Max tribulation HP.
        incoming_damage: Damage about to apply.
        prep_exhausted: Whether prep slots are empty.
        guardian_already_used: Session already used guardian.
        available_artifact_ids: Destroyable body artifacts.
        proc_chance: Config proc chance.
        restore_ratio: HP restore ratio of max.
        current_power_tier: Current power tier.
        mercy_damage_mult: Current mercy mult.
        rng: RNG for proc and artifact pick.

    Returns:
        GuardianResult: Trigger outcome and updated combat state fields.
    """
    would_die = (hp_current - incoming_damage) <= 0
    from app.domain.dice_rules import chance

    if (
        not prep_exhausted
        or not would_die
        or guardian_already_used
        or not available_artifact_ids
        or not chance(float(proc_chance), rng=rng)
    ):
        return GuardianResult(
            triggered=False,
            destroyed_artifact_id=None,
            hp_after=hp_current,
            new_power_tier=current_power_tier,
            mercy_damage_mult=mercy_damage_mult,
        )

    destroyed = rng.choice(list(available_artifact_ids))
    new_tier = lower_power_tier(current_power_tier)
    new_mercy = mercy_damage_mult
    if current_power_tier == "mercy":
        # 已在怜悯档：后续基础伤害 ×1%
        new_mercy = min(mercy_damage_mult, 0.01)
    restored = float(hp_max) * float(restore_ratio)
    return GuardianResult(
        triggered=True,
        destroyed_artifact_id=str(destroyed),
        hp_after=min(float(hp_max), restored),
        new_power_tier=new_tier,
        mercy_damage_mult=new_mercy,
    )


def compress_batch_events(
    events: list[dict],
    *,
    count_tier: str,
) -> list[dict]:
    """
    Compress thousand/myriad strike logs into summary rows for API payloads.

    Args:
        events: Per-strike event dicts.
        count_tier: Count tier id.

    Returns:
        list[dict]: Possibly compressed event list.
    """
    if count_tier not in ("thousand", "myriad") or len(events) <= 20:
        return events
    # 千/万劫：保留首尾各若干 + 一条摘要
    head = events[:5]
    tail = events[-5:]
    middle_damage = sum(float(e.get("damage", 0)) for e in events[5:-5])
    summary = {
        "type": "batch_summary",
        "omitted_strikes": len(events) - 10,
        "omitted_damage": round(middle_damage, 2),
    }
    return [*head, summary, *tail]
