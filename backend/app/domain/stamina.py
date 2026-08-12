"""
体力惰性恢复纯计算（M3战斗成型设计.md §12.9 · D10）。

与挂机同款 lazy 模式：不引入定时器，任何读取时按流逝时间结算。
体力值以「毫点」（1 点 = 1000 毫点）整数存储换算，避免浮点漂移；
对外读数与扣减均以整点为单位。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StaminaReading:
    """一次惰性结算后的体力读数。"""

    # 当前整点体力（向下取整后的可用值）
    current: int
    # 体力上限
    cap: int
    # 距离恢复下一整点还需的秒数（已满时为 0）
    next_point_in_seconds: int
    # 结算后的存储值（整点；回写用）
    stored_value: int


def settle_stamina(
    stored_value: int,
    stored_at: datetime,
    now: datetime,
    *,
    cap: int,
    regen_per_minute: float,
) -> StaminaReading:
    """
    惰性结算体力：``current = min(cap, stored + elapsed_minutes × regen)``。

    参数:
        stored_value: 上次结算时的体力整点值。
        stored_at: 上次结算时刻（UTC aware）。
        now: 当前时刻（UTC aware）。
        cap: 体力上限。
        regen_per_minute: 每分钟恢复点数。

    返回:
        StaminaReading: 当前整点体力、下一点恢复倒计时、回写值。
    """
    elapsed_seconds = max(0.0, (now - stored_at).total_seconds())
    regen_per_second = regen_per_minute / 60.0
    # 已恢复的「精确」体力（浮点仅用于本次计算，不入库）
    exact = min(float(cap), float(stored_value) + elapsed_seconds * regen_per_second)
    current = int(exact)

    if current >= cap or regen_per_second <= 0:
        next_seconds = 0
    else:
        # 距下一整点的欠缺量 → 秒
        deficit = (current + 1) - exact
        next_seconds = max(1, int(deficit / regen_per_second + 0.999))

    return StaminaReading(
        current=current,
        cap=cap,
        next_point_in_seconds=next_seconds,
        stored_value=current,
    )
