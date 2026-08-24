"""神通装备槽与来源协议常量。"""

from __future__ import annotations

from typing import Final

from app.constants.technique import (
    TECHNIQUE_SOURCE_LABELS_ZH,
    element_view,
    normalize_technique_source,
    technique_source_label_zh,
)

DIVINE_ABILITY_HELP_ZH: Final[str] = "神通装备数量与修为和品阶相关"

ERR_DIVINE_ABILITY_LOADOUT: Final[int] = 40216
ERR_DIVINE_ABILITY_LOADOUT_ZH: Final[str] = "无法装备该神通"

__all__ = [
    "DIVINE_ABILITY_HELP_ZH",
    "ERR_DIVINE_ABILITY_LOADOUT",
    "ERR_DIVINE_ABILITY_LOADOUT_ZH",
    "TECHNIQUE_SOURCE_LABELS_ZH",
    "element_view",
    "normalize_technique_source",
    "technique_source_label_zh",
]
