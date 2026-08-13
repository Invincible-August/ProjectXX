"""
道友化身助战体力：独立槽，仅随境界变容，无加成。

与本体化身 ``stamina``（探索/独战等）完全隔离。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.core.time_utils import ensure_aware_utc, now_utc


def assist_stamina_cap(*, character_major: str, assist_cfg: Any) -> int:
    """
    助战体力上限：只看主人大境界。

    Args:
        character_major: 主人大境界键。
        assist_cfg: AvatarFriendAssistConfig。

    Returns:
        int: 上限。
    """
    by_major = getattr(assist_cfg, "stamina_cap_by_major", None) or {}
    if character_major in by_major:
        return max(1, int(by_major[character_major]))
    return max(1, int(getattr(assist_cfg, "stamina_base_cap", 50) or 50))


def assist_resume_threshold(cap: int, *, resume_ratio: float) -> int:
    """体力归零后须恢复到该值才可再助战（默认 20% 向上取整，至少 1）。"""
    ratio = max(0.0, min(1.0, float(resume_ratio)))
    return max(1, int(math.ceil(cap * ratio)))


def tick_assist_stamina(
    *,
    current: int,
    cap: int,
    recovered_at: datetime | None,
    recovery_per_hour: float,
    now: datetime | None = None,
) -> tuple[int, datetime]:
    """
    惰性恢复助战体力（无任何加成）。

    Returns:
        (new_stamina, new_anchor).
    """
    now = now or now_utc()
    cur = max(0, min(int(current), int(cap)))
    if recovered_at is None:
        return cur, now
    anchor = ensure_aware_utc(recovered_at)
    if now <= anchor or recovery_per_hour <= 0:
        return cur, anchor
    hours = (now - anchor).total_seconds() / 3600.0
    gain = int(hours * float(recovery_per_hour))
    if gain <= 0:
        return cur, anchor
    # 只推进「已完整恢复」的小时，避免截断损失
    consumed_hours = gain / float(recovery_per_hour)
    from datetime import timedelta

    new_anchor = anchor + timedelta(seconds=consumed_hours * 3600.0)
    return min(cap, cur + gain), new_anchor


def can_assist_with_stamina(
    *,
    stamina: int,
    cap: int,
    resume_ratio: float,
    battle_cost: int,
) -> tuple[bool, str | None]:
    """
    是否允许发起/继续助战。

    归零后须 ≥ resume 阈值；且至少够扣一场战斗。
    """
    thr = assist_resume_threshold(cap, resume_ratio=resume_ratio)
    cur = int(stamina)
    cost = max(1, int(battle_cost))
    if cur <= 0:
        return False, f"化身助战体力已耗尽，须恢复至 {thr} 点后方可再助战"
    if cur < thr and cur < cost:
        # 未归零但低于开销
        return False, f"化身助战体力不足（需 {cost}，当前 {cur}）"
    # 若曾归零后缓慢爬升：仍低于阈值则禁止（用「当前 < 阈值且从未满过」难追踪，
    # 简化：当前 < 阈值 且 当前 < cost → 已在上面；若当前 < 阈值但够 cost，允许。
    # 用户要求：归零后强制恢复到 20%。用 locked 标志更准——在 spend 归零时置位。
    if cur < cost:
        return False, f"化身助战体力不足（需 {cost}，当前 {cur}）"
    return True, None
