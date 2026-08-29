"""
洞府（cave）房间协议常量。

工坊、研究室是洞府下的二级玩法；制造业 HTTP 仍走 /craft。
"""

from __future__ import annotations

from typing import Final

CAVE_LABEL_ZH: Final[str] = "洞府"
CAVE_ROOM_WORKSHOP: Final[str] = "workshop"
CAVE_ROOM_WORKSHOP_LABEL_ZH: Final[str] = "工坊"
CAVE_ROOM_WORKSHOP_SUMMARY_ZH: Final[str] = "炼丹 / 炼器 / 符箓 / 傀儡"
CAVE_ROOM_LAB: Final[str] = "lab"
CAVE_ROOM_LAB_LABEL_ZH: Final[str] = "研究室"
CAVE_ROOM_LAB_SUMMARY_ZH: Final[str] = "功法 / 阵盘 / 符箓图纸"

CAVE_ROOMS: Final[tuple[dict[str, str], ...]] = (
    {
        "id": CAVE_ROOM_WORKSHOP,
        "label_zh": CAVE_ROOM_WORKSHOP_LABEL_ZH,
        "summary_zh": CAVE_ROOM_WORKSHOP_SUMMARY_ZH,
    },
    {
        "id": CAVE_ROOM_LAB,
        "label_zh": CAVE_ROOM_LAB_LABEL_ZH,
        "summary_zh": CAVE_ROOM_LAB_SUMMARY_ZH,
    },
)
