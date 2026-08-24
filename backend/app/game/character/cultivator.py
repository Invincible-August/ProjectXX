"""修士子基类：可挂机、分配、突破；后台按本类渲染境界栏。"""

from __future__ import annotations

from abc import abstractmethod

from app.game.character.base import Character


class CultivatorCharacter(Character):
    """
    修士行动体（玩家 / NPC / 化身）。

    后台管理按 ``isinstance(..., CultivatorCharacter)`` 决定是否展示境界、
    分配与突破字段。道主境 / 轮回境默认关闭，由叶子类按身份打开。
    """

    kind = "cultivator"

    @abstractmethod
    def get_major_realm(self) -> str:
        """当前大境界 id（锻体/金丹/真仙等常规链）。"""

    @abstractmethod
    def get_realm_stage(self) -> int:
        """当前小境编号。"""

    @abstractmethod
    def get_realm_progress(self) -> int:
        """当前境界进度（修为池投入）。"""

    def can_enter_dao_lordship(self) -> bool:
        """是否允许进入道主境（身份，非常规修为台阶）。默认否。"""
        return False

    def can_enter_reincarnation_realm(self) -> bool:
        """是否允许作为轮回外环主体。默认否。"""
        return False
