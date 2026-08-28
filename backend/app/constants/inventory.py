"""背包 item_type / 四页 / 占用 / 丹药效果协议常量。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from app.constants.technique import (
    ELEMENT_DARK,
    ELEMENT_EARTH,
    ELEMENT_FIRE,
    ELEMENT_METAL,
    ELEMENT_THUNDER,
    ELEMENT_WATER,
    ELEMENT_WIND,
    ELEMENT_WOOD,
    element_view,
)


class ItemType(StrEnum):
    """inventory.yaml / InventoryItem.item_type。"""

    MATERIAL = "material"  # 材料
    CONSUMABLE = "consumable"  # 消耗品/丹药
    TALISMAN = "talisman"  # 符箓
    PUPPET = "puppet"  # 傀儡成品
    SKILL_BOOK = "skill_book"  # 技能书
    PET_EGG = "pet_egg"  # 灵兽蛋
    EQUIPMENT = "equipment"  # 装备
    MANUAL = "manual"  # 秘籍（图纸/丹方/功法书）
    PET = "pet"  # 孵化后的灵宠（背包面）


class ManualKind(StrEnum):
    """``item_type=manual`` 的细类（不是第三套背包大类）。"""

    FORGE_BLUEPRINT = "forge_blueprint"  # 锻造图纸
    TALISMAN_BLUEPRINT = "talisman_blueprint"  # 符箓图纸
    ALCHEMY_FORMULA = "alchemy_formula"  # 丹方
    PUPPET_BLUEPRINT = "puppet_blueprint"  # 傀儡图纸
    FORMATION_BLUEPRINT = "formation_blueprint"  # 阵盘图纸
    TECHNIQUE = "technique"  # 功法秘籍
    SKILL_BOOK = "skill_book"  # 技能书（可与 skill_book 大类并存）


class BagTab(StrEnum):
    """背包四页（机读；避免与 item_type=equipment 撞名）。"""

    GEAR = "gear"  # 装备页
    ELIXIR = "elixir"  # 丹药页
    MATERIAL = "material"  # 材料页
    MANUAL = "manual"  # 秘籍页


class Occupancy(StrEnum):
    """占位不迁格：槽/编成只是指针。"""

    NONE = "none"  # 闲置
    EQUIPPED = "equipped"  # 已装备
    DEPLOYED = "deployed"  # 已上阵


class UseEffectKind(StrEnum):
    """消耗品 use_effect.kind 白名单（只许追加）。"""

    STAMINA = "stamina"  # 恢复体力
    ATTR_MOD = "attr_mod"  # 时效改 ATTR
    IDLE_MOD = "idle_mod"  # 时效挂机乘区
    DICE_MOD = "dice_mod"  # 时效骰子区间
    GRANT = "grant"  # Ability grants
    PET_SKILL_BOOK = "pet_skill_book"  # 技能书专管线
    TECH_CARD_BLANK = "tech_card_blank"  # 空白卡 → 类型卡
    TECH_CARD_OPEN_TYPE = "tech_card_open_type"  # 类型卡 → 正式卡
    TECH_MANUAL_LEARN = "tech_manual_learn"  # 功法秘籍学习


class DurationClock(StrEnum):
    """丹药时效时钟（只许追加）。"""

    WALL = "wall"  # 现实秒
    BATTLE = "battle"  # 有战报的场次
    ROUND = "round"  # 自走棋回合


ITEM_TYPE_PUPPET: str = ItemType.PUPPET  # 傀儡物品类型
ITEM_TYPE_EQUIPMENT: str = ItemType.EQUIPMENT  # 装备物品类型

# item_type → 背包页
BAG_TAB_BY_ITEM_TYPE: Final[dict[str, str]] = {
    ItemType.EQUIPMENT: BagTab.GEAR,
    ItemType.PUPPET: BagTab.GEAR,
    ItemType.PET: BagTab.GEAR,
    ItemType.PET_EGG: BagTab.GEAR,
    ItemType.CONSUMABLE: BagTab.ELIXIR,
    ItemType.TALISMAN: BagTab.ELIXIR,
    ItemType.MATERIAL: BagTab.MATERIAL,
    ItemType.MANUAL: BagTab.MANUAL,
    ItemType.SKILL_BOOK: BagTab.MANUAL,
}

OCCUPANCY_LABELS_ZH: Final[dict[str, str]] = {
    Occupancy.NONE: "",
    Occupancy.EQUIPPED: "已装备",
    Occupancy.DEPLOYED: "已上阵",
}

BAG_TAB_LABELS_ZH: Final[dict[str, str]] = {
    BagTab.GEAR: "装备",
    BagTab.ELIXIR: "丹药",
    BagTab.MATERIAL: "材料",
    BagTab.MANUAL: "秘籍",
}

# 占用中禁止使用 / 非法 use_effect（M8 40200+）
ERR_ITEM_OCCUPIED: Final[int] = 40213  # 占用中不可使用/交易/换袋
ERR_ITEM_USE_EFFECT: Final[int] = 40214  # use_effect 白名单或时钟不合法
ERR_BLUEPRINT_TYPE_MISMATCH: Final[int] = 40209  # 图纸 manual_kind 与工坊分支不匹配

# 消耗品效果中文（玩家悬停 / 工坊配方）
USE_EFFECT_KIND_LABEL_ZH: Final[dict[str, str]] = {
    UseEffectKind.STAMINA: "恢复体力",
    UseEffectKind.ATTR_MOD: "属性修正",
    UseEffectKind.IDLE_MOD: "挂机修正",
    UseEffectKind.DICE_MOD: "骰子修正",
    UseEffectKind.GRANT: "授予能力",
    UseEffectKind.PET_SKILL_BOOK: "灵宠技能书",
    UseEffectKind.TECH_CARD_BLANK: "功法空白卡",
    UseEffectKind.TECH_CARD_OPEN_TYPE: "功法类型卡",
    UseEffectKind.TECH_MANUAL_LEARN: "功法秘籍",
}

INSTANT_USE_KINDS: Final[frozenset[str]] = frozenset({UseEffectKind.STAMINA})

# 工坊成品单一属性（同属性灵根后续可额外收益；本版只展示）
INSPECT_ELEMENT_IDS: Final[frozenset[str]] = frozenset(
    {
        ELEMENT_METAL,
        ELEMENT_WOOD,
        ELEMENT_WATER,
        ELEMENT_FIRE,
        ELEMENT_EARTH,
        ELEMENT_WIND,
        ELEMENT_THUNDER,
        ELEMENT_DARK,
    },
)
INSPECT_REALM_NONE_ZH: Final[str] = "无"  # 无境界门槛时的展示


def normalize_inspect_element(raw: Any) -> str | None:
    """Accept one of 金木水火土风雷暗; unknown / empty → None."""
    key = str(raw or "").strip()
    if key in INSPECT_ELEMENT_IDS:
        return key
    return None


def inspect_element_view(raw: Any) -> dict[str, str] | None:
    """Public chip for recipe hover, or None if the item has no element."""
    key = normalize_inspect_element(raw)
    if key is None:
        return None
    return element_view(key)


def bag_tab_for(item_type: str) -> str:
    """Map item_type to bag_tab; unknown types stay on the material tab."""
    return BAG_TAB_BY_ITEM_TYPE.get(str(item_type), BagTab.MATERIAL)
