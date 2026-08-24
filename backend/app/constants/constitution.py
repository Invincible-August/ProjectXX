"""体质槽协议常量（本源 / 旁支；软顶文案）。"""

from __future__ import annotations

from typing import Final

# 机读槽类型（一主多副）
CONSTITUTION_SLOT_MAIN: Final[str] = "main"
CONSTITUTION_SLOT_SUB: Final[str] = "sub"

# 玩家可见槽名（修仙称谓，仍分主副）
CONSTITUTION_SLOT_LABELS_ZH: Final[dict[str, str]] = {
    CONSTITUTION_SLOT_MAIN: "本源",
    CONSTITUTION_SLOT_SUB: "旁支",
}

# 角色页 i 标签（悬停、无外圈；说明黑体）
CONSTITUTION_SLOT_HELP_ZH: Final[str] = "可以通过轮回点购买更多体质槽"

# 软上限（栏位数提示）；实际可继续用轮回点购买
CONSTITUTION_SOFT_CAP: Final[int] = 7

# 效果键 → 玩家可见短名（收藏区预览）
CONSTITUTION_EFFECT_LABELS_ZH: Final[dict[str, str]] = {
    "hp_bonus": "生命",
    "atk_bonus": "攻击",
    "idle_mult": "挂机",
    "vitality": "气血",
    "defense": "防御",
}
