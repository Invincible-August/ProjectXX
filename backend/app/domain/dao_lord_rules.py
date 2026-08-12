"""
道主资格、时段、冷却与更替合法性纯规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence


@dataclass(frozen=True)
class DaoLordWindowDef:
    """挑战开窗定义。"""

    start_hour: int
    end_hour: int
    tz: str
    label_zh: str
    weekday: int | None = None  # 0=Mon … 6=Sun；None=每日


@dataclass(frozen=True)
class DaoLordRules:
    """道主门槛与冷却。"""

    claim_min_level: int
    challenge_min_level: int
    win_cooldown_seconds: int
    lose_cooldown_seconds: int
    abort_cooldown_seconds: int
    reconnect_grace_seconds: int
    missing_snapshot_policy: str
    privileges_default: dict[str, Any]
    windows: tuple[DaoLordWindowDef, ...]
    single_challenge_per_dao: bool


def is_window_open(windows: Sequence[DaoLordWindowDef], *, now: datetime) -> tuple[bool, str]:
    """
    判断 ``now`` 是否落在任一开窗内。

    Args:
        windows: 开窗列表。
        now: 当前时刻（建议 UTC aware）。

    Returns:
        (open, label_zh)。
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    utc = now.astimezone(timezone.utc)
    hour = utc.hour + utc.minute / 60.0
    weekday = utc.weekday()
    for w in windows:
        if w.weekday is not None and int(w.weekday) != weekday:
            continue
        start = float(w.start_hour)
        end = float(w.end_hour)
        # end==24 表示到日末
        if end >= 24 and start <= hour < 24:
            return True, w.label_zh
        if start <= hour < end:
            return True, w.label_zh
    label = windows[0].label_zh if windows else "未配置开窗"
    return False, label


def can_claim(
    *,
    fate_dao_id: str | None,
    dao_level: int,
    claim_min_level: int,
    seat_occupied: bool,
) -> tuple[bool, str | None]:
    """
    空位自动就任资格（无需手动夺位；有主则须挑战）。

    Returns:
        (ok, block_reason_zh)。
    """
    if seat_occupied:
        return False, "该道已有道主，请走挑战更替"
    if not fate_dao_id:
        return False, "须先开辟本命大道"
    if int(dao_level) < int(claim_min_level):
        return False, f"道等级须达到 {claim_min_level}（空位达标后自动就任）"
    return True, None


def can_challenge(
    *,
    fate_dao_id: str | None,
    target_dao_id: str,
    dao_level: int,
    challenge_min_level: int,
    is_self_lord: bool,
    cooldown_until: datetime | None,
    now: datetime,
    window_open: bool,
    seat_occupied: bool,
) -> tuple[bool, str | None]:
    """
    挑战资格（不含快照存在性）。

    Returns:
        (ok, block_reason_zh)。
    """
    if not window_open:
        return False, "非挑战时段"
    if not seat_occupied:
        return False, "该道尚无道主，请先夺位"
    if is_self_lord:
        return False, "不可挑战自己"
    if not fate_dao_id or fate_dao_id != target_dao_id:
        return False, "本命道须与目标道主之道路径相同"
    if int(dao_level) < int(challenge_min_level):
        return False, f"道等级须达到 {challenge_min_level}"
    if cooldown_until is not None:
        if cooldown_until.tzinfo is None:
            cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if now < cooldown_until:
            return False, "挑战冷却中"
    return True, None
