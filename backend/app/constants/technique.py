"""功法装备 / 来源 / 元素协议常量。"""

from __future__ import annotations

from typing import Final

TECHNIQUE_SLOT_MAIN: Final[str] = "main"  # 主功法
TECHNIQUE_SLOT_ART: Final[str] = "art"  # 技法

TECHNIQUE_SLOT_LABELS_ZH: Final[dict[str, str]] = {
    TECHNIQUE_SLOT_MAIN: "主功法",
    TECHNIQUE_SLOT_ART: "技法",
}

TECHNIQUE_SLOT_HELP_ZH: Final[str] = (
    "主功法只能装备一本；技法可装备多本，修为越高槽位越多。"
)

TECHNIQUE_SOURCE_SYSTEM: Final[str] = "system"  # 系统
TECHNIQUE_SOURCE_SECT: Final[str] = "sect"  # 宗门
TECHNIQUE_SOURCE_MENTOR: Final[str] = "mentor"  # 师承
TECHNIQUE_SOURCE_RESEARCH: Final[str] = "research"  # 自研
TECHNIQUE_SOURCE_CHANCE: Final[str] = "chance"  # 机缘

TECHNIQUE_SOURCE_LABELS_ZH: Final[dict[str, str]] = {
    TECHNIQUE_SOURCE_SYSTEM: "系统",
    TECHNIQUE_SOURCE_SECT: "宗门",
    TECHNIQUE_SOURCE_MENTOR: "师承",
    TECHNIQUE_SOURCE_RESEARCH: "自研",
    TECHNIQUE_SOURCE_CHANCE: "机缘",
}

# 旧列表文案 → 五源
TECHNIQUE_SOURCE_ALIASES: Final[dict[str, str]] = {
    "official": TECHNIQUE_SOURCE_SYSTEM,
    "custom": TECHNIQUE_SOURCE_RESEARCH,
}

ELEMENT_METAL: Final[str] = "metal"
ELEMENT_WOOD: Final[str] = "wood"
ELEMENT_WATER: Final[str] = "water"
ELEMENT_FIRE: Final[str] = "fire"
ELEMENT_EARTH: Final[str] = "earth"
ELEMENT_WIND: Final[str] = "wind"
ELEMENT_THUNDER: Final[str] = "thunder"
ELEMENT_DARK: Final[str] = "dark"  # 暗

ELEMENT_LABELS_ZH: Final[dict[str, str]] = {
    ELEMENT_METAL: "金",
    ELEMENT_WOOD: "木",
    ELEMENT_WATER: "水",
    ELEMENT_FIRE: "火",
    ELEMENT_EARTH: "土",
    ELEMENT_WIND: "风",
    ELEMENT_THUNDER: "雷",
    ELEMENT_DARK: "暗",
}

ELEMENT_BORDER_COLORS: Final[dict[str, str]] = {
    ELEMENT_METAL: "#c9a227",
    ELEMENT_WOOD: "#3d8c40",
    ELEMENT_WATER: "#2b6cb0",
    ELEMENT_FIRE: "#c53030",
    ELEMENT_EARTH: "#8d6e3d",
    ELEMENT_WIND: "#319795",
    ELEMENT_THUNDER: "#6b46c1",
    ELEMENT_DARK: "#5c5470",
}

DEFAULT_SPIRIT_ROOT: Final[str] = "mixed_root"  # 创角默认杂灵根

ERR_TECHNIQUE_LOADOUT: Final[int] = 40215  # 功法装备槽不合法
ERR_TECHNIQUE_LOADOUT_ZH: Final[str] = "无法装备该功法"


def normalize_technique_source(raw: str | None) -> str:
    """Map legacy official/custom ids onto the five player-facing sources."""
    key = str(raw or TECHNIQUE_SOURCE_SYSTEM).strip()
    key = TECHNIQUE_SOURCE_ALIASES.get(key, key)
    if key not in TECHNIQUE_SOURCE_LABELS_ZH:
        return TECHNIQUE_SOURCE_SYSTEM
    return key


def technique_source_label_zh(raw: str | None) -> str:
    """Player-visible source label."""
    return TECHNIQUE_SOURCE_LABELS_ZH[normalize_technique_source(raw)]


def element_view(element_id: str) -> dict[str, str]:
    """Build one element chip for the technique tooltip."""
    eid = str(element_id).strip()
    return {
        "id": eid,
        "label_zh": ELEMENT_LABELS_ZH.get(eid, eid),
        "border": ELEMENT_BORDER_COLORS.get(eid, "#909399"),
    }

