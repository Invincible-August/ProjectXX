"""
双修纯规则（M7 L7）：性别 / 功法门槛 / 掷骰档查表。

无 IO；禁止业务裸 random。
"""

from __future__ import annotations

from typing import Any


VALID_GENDERS = frozenset({"male", "female"})
ACTIVE_SESSION_STATUSES = frozenset({"inviting", "confirmed", "running"})
BOARD_KEYS = (
    "male_number_one",
    "male_zero",
    "female_number_one",
    "female_zero",
)


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
    组装四榜机读键。

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
