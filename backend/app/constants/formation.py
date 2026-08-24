"""阵法预设槽位协议常量（出战页 / 快照回退）。"""

from __future__ import annotations

# 每名角色最多保存的阵法预设数（出战页下拉编辑）
FORMATION_PRESET_SLOT_COUNT: int = 5

# 默认种子：(槽位, 中文名, 内部 role)。
# role 仍给开战缺省 / 防守快照回退用；前端不再展示进攻/防守/临时。
FORMATION_DEFAULT_PRESET_SLOTS: tuple[tuple[int, str, str], ...] = (
    (0, "阵法一", "attack"),
    (1, "阵法二", "defense"),
    (2, "阵法三", "temp"),
    (3, "阵法四", "attack"),
    (4, "阵法五", "attack"),
)

# 合法内部定位（机读；不直接给玩家看）
FORMATION_PRESET_ROLES: frozenset[str] = frozenset({"attack", "defense", "temp"})

# 助战锚点：预设独立字段，不进棋子栏；开战注入客串化身
ASSIST_ANCHOR_UID: str = "assist_anchor"
ASSIST_ANCHOR_KIND: str = "assist"
