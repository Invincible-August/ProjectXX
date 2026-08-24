"""神识乘区协议常量（M4 §6.1：化身+灵宠+傀儡同一池）。

玩法数字在 ``divine_sense.yaml``；本模块只放区名中文与玩家可见说明。
"""

from __future__ import annotations

from typing import Final

# 超载档 zone → 玩家可见中文（与 YAML zone 键对齐）
DIVINE_SENSE_ZONE_LABELS_ZH: Final[dict[str, str]] = {
    "comfort": "舒适区",
    "overload": "超载",
    "critical": "严重超载",
}

# 编成板上阵真傀硬顶（角色页勾选 + PUT / add）
PUPPET_LOADOUT_MAX: Final[int] = 3

# 角色页编成板 i 标签：件数硬顶 + 超过最大神识则削弱
PUPPET_SENSE_HELP_ZH: Final[str] = (
    "上阵傀儡最多不得超过3个，神识消耗总量超过最大神识后，傀儡强度将会受到削弱"
)

# 超员时的拒绝文案（与 i 标签首句一致）
PUPPET_LOADOUT_MAX_ZH: Final[str] = "上阵傀儡最多不得超过3个"
