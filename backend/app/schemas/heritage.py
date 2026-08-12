"""传承 HTTP DTO（M7 L5）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HeritageItemLine(BaseModel):
    """传承物品行。"""

    item_id: str
    quantity: int = Field(ge=1)


class HeritageCreateRequest(BaseModel):
    """发传承。"""

    channel_ref: str
    mode: str = Field(description="random|fixed")
    share_count: int = Field(ge=1, le=100)
    spirit_stones: int = Field(default=0, ge=0)
    items: list[HeritageItemLine] = Field(default_factory=list)
    note_zh: str | None = Field(default=None, max_length=64)
