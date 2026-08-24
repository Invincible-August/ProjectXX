"""
开战种子：养成 Character → 可序列化 dict，供 simulate_battle 消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BattleUnitSeed:
    """
    单棋子开战快照（与现行 setup.units[] 字段兼容）。

    Attributes:
        unit_uid: 棋盘唯一 id。
        unit_kind: main/avatar/pet/puppet/monster/npc/boss。
        ref_id: 持有物/模板引用。
        side: attacker/defender。
        x/y: 坐标。
        stats: 引擎核心数值（hp/phys_atk/speed/mp…）。
        meta: 扩展（ability 快照、flags 等）。
    """

    unit_uid: str
    unit_kind: str
    side: str
    x: int
    y: int
    ref_id: int | str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_setup_unit(self) -> dict[str, Any]:
        """
        转为现行 autochess setup 单元 dict。

        Returns:
            dict[str, Any]: 可并入 setup['units']。
        """
        payload: dict[str, Any] = {
            "unit_uid": self.unit_uid,
            "unit_kind": self.unit_kind,
            "side": self.side,
            "x": self.x,
            "y": self.y,
            **self.stats,
        }
        if self.ref_id is not None:
            payload["ref_id"] = self.ref_id
        if self.meta:
            payload["meta"] = self.meta
        return payload
