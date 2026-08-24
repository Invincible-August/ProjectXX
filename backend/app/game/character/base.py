"""
可参战行动体抽象基类（UE 式契约）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from app.game.ability.grant import GrantSource
    from app.game.battle.seed import BattleUnitSeed


class Character(ABC):
    """
    可参战行动体基类：子类必须实现身份、属性、授予与开战种子。

    生命值 / 法力值是全体行动体的基础属性，从 ``build_base_attrs`` 的 combat.final 读取。
    玩家专属（道主/交易等）不得写入本 ABC；神识池只属于 ``PlayerNpcCharacter``；
    修士契约见 ``CultivatorCharacter``。
    """

    kind: str = "character"

    @abstractmethod
    def get_entity_kind(self) -> str:
        """ATTR ``entity_kind``（player/avatar/pet/puppet/…）。"""

    @abstractmethod
    def get_piece_kind(self) -> str:
        """布阵 ``unit_kind``（main/avatar/pet/puppet/monster/…）。"""

    @abstractmethod
    def build_base_attrs(self) -> dict[str, Any]:
        """
        无临时战斗 Buff 的属性块（可含 combat/life 或扁平 stats）。

        存量期可直接返回服务层 ``build_combat_attrs`` / 面板 dict。
        """

    @abstractmethod
    def iter_grant_sources(self) -> Iterable[GrantSource]:
        """装备/天赋/模板被动等授予源（可空迭代）。"""

    @abstractmethod
    def on_battle_enter(
        self,
        *,
        unit_uid: str,
        side: str,
        x: int,
        y: int,
        ctx: dict[str, Any] | None = None,
    ) -> BattleUnitSeed:
        """养成/模板 → 开战种子。"""

    @abstractmethod
    def can_be_deployed(self) -> bool:
        """当前是否允许进入 bench/布阵。"""

    def _combat_final(self) -> dict[str, Any]:
        """读取 ``build_base_attrs`` 中的 combat.final（兼容扁平 stats）。"""
        block = self.build_base_attrs() or {}
        combat = block.get("combat")
        if isinstance(combat, dict):
            final = combat.get("final")
            if isinstance(final, dict):
                return final
        if any(key in block for key in ("hp", "mp", "phys_atk", "atk", "speed")):
            return block
        return {}

    def battle_core_stats(self) -> dict[str, int]:
        """开战核心四键（hp / phys_atk / speed / mp）。"""
        final = self._combat_final()
        return {
            "hp": max(1, int(final.get("hp") or 1)),
            "phys_atk": int(self.phys_atk),
            "speed": int(final.get("speed") or 10),
            "mp": max(0, int(self.mp)),
        }

    @property
    def hp(self) -> int:
        """当前有效生命上限（无副作用；读缓存块）。"""
        return max(1, int(self._combat_final().get("hp") or 1))

    @property
    def mp(self) -> int:
        """当前有效法力上限（基础属性；无副作用）。"""
        return max(0, int(self._combat_final().get("mp") or 0))

    @property
    def phys_atk(self) -> int:
        """当前有效物攻（无副作用；读缓存块）。"""
        final = self._combat_final()
        if "phys_atk" in final:
            return int(final["phys_atk"])
        if "atk" in final:
            return int(final["atk"])
        return 0

    @property
    def display_name(self) -> str:
        """面板/战报展示名；子类可覆盖。"""
        return self.kind
