"""
化身体力账本：恢复 / 日切 / 扣费纯计算；仅在数值变化时写回 ORM。

降低大厅 enrich 等高频路径的无意义 dirty flush。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.avatar_capability import AvatarCapabilityIndex
from app.domain.avatar_rules import (
    apply_stamina_recovery,
    check_action_cost,
    sync_daily_actions,
)


@dataclass(frozen=True)
class StaminaSnapshot:
    """体力面板只读快照。"""

    stamina: int
    stamina_cap: int
    daily_actions_used: int
    daily_action_cap: int
    daily_actions_remaining: int
    recovery_summary: str
    recovery_per_hour: float

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 字典。"""
        return {
            "stamina": self.stamina,
            "stamina_cap": self.stamina_cap,
            "daily_actions_used": self.daily_actions_used,
            "daily_action_cap": self.daily_action_cap,
            "daily_actions_remaining": self.daily_actions_remaining,
            "recovery_summary": self.recovery_summary,
            "recovery_per_hour": self.recovery_per_hour,
        }


@dataclass(frozen=True)
class StaminaTickResult:
    """一次恢复/日切演算结果。"""

    snapshot: StaminaSnapshot
    stamina: int
    daily_actions_used: int
    daily_actions_day: str
    stamina_recovered_at: datetime
    dirty: bool


class AvatarStaminaLedger:
    """
    化身体力领域服务（无会话）。

    由 ``AvatarCapabilityIndex`` 提供上限与恢复参数。
    """

    def __init__(self, capability: AvatarCapabilityIndex) -> None:
        """
        参数:
            capability: 预计算能力索引。
        """
        self._cap = capability

    def tick(
        self,
        *,
        character_major: str,
        stamina: int,
        daily_actions_used: int,
        daily_actions_day: str | None,
        stamina_recovered_at: datetime | None,
        now: datetime,
        bootstrap_if_empty: bool = True,
    ) -> StaminaTickResult:
        """
        应用恢复与日切；``dirty`` 表示 ORM 字段需要写回。

        参数:
            bootstrap_if_empty: 首次启用（无锚点且体力 0）时灌满上限。
        """
        cap = self._cap.stamina_cap(character_major)
        stamp = now
        cur = int(stamina)
        anchor = stamina_recovered_at
        if bootstrap_if_empty and anchor is None and cur == 0 and cap > 0:
            cur = cap
            anchor = stamp

        new_stamina, new_anchor = apply_stamina_recovery(
            cur,
            cap=cap,
            last_recovery_at=anchor,
            now=stamp,
            per_hour=self._cap.stamina_recovery_per_hour,
        )
        used, day_key, remaining = sync_daily_actions(
            used=int(daily_actions_used),
            day_key=daily_actions_day or None,
            now=stamp,
            daily_cap=self._cap.stamina_daily_cap,
        )
        dirty = (
            new_stamina != int(stamina)
            or used != int(daily_actions_used)
            or day_key != (daily_actions_day or "")
            or new_anchor != stamina_recovered_at
        )
        snap = StaminaSnapshot(
            stamina=new_stamina,
            stamina_cap=cap,
            daily_actions_used=used,
            daily_action_cap=self._cap.stamina_daily_cap,
            daily_actions_remaining=remaining,
            recovery_summary=self._cap.stamina_recovery_summary,
            recovery_per_hour=self._cap.stamina_recovery_per_hour,
        )
        return StaminaTickResult(
            snapshot=snap,
            stamina=new_stamina,
            daily_actions_used=used,
            daily_actions_day=day_key,
            stamina_recovered_at=new_anchor,
            dirty=dirty,
        )

    def spend(
        self,
        *,
        character_major: str,
        stamina: int,
        daily_actions_used: int,
        daily_actions_day: str | None,
        stamina_recovered_at: datetime | None,
        action_key: str,
        now: datetime,
    ) -> tuple[StaminaTickResult, int | None, str]:
        """
        先 tick 再扣行动；失败返回 (tick结果, error_code, message)。

        成功时 ``dirty`` 恒为 True（若 cost>0 或 tick 已脏）。
        """
        tick = self.tick(
            character_major=character_major,
            stamina=stamina,
            daily_actions_used=daily_actions_used,
            daily_actions_day=daily_actions_day,
            stamina_recovered_at=stamina_recovered_at,
            now=now,
        )
        cost = self._cap.action_cost(action_key)
        ok, code, msg = check_action_cost(
            stamina=tick.snapshot.stamina,
            daily_remaining=tick.snapshot.daily_actions_remaining,
            cost=cost,
        )
        if not ok:
            return tick, code, msg
        if cost <= 0:
            return tick, None, ""
        new_stamina = tick.stamina - cost
        new_used = tick.daily_actions_used + 1
        remaining = max(0, self._cap.stamina_daily_cap - new_used)
        snap = StaminaSnapshot(
            stamina=new_stamina,
            stamina_cap=tick.snapshot.stamina_cap,
            daily_actions_used=new_used,
            daily_action_cap=self._cap.stamina_daily_cap,
            daily_actions_remaining=remaining,
            recovery_summary=self._cap.stamina_recovery_summary,
            recovery_per_hour=self._cap.stamina_recovery_per_hour,
        )
        return (
            StaminaTickResult(
                snapshot=snap,
                stamina=new_stamina,
                daily_actions_used=new_used,
                daily_actions_day=tick.daily_actions_day,
                stamina_recovered_at=tick.stamina_recovered_at,
                dirty=True,
            ),
            None,
            "",
        )
