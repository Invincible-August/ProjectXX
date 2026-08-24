"""灵宠 / 傀儡：消耗宿主神识的随从基类；神识消耗切面亦可挂在化身修士上。"""

from __future__ import annotations

from app.constants.battle import PieceKind
from app.game.character.base import Character


def default_divine_sense_cost(kind: str, *, ephemeral: bool = False) -> int:
    """
    读取 YAML 默认神识消耗；试炼木傀等 ephemeral 为 0。

    Args:
        kind: avatar / pet / puppet。
        ephemeral: True 时不占神识（试炼木傀）。

    Returns:
        非负整数消耗。
    """
    if ephemeral:
        return 0
    from app.services.realm_config import get_game_config

    cfg = get_game_config().divine_sense
    if kind == PieceKind.AVATAR:
        return max(0, int(cfg.cost_avatar))
    if kind == PieceKind.PET:
        return max(0, int(cfg.cost_pet))
    if kind == PieceKind.PUPPET:
        return max(0, int(cfg.cost_puppet))
    return 0


class DivineSenseConsumer:
    """
    上阵消耗宿主神识的切面。

    化身是修士（``CultivatorCharacter``）但仍占本体神识，故与灵宠/傀儡共用本切面，
    **不**再挂到 ``SenseMinionCharacter`` 上。后台按本切面渲染「神识占用」列。
    """

    def _init_sense_cost(self, divine_sense_cost: int) -> None:
        """由化身 / 灵宠 / 傀儡构造器写入消耗。"""
        self._divine_sense_cost = max(0, int(divine_sense_cost))

    @property
    def divine_sense_cost(self) -> int:
        """上阵时占用宿主的神识值。"""
        return max(0, int(getattr(self, "_divine_sense_cost", 0) or 0))


class SenseMinionCharacter(Character, DivineSenseConsumer):
    """
    灵宠、傀儡的子基类（非修士）。

    基础属性 ``divine_sense_cost`` 计入宿主 ``PlayerNpcCharacter`` 的神识分子。
    """

    kind = "sense_minion"
