"""
挂机领域：结算摘要、离线 pending 值对象、收益计算纯函数。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.time_utils import to_utc_iso

# 可产出资源的挂机方向
PRODUCTIVE_DIRECTIONS = frozenset({"spirit", "body", "crafting"})


@dataclass
class SettleResult:
    """一次权威 settle 的摘要。"""

    stalled: bool  # 灵石不足导致本段停滞
    ticks: int  # 实际推进的 tick 数
    gained_cultivation: int = 0  # 本段修灵池增量
    gained_body: int = 0  # 本段炼体池增量
    gained_crafting: int = 0  # 本段制造业经验增量
    spent_spirit_stones: int = 0  # 本段消耗灵石
    advanced_only: bool = False  # True=仅推进锚点无产出（如状态非 normal）
    # M5-D11：跨时辰/天气切段明细（可空；短窗单段时仍可有一条）
    segments: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class IdleGainBreakdown:
    """按方向与灵石算出的 tick 收益分解。"""

    used: int  # 实际可用 tick（受灵石约束）
    gained_cultivation: int  # 修灵产出
    gained_body: int  # 炼体产出
    gained_crafting: int  # 制造业产出
    spent_stones: int  # 消耗灵石
    stalled: bool  # 因灵石不够跑满 max_ticks


class IdleGainCalculator:
    """
    挂机收益纯计算器（无 DB IO）。

    调用方负责传入方向速率与每 tick 灵石消耗。
    """

    @staticmethod
    def compute(
        *,
        status: str,
        direction: str,
        spirit_stones: int,
        max_ticks: int,
        gain_per_tick: int | None,
        stone_cost_per_tick: int,
    ) -> IdleGainBreakdown:
        """
        按方向与灵石计算 used ticks 与三向产出。

        Args:
            status: 角色状态（非 normal 零产出）。
            direction: 当前挂机方向。
            spirit_stones: 当前灵石。
            max_ticks: 时间片允许的最大 tick。
            gain_per_tick: 方向配置产出；None 表示方向未开放。
            stone_cost_per_tick: 每 tick 灵石消耗。

        Returns:
            IdleGainBreakdown: used / 三向产出 / 消耗 / 是否停滞。
        """
        if status != "normal" or direction not in PRODUCTIVE_DIRECTIONS:
            return IdleGainBreakdown(0, 0, 0, 0, 0, False)
        if gain_per_tick is None:
            return IdleGainBreakdown(0, 0, 0, 0, 0, False)

        # 灵石消耗为 0：不限灵石，按时间片满 tick 结算且不停滞
        if stone_cost_per_tick <= 0:
            used = max(0, int(max_ticks))
            gain = used * gain_per_tick
            return IdleGainBreakdown(
                used=used,
                gained_cultivation=gain if direction == "spirit" else 0,
                gained_body=gain if direction == "body" else 0,
                gained_crafting=gain if direction == "crafting" else 0,
                spent_stones=0,
                stalled=False,
            )

        affordable = int(spirit_stones) // stone_cost_per_tick
        used = min(max_ticks, affordable)
        stalled = affordable < max_ticks
        gain = used * gain_per_tick
        return IdleGainBreakdown(
            used=used,
            gained_cultivation=gain if direction == "spirit" else 0,
            gained_body=gain if direction == "body" else 0,
            gained_crafting=gain if direction == "crafting" else 0,
            spent_stones=used * stone_cost_per_tick,
            stalled=stalled,
        )


class OfflinePending:
    """
    离线 pending JSON 的解析与构造。

    值对象本身不写库；由 IdleService 负责持久化。
    """

    @staticmethod
    def parse_raw(raw: str | None) -> dict[str, Any] | None:
        """
        解析 ``pending_offline_json`` 原始字符串。

        参数:
            raw: JSON 文本或 None。

        返回:
            pending 明细或 None。
        """
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def build_payload(
        *,
        last: datetime,
        used: int,
        tick: int,
        cap_hours: float,
        wall_elapsed: float,
        capped: bool,
        direction: str,
        gained_cultivation: int,
        gained_body: int,
        gained_crafting: int,
        spent_stones: int,
        stalled: bool,
        main_gains: dict[str, Any] | None = None,
        avatar_gains: dict[str, Any] | None = None,
        craft_completed: list[int] | None = None,
        segments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        构造 pending_offline_json 结构。

        M4 扩展：main_gains / avatar_gains / craft_completed 分列明细。
        M5-D11：segments 为跨时辰/天气切段乘区明细。
        """
        payload = {
            "from": to_utc_iso(last),
            "to_effective": to_utc_iso(last + timedelta(seconds=used * tick)),
            "cap_hours": cap_hours,
            "capped": capped,
            "wall_elapsed_seconds": int(wall_elapsed),
            "settled_ticks": used,
            "direction": direction,
            "gained_cultivation": gained_cultivation,
            "gained_body": gained_body,
            "gained_crafting": gained_crafting,
            "spent_spirit_stones": spent_stones,
            "is_stalled": stalled,
        }
        if main_gains is not None:
            payload["main_gains"] = main_gains
        if avatar_gains is not None:
            payload["avatar_gains"] = avatar_gains
        if craft_completed is not None:
            payload["craft_completed"] = craft_completed
        if segments is not None:
            payload["segments"] = segments
        return payload

    @staticmethod
    def to_json(pending: dict[str, Any]) -> str:
        """序列化为写入 ORM 的 JSON 文本。"""
        return json.dumps(pending, ensure_ascii=False)
