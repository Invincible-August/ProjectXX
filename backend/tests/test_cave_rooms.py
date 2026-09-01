"""洞府房间表。"""

from __future__ import annotations

from app.constants.cave import CAVE_ROOM_LAB, CAVE_ROOM_WORKSHOP, CAVE_ROOMS


def test_cave_rooms_include_workshop_and_lab() -> None:
    """Hub lists workshop then lab; manufacturing HTTP stays on /craft."""
    ids = [row["id"] for row in CAVE_ROOMS]
    assert ids == [CAVE_ROOM_WORKSHOP, CAVE_ROOM_LAB]
    labels = {row["id"]: row["label_zh"] for row in CAVE_ROOMS}
    assert labels[CAVE_ROOM_WORKSHOP] == "工坊"
    assert labels[CAVE_ROOM_LAB] == "研究室"
