"""
洞府（cave）房间协议常量。

研究室是洞府下的二级玩法，对应原自研桌。
"""

from __future__ import annotations

from typing import Final

CAVE_LABEL_ZH: Final[str] = "洞府"
CAVE_ROOM_LAB: Final[str] = "lab"
CAVE_ROOM_LAB_LABEL_ZH: Final[str] = "研究室"
CAVE_ROOM_LAB_SUMMARY_ZH: Final[str] = "功法 / 阵盘 / 符箓图纸"

CAVE_ROOMS: Final[tuple[dict[str, str], ...]] = (
    {
        "id": CAVE_ROOM_LAB,
        "label_zh": CAVE_ROOM_LAB_LABEL_ZH,
        "summary_zh": CAVE_ROOM_LAB_SUMMARY_ZH,
    },
)
