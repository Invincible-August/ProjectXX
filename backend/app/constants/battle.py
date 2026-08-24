"""战斗 / 布阵协议常量（棋子 kind、攻守方、UID 前缀）。"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class PieceKind(StrEnum):
    """布阵与开战 setup 中的 unit_kind / kind。"""

    MAIN = "main"  # 玩家本体
    AVATAR = "avatar"  # 化身（含客串）
    PET = "pet"  # 灵宠
    PUPPET = "puppet"  # 傀儡（真傀或试炼木傀）
    MONSTER = "monster"  # PVE 怪物
    NPC = "npc"  # NPC 战斗体
    BOSS = "boss"  # Boss
    PROP = "prop"  # 占位道具格（若启用）


# 下列别名便于业务 ``from app.constants.battle import PIECE_KIND_MAIN`` 式引用
PIECE_KIND_MAIN: str = PieceKind.MAIN  # 本体棋子 kind
PIECE_KIND_AVATAR: str = PieceKind.AVATAR  # 化身棋子 kind
PIECE_KIND_PET: str = PieceKind.PET  # 灵宠棋子 kind
PIECE_KIND_PUPPET: str = PieceKind.PUPPET  # 傀儡棋子 kind
PIECE_KIND_MONSTER: str = PieceKind.MONSTER  # 怪物棋子 kind


class BattleSide(IntEnum):
    """自走棋引擎 side：0 攻方 / 1 守方。"""

    ATTACKER = 0  # 进攻方
    DEFENDER = 1  # 防守方（含 PVE 怪侧）


BATTLE_SIDE_ATTACKER: int = int(BattleSide.ATTACKER)  # 进攻方 side 数值
BATTLE_SIDE_DEFENDER: int = int(BattleSide.DEFENDER)  # 防守方 side 数值

ATTACKER_UID_PREFIX: str = "a_"  # 进攻方棋子 uid 前缀（接 unit_uid）
DEFENDER_UID_PREFIX: str = "d_"  # 防守方棋子 uid 前缀

EVENT_TYPE_ITEM_TRIGGER: str = "item_trigger"  # 符箓/道具触发（战报中文出口）
TRIAL_PUPPET_UID_PREFIX: str = "puppet_"  # 试炼木傀 unit_uid 前缀（后接序号）

MIN_COMBAT_STAT: int = 1  # 派生棋子 atk/hp 折算后的下限（至少 1）

DEFAULT_FALLBACK_SPEED: int = 10  # 缺省速度（与 combat_attrs.defaults.speed 对齐的工程回退）

DICE_PURPOSE_COMBAT_DAMAGE: str = "combat_damage"  # 修为骰用途：战斗伤害/先攻区间
