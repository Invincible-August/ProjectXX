"""工坊品质与制作等级协议常量。"""

from __future__ import annotations

from typing import Final

# 造物品质（机读；展示用 CRAFT_QUALITY_LABEL_ZH）
CRAFT_QUALITY_COMMON: Final[str] = "common"  # 凡品
CRAFT_QUALITY_FINE: Final[str] = "fine"  # 良品
CRAFT_QUALITY_RARE: Final[str] = "rare"  # 上品
CRAFT_QUALITY_SUPERB: Final[str] = "superb"  # 极品

CRAFT_QUALITIES: Final[tuple[str, ...]] = (
    CRAFT_QUALITY_COMMON,
    CRAFT_QUALITY_FINE,
    CRAFT_QUALITY_RARE,
    CRAFT_QUALITY_SUPERB,
)

CRAFT_QUALITY_LABEL_ZH: Final[dict[str, str]] = {
    CRAFT_QUALITY_COMMON: "凡品",
    CRAFT_QUALITY_FINE: "良品",
    CRAFT_QUALITY_RARE: "上品",
    CRAFT_QUALITY_SUPERB: "极品",
}

# 制作等级不足（开工拒绝）
ERR_CRAFT_LEVEL: Final[int] = 40086
ERR_CRAFT_LEVEL_ZH: Final[str] = "制作等级不足，无法学习或制造该图纸"

# 阵法等非制造业配方不可开工
ERR_CRAFT_NOT_WORKSHOP: Final[int] = 40087
ERR_CRAFT_NOT_WORKSHOP_ZH: Final[str] = "阵法不属于工坊制造业"
