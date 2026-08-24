"""玩家与 NPC 共用子基类：修士 + 神识池。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from app.game.character.cultivator import CultivatorCharacter

if TYPE_CHECKING:
    from app.game.character.minion import DivineSenseConsumer


class PlayerNpcCharacter(CultivatorCharacter):
    """
    玩家 / NPC 子基类。

    神识容量与占用只存在于此层；化身、灵宠、傀儡、怪物不继承本类。
    分子（占用）= 上阵化身/灵宠/傀儡的 ``divine_sense_cost`` 之和。
    """

    kind = "player_npc"

    def _init_sense(
        self,
        *,
        divine_sense_capacity: int = 0,
        divine_sense_load: int = 0,
    ) -> None:
        """初始化神识池（由 Player / Npc 构造器调用）。"""
        self._sense_capacity = max(0, int(divine_sense_capacity))
        self._sense_load = max(0, int(divine_sense_load))
        self._deployed_minions: list[DivineSenseConsumer] = []
        self._spirit_root_tags: list[str] = []

    def set_spirit_root_tags(self, tags: list[str] | None) -> None:
        """注入灵根 id 列表（玩家读 ORM；NPC 读模板）。"""
        self._spirit_root_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

    @property
    def spirit_root_tags(self) -> list[str]:
        """灵根机读 id。"""
        return list(getattr(self, "_spirit_root_tags", []) or [])

    def set_divine_sense(self, *, capacity: int, load: int | None = None) -> None:
        """由服务层注入容量；load 缺省则保留已绑定随从合计。"""
        self._sense_capacity = max(0, int(capacity))
        if load is not None:
            self._sense_load = max(0, int(load))

    def bind_deployed_minions(self, minions: Sequence[DivineSenseConsumer]) -> None:
        """绑定上阵消耗神识的单位并重算占用。"""
        self._deployed_minions = list(minions)
        self._sense_load = sum(int(m.divine_sense_cost) for m in self._deployed_minions)

    @property
    def divine_sense_capacity(self) -> int:
        """自身神识总量（分母）。"""
        return int(getattr(self, "_sense_capacity", 0) or 0)

    @property
    def divine_sense_load(self) -> int:
        """已使用神识（分子：上阵化身/灵宠/傀儡消耗合计）。"""
        return int(getattr(self, "_sense_load", 0) or 0)

    @property
    def deployed_minions(self) -> list[DivineSenseConsumer]:
        """当前计入神识占用的上阵单位。"""
        return list(getattr(self, "_deployed_minions", []) or [])
