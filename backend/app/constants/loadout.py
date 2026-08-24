"""本体 / 化身独立编成（装备、功法、神通）协议常量。"""

from __future__ import annotations

from typing import Final

from app.constants.equipment import EQUIPMENT_SLOT_FUBAO, EQUIPMENT_SLOT_PET, EQUIPMENT_SLOTS

# 编成主体：本体页 / 化身页
LOADOUT_ACTOR_MAIN: Final[str] = "main"
LOADOUT_ACTOR_AVATAR: Final[str] = "avatar"

# 化身不可穿：灵宠、符宝（傀儡/符箓是编成板，不走指针槽）
AVATAR_FORBIDDEN_EQUIP_SLOTS: Final[frozenset[str]] = frozenset(
    {
        EQUIPMENT_SLOT_PET,
        EQUIPMENT_SLOT_FUBAO,
    },
)

AVATAR_EQUIPMENT_SLOTS: Final[tuple[str, ...]] = tuple(
    slot for slot in EQUIPMENT_SLOTS if slot not in AVATAR_FORBIDDEN_EQUIP_SLOTS
)


def normalize_loadout_actor(raw: str | None) -> str:
    """把查询/请求里的 actor 收成 main 或 avatar。"""
    value = str(raw or LOADOUT_ACTOR_MAIN).strip().lower()
    if value in {LOADOUT_ACTOR_AVATAR, "av"}:
        return LOADOUT_ACTOR_AVATAR
    return LOADOUT_ACTOR_MAIN
