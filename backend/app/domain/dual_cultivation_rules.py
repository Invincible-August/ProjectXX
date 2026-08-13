"""
双修纯规则（M7 L7）：性别 / 功法门槛 / 掷骰档 / 时长转化。

无 IO；禁止业务裸 random。

时长语义（现行占位）：
- 掷骰得到的 ``duration_sec`` 近似「双修持续秒数」；
- 一号位（主动）按秒累计插入时长，零号位累计承纳时长；
- 高潮概率（自身功法 + 双修环境 + 对方功法 + 掷骰）后续按秒结算细化，本阶段用掷骰档时长。
"""

from __future__ import annotations

from typing import Any


VALID_GENDERS = frozenset({"male", "female"})
# inviting 邀约中 · accepted 已接受待宽衣 · undressed 已宽衣待开始 · running 结算中
ACTIVE_SESSION_STATUSES = frozenset({"inviting", "accepted", "undressed", "running", "confirmed"})
BOARD_DURATION_TOTAL = "duration_total"
BOARD_KEYS = (
    BOARD_DURATION_TOTAL,
    "male_number_one",
    "male_zero",
    "female_number_one",
    "female_zero",
)
# 角色位：一号=主动 / 零号=承纳
ROLE_NUMBER_ONE = "number_one"
ROLE_ZERO = "zero"
VALID_ROLES = frozenset({ROLE_NUMBER_ONE, ROLE_ZERO})

STATUS_LABEL_ZH = {
    "inviting": "待接受",
    "accepted": "待宽衣",
    "undressed": "已宽衣",
    "running": "双修中",
    "settled": "已完成",
    "cancelled": "已取消",
    "timeout": "已超时",
    "confirmed": "待宽衣",  # 兼容旧态
}


def normalize_gender(raw: str | None) -> str | None:
    """
    规范化性别键。

    Args:
        raw: 原始字符串。

    Returns:
        ``male`` / ``female`` / None。
    """
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in VALID_GENDERS:
        return value
    return None


def gender_label_zh(gender: str | None) -> str:
    """性别中文展示。"""
    if gender == "male":
        return "乾道（男）"
    if gender == "female":
        return "坤道（女）"
    return "未定阴阳"


def normalize_role(raw: str | None) -> str:
    """
    规范化双修角色位。

    Args:
        raw: number_one|zero 或空。

    Returns:
        合法角色位；非法回落一号。
    """
    value = str(raw or ROLE_NUMBER_ONE).strip().lower()
    if value in VALID_ROLES:
        return value
    return ROLE_NUMBER_ONE


def opposite_role(role: str) -> str:
    """返回对位角色。"""
    return ROLE_ZERO if normalize_role(role) == ROLE_NUMBER_ONE else ROLE_NUMBER_ONE


def technique_allows_pair(
    technique: dict[str, Any],
    *,
    gender_a: str | None,
    gender_b: str | None,
) -> tuple[bool, str]:
    """
    校验双方性别是否满足功法。

    Args:
        technique: 功法定义。
        gender_a: 甲方性别。
        gender_b: 乙方性别。

    Returns:
        (ok, reason_zh)。
    """
    if not gender_a or not gender_b:
        return False, "双方须先补全道途阴阳（性别）"
    if bool(technique.get("require_opposite_gender")) and gender_a == gender_b:
        return False, "此功法须异性双修"
    return True, ""


def resolve_dice_tier(
    tiers: list[dict[str, Any]],
    roll: int,
) -> dict[str, Any]:
    """
    按出目查效果档；未命中取最后一档或默认 mid。

    Args:
        tiers: YAML ``dice_tiers``。
        roll: 骰出目。

    Returns:
        命中档 dict（含 effect_tier / yield_mult / duration_sec）。
    """
    for tier in tiers:
        lo = int(tier.get("min_roll", 0))
        hi = int(tier.get("max_roll", 10**9))
        if lo <= int(roll) <= hi:
            return dict(tier)
    if tiers:
        return dict(tiers[-1])
    return {
        "effect_tier": "mid",
        "yield_mult": 1.0,
        "duration_sec": 40,
        "label_zh": "合契",
    }


def board_key_for(*, gender: str, kind: str) -> str:
    """
    组装角色时长榜机读键。

    Args:
        gender: male|female。
        kind: number_one|zero。

    Returns:
        如 ``male_number_one``。
    """
    if gender not in VALID_GENDERS:
        raise ValueError("invalid gender")
    if kind not in ("number_one", "zero"):
        raise ValueError("invalid board kind")
    return f"{gender}_{kind}"


def scaled_yield(base: int, mult: float) -> int:
    """基础产出 × 倍率，至少 0。"""
    return max(0, int(round(float(base) * float(mult))))


def duration_conversion_ratio(duration_sec: int) -> float:
    """
    由双修时长得到基础转化率。

    曲线约定：1s→0.01，100s→1.0，200s→1.5（可超 100%）。

    Args:
        duration_sec: 本场持续秒。

    Returns:
        转化率（可为 >1）。
    """
    seconds = max(0, int(duration_sec))
    if seconds <= 100:
        return seconds / 100.0
    # 100s 后每再 200s 追加 +1.0 → 200s = 1.5
    return 1.0 + (seconds - 100) / 200.0


def cultivation_gap_factor(
    giver_cultivation: int,
    receiver_cultivation: int,
    *,
    gap_scale: int = 500,
) -> float:
    """
    修为差距对传功转化的修正项。

    传方高于受方 → 正值，用于压低甚至翻负转化率；
    受方高于传方 → 负值，用于抬高传方扣费倍率。

    Args:
        giver_cultivation: 传方修为池。
        receiver_cultivation: 受方修为池。
        gap_scale: 差距归一化尺度（YAML 可调）。

    Returns:
        gap / scale。
    """
    scale = max(1, int(gap_scale))
    return (int(giver_cultivation) - int(receiver_cultivation)) / float(scale)


def resolve_transfer_settlement(
    *,
    base_transfer: int,
    duration_sec: int,
    yield_mult: float,
    giver_cultivation: int,
    receiver_cultivation: int,
    gap_scale: int = 500,
) -> dict[str, Any]:
    """
    传功结算：时长转化 + 修为差距。

    - 时长越长转化越高，可超过 100%。
    - 传方远高于受方：转化可负（受方反而掉修为）；传方仍扣设定值。
    - 受方高于传方：传方扣费高于设定值；受方按 100% 基础值收取（再乘掷骰倍率）。

    Args:
        base_transfer: 设定传功值（YAML transfer_cost / base_yield）。
        duration_sec: 本场秒数。
        yield_mult: 掷骰倍率。
        giver_cultivation: 传方当前修为。
        receiver_cultivation: 受方当前修为。
        gap_scale: 差距尺度。

    Returns:
        含 giver_cost / receiver_delta / conversion_ratio 等字段。
    """
    base = max(0, int(base_transfer))
    duration_ratio = duration_conversion_ratio(duration_sec)
    gap = cultivation_gap_factor(
        giver_cultivation,
        receiver_cultivation,
        gap_scale=gap_scale,
    )
    mult = float(yield_mult) if yield_mult else 1.0

    if gap > 0:
        # 传方更强：时长率被差距压低，可为负
        conversion = duration_ratio - gap
        giver_cost = base
        receiver_delta = int(round(base * conversion * mult))
    elif gap < 0:
        # 受方更强：传方多扣；受方至少按 100% 基础收取
        cost_mult = 1.0 + abs(gap)
        giver_cost = max(base, int(round(base * cost_mult)))
        conversion = max(1.0, duration_ratio)
        receiver_delta = int(round(base * conversion * mult))
    else:
        conversion = duration_ratio
        giver_cost = base
        receiver_delta = int(round(base * conversion * mult))

    return {
        "base_transfer": base,
        "duration_sec": int(duration_sec),
        "duration_ratio": duration_ratio,
        "gap_factor": gap,
        "yield_mult": mult,
        "conversion_ratio": conversion,
        "giver_cost": int(giver_cost),
        "receiver_delta": int(receiver_delta),
    }


def resolve_mutual_gain(
    *,
    base_yield: int,
    duration_sec: int,
    yield_mult: float,
    cultivation_a: int,
    cultivation_b: int,
    gap_scale: int = 500,
) -> dict[str, Any]:
    """
    双增结算：时长抬收益；双方修为差距过大则压低双方收益。

    Args:
        base_yield: 功法基础双增。
        duration_sec: 时长。
        yield_mult: 掷骰倍率。
        cultivation_a: 甲方修为。
        cultivation_b: 乙方修为。
        gap_scale: 差距尺度。

    Returns:
        含双方 gain 与倍率字段。
    """
    base = max(0, int(base_yield))
    duration_ratio = duration_conversion_ratio(duration_sec)
    gap_abs = abs(
        cultivation_gap_factor(cultivation_a, cultivation_b, gap_scale=gap_scale),
    )
    # 差距越大双增越低，最低保留 10% 时长收益
    gap_penalty = min(0.9, gap_abs)
    effective = max(0.1, duration_ratio * (1.0 - gap_penalty)) * float(yield_mult or 1.0)
    gained = max(0, int(round(base * effective)))
    return {
        "base_yield": base,
        "duration_sec": int(duration_sec),
        "duration_ratio": duration_ratio,
        "gap_abs": gap_abs,
        "effective_mult": effective,
        "gain_each": gained,
    }


def resolve_extract_settlement(
    *,
    base_extract: int,
    duration_sec: int,
    yield_mult: float,
    extractor_cultivation: int,
    target_cultivation: int,
    gap_scale: int = 500,
) -> dict[str, Any]:
    """
    索取结算：从被索取方取修为。

    初始转化率：
    - 被索取方修为过低（索取方远高于对方）→ 0；
    - 索取方修为过低 → 负数；
    - 双方相当 → 1.0。
    再叠加时长抬升 ``(duration_ratio - 1)``。

    Args:
        base_extract: 设定索取值（YAML extract_cost / base_yield）。
        duration_sec: 本场秒数。
        yield_mult: 倍率。
        extractor_cultivation: 索取方修为。
        target_cultivation: 被索取方修为。
        gap_scale: 差距尺度。

    Returns:
        含 target_cost / extractor_delta / initial_conversion 等。
    """
    base = max(0, int(base_extract))
    duration_ratio = duration_conversion_ratio(duration_sec)
    # 正：索取方更强（被索取更弱）
    gap = cultivation_gap_factor(
        extractor_cultivation,
        target_cultivation,
        gap_scale=gap_scale,
    )
    mult = float(yield_mult) if yield_mult else 1.0

    if gap > 0:
        initial_conversion = 0.0
    elif gap < 0:
        initial_conversion = float(gap)
    else:
        initial_conversion = 1.0

    conversion = initial_conversion + (duration_ratio - 1.0)
    target_cost = base
    extractor_delta = int(round(base * conversion * mult))

    return {
        "base_extract": base,
        "duration_sec": int(duration_sec),
        "duration_ratio": duration_ratio,
        "gap_factor": gap,
        "yield_mult": mult,
        "initial_conversion": initial_conversion,
        "conversion_ratio": conversion,
        "target_cost": int(target_cost),
        "extractor_delta": int(extractor_delta),
    }


def status_label_zh(status: str | None) -> str:
    """会话状态中文。"""
    return STATUS_LABEL_ZH.get(str(status or ""), str(status or "—"))


def simulate_climax_loop(
    rng: Any,
    *,
    base_chance: float,
    growth_per_tick: float,
    chance_cap: float,
    max_ticks: int,
    tick_jitter: float,
    technique_mod: float = 0.0,
    partner_mod: float = 0.0,
    env_mod: float = 0.0,
) -> dict[str, Any]:
    """
    双修高潮循环：每轮抽插一次，累加发射几率直至发射。

    每轮基础时长 1 秒，再乘 ``1±tick_jitter``。禁止业务裸 ``random()``，
    须传入 ``DiceService.make_rng`` 实例。

    Args:
        rng: random.Random 兼容对象。
        base_chance: 初始发射几率。
        growth_per_tick: 每轮追加。
        chance_cap: 单轮几率上限。
        max_ticks: 最大轮次。
        tick_jitter: 秒数抖动比例（0.2=±20%）。
        technique_mod: 己方功法修正。
        partner_mod: 对方功法修正。
        env_mod: 环境修正。

    Returns:
        insert_count / duration_sec / climax_tick / mods / log_zh。
    """
    chance = max(0.0, float(base_chance))
    growth = max(0.0, float(growth_per_tick))
    cap = max(0.01, min(0.99, float(chance_cap)))
    limit = max(1, int(max_ticks))
    jitter = max(0.0, min(0.9, float(tick_jitter)))
    mod_sum = float(technique_mod) + float(partner_mod) + float(env_mod)
    duration = 0.0
    climax_tick = limit
    for tick in range(1, limit + 1):
        chance = min(cap, chance + growth)
        effective = min(cap, max(0.001, chance * (1.0 + mod_sum)))
        # 本轮耗时：1s ± jitter
        scale = 1.0 + (rng.random() * 2.0 - 1.0) * jitter
        duration += max(0.05, 1.0 * scale)
        if rng.random() < effective:
            climax_tick = tick
            break
    insert_count = int(climax_tick)
    duration_sec = max(1, int(round(duration)))
    log_zh = f"抽插 {insert_count} 次，耗时约 {duration_sec} 秒"
    return {
        "insert_count": insert_count,
        "duration_sec": duration_sec,
        "climax_tick": climax_tick,
        "final_chance": round(min(cap, chance * (1.0 + mod_sum)), 4),
        "technique_mod": technique_mod,
        "partner_mod": partner_mod,
        "env_mod": env_mod,
        "log_zh": log_zh,
    }
