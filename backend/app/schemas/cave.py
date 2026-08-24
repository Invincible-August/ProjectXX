"""Cave (洞府) HTTP schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CaveRoomPublic(BaseModel):
    """A room listed on the cave hub."""

    id: str = Field(description="lab")
    label_zh: str
    summary_zh: str = ""


class CaveOverviewPublic(BaseModel):
    """洞府枢纽：房间列表。"""

    label_zh: str
    rooms: list[CaveRoomPublic] = Field(default_factory=list)
