"""
挂机跨时辰/天气切段纯函数（M5-D11）。

按 tick 完成时刻的环境键分组；同 (shichen, weather) 合并。
天气历史在无重放时由调用方 ``resolve_env`` 提供。

性能：调用方应用 ``memoize_env_resolve`` 或按槽位缓存的 resolver，
避免每个 tick 新建 Calendar/Weather 服务快照。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable


@dataclass(frozen=True)
class IdleEnvTickGroup:
    """Consecutive ticks sharing the same environment key."""

    shichen_id: str
    weather_id: str
    tick_count: int
    from_at: datetime
    to_at: datetime


def memoize_env_resolve(
    resolve_env: Callable[[datetime], tuple[str, str]],
    *,
    bucket_seconds: int = 1,
) -> Callable[[datetime], tuple[str, str]]:
    """
    Memoize env resolution by time bucket to cut repeated snapshot work.

    Args:
        resolve_env: Underlying ``(at) -> (shichen_id, weather_id)``.
        bucket_seconds: Floor ``at`` into this many seconds (use calendar
            ``slot_seconds`` when shichen only changes on slot boundaries).

    Returns:
        Callable: Cached resolver safe for one settle pass.
    """
    cache: dict[int, tuple[str, str]] = {}
    step = max(1, int(bucket_seconds))

    def _cached(at: datetime) -> tuple[str, str]:
        key = int(at.timestamp()) // step
        hit = cache.get(key)
        if hit is not None:
            return hit
        value = resolve_env(at)
        cache[key] = (str(value[0]), str(value[1]))
        return cache[key]

    return _cached


def group_ticks_by_env(
    last: datetime,
    max_ticks: int,
    tick_seconds: int,
    *,
    resolve_env: Callable[[datetime], tuple[str, str]],
    max_segments: int = 64,
) -> list[IdleEnvTickGroup]:
    """
    Group settle ticks by (shichen_id, weather_id) at each tick end time.

    Args:
        last: Settle anchor (tick-aligned preferred).
        max_ticks: Number of complete ticks in the window.
        tick_seconds: Seconds per idle tick.
        resolve_env: ``(at) -> (shichen_id, weather_id)``.
        max_segments: Soft cap; when exceeded, merge remaining into last group
            (keeps totals, coarsens breakdown — see design risk table).

    Returns:
        list[IdleEnvTickGroup]: Ordered groups covering ``max_ticks``.
    """
    if max_ticks <= 0 or tick_seconds <= 0:
        return []

    groups: list[IdleEnvTickGroup] = []
    current_key: tuple[str, str] | None = None
    current_count = 0
    current_from = last

    for index in range(1, max_ticks + 1):
        tick_end = last + timedelta(seconds=index * tick_seconds)
        shichen_id, weather_id = resolve_env(tick_end)
        key = (str(shichen_id), str(weather_id))
        if key != current_key:
            if current_count > 0 and current_key is not None:
                groups.append(
                    IdleEnvTickGroup(
                        shichen_id=current_key[0],
                        weather_id=current_key[1],
                        tick_count=current_count,
                        from_at=current_from,
                        to_at=last + timedelta(seconds=(index - 1) * tick_seconds),
                    ),
                )
                # 段数上限：后续 tick 并入最后一段（用新 key 仍并入，避免爆炸）
                if len(groups) >= max_segments:
                    remaining = max_ticks - (index - 1)
                    last_group = groups[-1]
                    groups[-1] = IdleEnvTickGroup(
                        shichen_id=last_group.shichen_id,
                        weather_id=last_group.weather_id,
                        tick_count=last_group.tick_count + remaining,
                        from_at=last_group.from_at,
                        to_at=last + timedelta(seconds=max_ticks * tick_seconds),
                    )
                    return groups
            current_key = key
            current_count = 1
            current_from = last + timedelta(seconds=(index - 1) * tick_seconds)
        else:
            current_count += 1

    if current_count > 0 and current_key is not None:
        groups.append(
            IdleEnvTickGroup(
                shichen_id=current_key[0],
                weather_id=current_key[1],
                tick_count=current_count,
                from_at=current_from,
                to_at=last + timedelta(seconds=max_ticks * tick_seconds),
            ),
        )
    return groups
