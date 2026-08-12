"""
UTC 时间工具：全站唯一入口，避免各 service 重复实现。

所有业务层时间比较与序列化应优先使用本模块。
"""

from __future__ import annotations

from datetime import datetime, timezone


def now_utc(now: datetime | None = None) -> datetime:
    """
    返回 aware UTC 时刻。

    Args:
        now: 可选冻结时间；为 None 时取当前 UTC。

    Returns:
        datetime: tzinfo=UTC 的时刻。
    """
    value = now if now is not None else datetime.now(timezone.utc)
    return ensure_aware_utc(value)


def ensure_aware_utc(value: datetime) -> datetime:
    """
    将 naive datetime 视为 UTC，或将 aware 时刻换算为 UTC。

    Args:
        value: 任意 datetime。

    Returns:
        datetime: aware UTC。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_iso(value: datetime) -> str:
    """
    将 datetime 格式化为 ISO 8601 UTC 字符串（以 Z 结尾）。

    Args:
        value: 数据库或业务中的时间戳。

    Returns:
        str: 如 ``2026-07-28T09:00:00Z``。
    """
    aware = ensure_aware_utc(value)
    return aware.isoformat().replace("+00:00", "Z")
