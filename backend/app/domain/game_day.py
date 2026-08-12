"""
历法游戏日纯函数（宗门晋升次日通过等）。

游戏日 = floor((now - epoch).total_seconds() / (slot_seconds * 6))。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.calendar_rules import parse_epoch_utc


def game_day_number(
    now: datetime,
    *,
    epoch: datetime | str,
    slot_seconds: int,
) -> int:
    """
    计算当前游戏日序号（从 0 起）。

    Args:
        now: 当前 UTC 时间。
        epoch: 历法纪元。
        slot_seconds: 一时辰墙钟秒。

    Returns:
        int: 游戏日号（非负）。

    Raises:
        ValueError: slot_seconds 非正。
    """
    if slot_seconds <= 0:
        raise ValueError("slot_seconds must be positive")
    epoch_dt = parse_epoch_utc(epoch)
    now_aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    delta = (now_aware.astimezone(timezone.utc) - epoch_dt).total_seconds()
    day_seconds = float(slot_seconds) * 6.0
    if delta < 0:
        return 0
    return int(delta // day_seconds)
