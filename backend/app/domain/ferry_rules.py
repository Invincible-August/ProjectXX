"""
待引渡倒计时与自救合法性纯函数（M5 D8）。
"""

from __future__ import annotations

from datetime import datetime, timedelta


def compute_ferry_deadline(
    fallen_at: datetime,
    countdown_seconds: int,
) -> datetime:
    """
    Compute ferry deadline from fall moment.

    Args:
        fallen_at: UTC moment of fall.
        countdown_seconds: Configured countdown length.

    Returns:
        datetime: Deadline (aware if input is aware).
    """
    return fallen_at + timedelta(seconds=max(0, int(countdown_seconds)))


def is_ferry_timed_out(
    now: datetime,
    deadline: datetime | None,
) -> bool:
    """
    Return whether ferry countdown has expired.

    Args:
        now: Current UTC.
        deadline: Ferry deadline; None means not in ferry.

    Returns:
        bool: True when overdue.
    """
    if deadline is None:
        return False
    from app.core.time_utils import ensure_aware_utc

    return ensure_aware_utc(now) >= ensure_aware_utc(deadline)


def can_self_rescue(
    *,
    status: str,
    spirit_stones: int,
    cost: int,
    last_rescue_at: datetime | None,
    now: datetime,
    cooldown_seconds: int,
) -> tuple[bool, str, int]:
    """
    Validate self-rescue preconditions.

    Args:
        status: Character status.
        spirit_stones: Current stones.
        cost: Configured spirit stone cost.
        last_rescue_at: Last successful self-rescue (optional cooldown).
        now: Current UTC.
        cooldown_seconds: Cooldown length.

    Returns:
        tuple: ``(ok, reason, cooldown_remaining_seconds)``;
        reason empty when ok；cooldown_remaining 仅冷却未满时 >0。
    """
    if status != "awaiting_ferry":
        return False, "非待引渡状态", 0
    stones = int(spirit_stones)
    need = int(cost)
    if stones < need:
        return False, f"灵石不足（自救需 {need} 灵石，当前 {stones}）", 0
    if last_rescue_at is not None and cooldown_seconds > 0:
        from app.core.time_utils import ensure_aware_utc

        elapsed = (
            ensure_aware_utc(now) - ensure_aware_utc(last_rescue_at)
        ).total_seconds()
        remaining = int(cooldown_seconds) - int(elapsed)
        if remaining > 0:
            return False, f"自救冷却中（还需 {remaining} 秒，冷却共 {int(cooldown_seconds)} 秒）", remaining
    return True, "", 0
