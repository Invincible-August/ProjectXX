"""
Equipment slot and API error constants (M8 R0 · 17-zone loadout).
"""

from __future__ import annotations

from typing import Final

# Canonical pointer slots (15 gear + pet). Puppet is a loadout board, not a slot.
EQUIPMENT_SLOT_WEAPON_1: Final[str] = "weapon_1"
EQUIPMENT_SLOT_WEAPON_2: Final[str] = "weapon_2"
EQUIPMENT_SLOT_ARMOR_HEAD: Final[str] = "armor_head"
EQUIPMENT_SLOT_ARMOR_CHEST: Final[str] = "armor_chest"
EQUIPMENT_SLOT_ARMOR_LEGS: Final[str] = "armor_legs"
EQUIPMENT_SLOT_ARMOR_SHOES: Final[str] = "armor_shoes"
EQUIPMENT_SLOT_ARMOR_HANDS: Final[str] = "armor_hands"
EQUIPMENT_SLOT_ACCESSORY_1: Final[str] = "accessory_1"
EQUIPMENT_SLOT_ACCESSORY_2: Final[str] = "accessory_2"
EQUIPMENT_SLOT_RING_1: Final[str] = "ring_1"
EQUIPMENT_SLOT_RING_2: Final[str] = "ring_2"
EQUIPMENT_SLOT_FABAO_1: Final[str] = "fabao_1"
EQUIPMENT_SLOT_FABAO_2: Final[str] = "fabao_2"
EQUIPMENT_SLOT_NATAL_FABAO: Final[str] = "natal_fabao"
EQUIPMENT_SLOT_FUBAO: Final[str] = "fubao"
EQUIPMENT_SLOT_PET: Final[str] = "pet"

# Catalog kinds that occupy both weapon pointers with one inventory row
EQUIP_KIND_WEAPON_2H: Final[str] = "weapon_2h"
CATALOG_KIND_WEAPON_1H: Final[str] = "weapon_1h"  # 单手武器，主手或副手
CATALOG_KIND_WEAPON_ANY: Final[str] = "weapon_any"  # 任意武器格
CATALOG_KIND_ACCESSORY: Final[str] = "accessory"  # 项链或饰品
CATALOG_KIND_ACCESSORY_ANY: Final[str] = "accessory_any"
CATALOG_KIND_RING: Final[str] = "ring"  # 戒指一或戒指二
CATALOG_KIND_RING_ANY: Final[str] = "ring_any"
CATALOG_KIND_FABAO: Final[str] = "fabao"  # 法宝一或法宝二
CATALOG_KIND_LINGBAO: Final[str] = "lingbao"  # 灵宝，占用同法宝对槽
CATALOG_KIND_FABAO_ANY: Final[str] = "fabao_any"
CATALOG_KIND_PET: Final[str] = "pet"  # 灵宠硬顶槽

WEAPON_POINTER_SLOTS: Final[tuple[str, ...]] = (
    EQUIPMENT_SLOT_WEAPON_1,
    EQUIPMENT_SLOT_WEAPON_2,
)

# 化身不可穿：灵宠、符宝（傀儡/符箓走编成板，也不给化身）
AVATAR_FORBIDDEN_EQUIP_SLOTS: Final[frozenset[str]] = frozenset(
    {
        EQUIPMENT_SLOT_PET,
        EQUIPMENT_SLOT_FUBAO,
    },
)

# Live wear API / ORM slot ids (no puppet single-slot)
EQUIPMENT_SLOTS: Final[tuple[str, ...]] = (
    EQUIPMENT_SLOT_WEAPON_1,
    EQUIPMENT_SLOT_WEAPON_2,
    EQUIPMENT_SLOT_ARMOR_HEAD,
    EQUIPMENT_SLOT_ARMOR_CHEST,
    EQUIPMENT_SLOT_ARMOR_LEGS,
    EQUIPMENT_SLOT_ARMOR_SHOES,
    EQUIPMENT_SLOT_ARMOR_HANDS,
    EQUIPMENT_SLOT_ACCESSORY_1,
    EQUIPMENT_SLOT_ACCESSORY_2,
    EQUIPMENT_SLOT_RING_1,
    EQUIPMENT_SLOT_RING_2,
    EQUIPMENT_SLOT_FABAO_1,
    EQUIPMENT_SLOT_FABAO_2,
    EQUIPMENT_SLOT_NATAL_FABAO,
    EQUIPMENT_SLOT_FUBAO,
    EQUIPMENT_SLOT_PET,
)

EQUIPMENT_POINTER_SLOTS: Final[tuple[str, ...]] = EQUIPMENT_SLOTS

# 化身可穿指针槽（不含灵宠 / 符宝）
AVATAR_EQUIPMENT_SLOTS: Final[tuple[str, ...]] = tuple(
    slot for slot in EQUIPMENT_SLOTS if slot not in AVATAR_FORBIDDEN_EQUIP_SLOTS
)

# Legacy five-slot ids → canonical (one-time DB migrate / read old YAML)
LEGACY_EQUIPMENT_SLOT_WEAPON: Final[str] = "weapon"
LEGACY_EQUIPMENT_SLOT_ARMOR: Final[str] = "armor"
LEGACY_EQUIPMENT_SLOT_FABAO: Final[str] = "fabao"

EQUIPMENT_SLOT_ALIASES: Final[dict[str, str]] = {
    LEGACY_EQUIPMENT_SLOT_WEAPON: EQUIPMENT_SLOT_WEAPON_1,
    LEGACY_EQUIPMENT_SLOT_ARMOR: EQUIPMENT_SLOT_ARMOR_CHEST,
    LEGACY_EQUIPMENT_SLOT_FABAO: EQUIPMENT_SLOT_FABAO_1,
}

# 玩家可见槽名（§0.0.2）；机读 id 仍为英文
EQUIPMENT_SLOT_LABELS_ZH: Final[dict[str, str]] = {
    EQUIPMENT_SLOT_WEAPON_1: "主手",
    EQUIPMENT_SLOT_WEAPON_2: "副手",
    EQUIPMENT_SLOT_ARMOR_HEAD: "头",
    EQUIPMENT_SLOT_ARMOR_CHEST: "胸",
    EQUIPMENT_SLOT_ARMOR_LEGS: "腿",
    EQUIPMENT_SLOT_ARMOR_SHOES: "鞋",
    EQUIPMENT_SLOT_ARMOR_HANDS: "手",
    EQUIPMENT_SLOT_ACCESSORY_1: "项链",
    EQUIPMENT_SLOT_ACCESSORY_2: "饰品",
    EQUIPMENT_SLOT_RING_1: "戒指一",
    EQUIPMENT_SLOT_RING_2: "戒指二",
    EQUIPMENT_SLOT_FABAO_1: "法宝一",
    EQUIPMENT_SLOT_FABAO_2: "法宝二",
    EQUIPMENT_SLOT_NATAL_FABAO: "本命法宝",
    EQUIPMENT_SLOT_FUBAO: "符宝",  # 机读 id 仍为 fubao（福宝消耗件）
    EQUIPMENT_SLOT_PET: "灵宠",
}

# Slot groups for UI / catalog hints
EQUIPMENT_SLOT_GROUPS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("武器", (EQUIPMENT_SLOT_WEAPON_1, EQUIPMENT_SLOT_WEAPON_2)),
    (
        "防具",
        (
            EQUIPMENT_SLOT_ARMOR_HEAD,
            EQUIPMENT_SLOT_ARMOR_CHEST,
            EQUIPMENT_SLOT_ARMOR_LEGS,
            EQUIPMENT_SLOT_ARMOR_SHOES,
            EQUIPMENT_SLOT_ARMOR_HANDS,
        ),
    ),
    (
        "饰品",
        (
            EQUIPMENT_SLOT_ACCESSORY_1,
            EQUIPMENT_SLOT_ACCESSORY_2,
            EQUIPMENT_SLOT_RING_1,
            EQUIPMENT_SLOT_RING_2,
        ),
    ),
    (
        "法宝",
        (
            EQUIPMENT_SLOT_FABAO_1,
            EQUIPMENT_SLOT_FABAO_2,
            EQUIPMENT_SLOT_NATAL_FABAO,
            EQUIPMENT_SLOT_FUBAO,
        ),
    ),
    ("上阵", (EQUIPMENT_SLOT_PET,)),
)

# M8 business errors (40200+)
ERR_EQUIP_INVALID: Final[int] = 40205
ERR_EQUIP_CHANNEL_FORCE: Final[int] = 40212

# YAML slot / equip_kind → 可穿指针槽（点槽筛选与穿戴校验同源）
CATALOG_KIND_POINTER_SLOTS: Final[dict[str, tuple[str, ...]]] = {
    CATALOG_KIND_WEAPON_1H: WEAPON_POINTER_SLOTS,
    CATALOG_KIND_WEAPON_ANY: WEAPON_POINTER_SLOTS,
    EQUIP_KIND_WEAPON_2H: WEAPON_POINTER_SLOTS,
    CATALOG_KIND_ACCESSORY: (EQUIPMENT_SLOT_ACCESSORY_1, EQUIPMENT_SLOT_ACCESSORY_2),
    CATALOG_KIND_ACCESSORY_ANY: (EQUIPMENT_SLOT_ACCESSORY_1, EQUIPMENT_SLOT_ACCESSORY_2),
    CATALOG_KIND_RING: (EQUIPMENT_SLOT_RING_1, EQUIPMENT_SLOT_RING_2),
    CATALOG_KIND_RING_ANY: (EQUIPMENT_SLOT_RING_1, EQUIPMENT_SLOT_RING_2),
    CATALOG_KIND_FABAO: (EQUIPMENT_SLOT_FABAO_1, EQUIPMENT_SLOT_FABAO_2),
    CATALOG_KIND_LINGBAO: (EQUIPMENT_SLOT_FABAO_1, EQUIPMENT_SLOT_FABAO_2),
    CATALOG_KIND_FABAO_ANY: (EQUIPMENT_SLOT_FABAO_1, EQUIPMENT_SLOT_FABAO_2),
    CATALOG_KIND_PET: (EQUIPMENT_SLOT_PET,),
}


def canonical_equipment_slot(slot: str) -> str:
    """Map legacy five-slot ids onto the 17-zone pointer ids."""
    key = str(slot)
    return EQUIPMENT_SLOT_ALIASES.get(key, key)


def compatible_pointer_slots(def_slot: str) -> tuple[str, ...]:
    """Return wear pointers that a catalog slot/kind may occupy."""
    kind = str(def_slot)
    mapped = CATALOG_KIND_POINTER_SLOTS.get(kind)
    if mapped is not None:
        return mapped
    pointer = canonical_equipment_slot(kind)
    if pointer in EQUIPMENT_SLOTS:
        return (pointer,)
    return ()
