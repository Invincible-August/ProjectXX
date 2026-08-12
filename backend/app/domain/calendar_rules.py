"""
六时历法纯函数：权威 slot 计算（M5 D1）。

无副作用；时钟注入经 ``now`` / ``epoch`` / ``slot_seconds`` 参数。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence


@dataclass(frozen=True)
class ShichenSnapshot:
    """当前时辰快照（权威公式：slot = floor((now-epoch)/slot_seconds) % 6）。"""

    slot: int  # 时辰槽位 0～5
    shichen_id: str  # 时辰键：dawn/noon/afternoon/dusk/night/late_night
    next_at: datetime  # 下一时辰边界 UTC
    server_now: datetime  # 计算所用服务器当前 UTC
    label: str | None = None  # 展示名（清晨/正午/…）；无配置则为 None


def parse_epoch_utc(epoch_utc: str | datetime) -> datetime:
    """
    Parse calendar epoch into aware UTC datetime.

    Args:
        epoch_utc: ISO string (``Z`` or offset) or datetime.

    Returns:
        datetime: Aware UTC epoch.

    Raises:
        ValueError: When the string cannot be parsed.
    """
    if isinstance(epoch_utc, datetime):
        value = epoch_utc
    else:
        text = str(epoch_utc).strip().replace("Z", "+00:00")
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def current_shichen(
    now: datetime,
    epoch: datetime | str,
    slot_seconds: int = 60,
    shichen_order: Sequence[str] | None = None,
    labels: dict[str, str] | None = None,
) -> ShichenSnapshot:
    """
    Compute the authoritative current shichen from wall-clock formula.

    ``slot = floor((now - epoch).total_seconds() / slot_seconds) % 6``

    Args:
        now: Current UTC time (aware preferred).
        epoch: Calendar epoch.
        slot_seconds: Real seconds per shichen slot.
        shichen_order: Ordered list of six shichen ids.
        labels: Optional display names keyed by shichen id.

    Returns:
        ShichenSnapshot: Slot index, id, next boundary, and server now.

    Raises:
        ValueError: When ``slot_seconds`` is non-positive or order length != 6.
    """
    if slot_seconds <= 0:
        raise ValueError("slot_seconds must be positive")
    order = list(shichen_order) if shichen_order else [
        "dawn",
        "noon",
        "afternoon",
        "dusk",
        "night",
        "late_night",
    ]
    if len(order) != 6:
        raise ValueError("shichen_order must contain exactly 6 ids")

    epoch_aware = parse_epoch_utc(epoch)
    if now.tzinfo is None:
        now_aware = now.replace(tzinfo=timezone.utc)
    else:
        now_aware = now.astimezone(timezone.utc)

    elapsed = (now_aware - epoch_aware).total_seconds()
    # 负相位仍按模运算落到合法 slot，便于测假时钟
    slot_index = int(elapsed // slot_seconds)
    slot = slot_index % 6
    if slot < 0:
        slot += 6
    next_at = epoch_aware + timedelta(seconds=(slot_index + 1) * slot_seconds)
    shichen_id = order[slot]
    label = (labels or {}).get(shichen_id)
    return ShichenSnapshot(
        slot=slot,
        shichen_id=shichen_id,
        next_at=next_at,
        server_now=now_aware,
        label=label,
    )
