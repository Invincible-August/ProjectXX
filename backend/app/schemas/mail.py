"""邮件 / 赠送 HTTP DTO（M7 L3）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MailSendRequest(BaseModel):
    """玩家无附件信。"""

    to_character_id: int | None = Field(default=None, description="收件人角色 id")
    to_name: str | None = Field(default=None, description="收件人道号")
    subject_zh: str = Field(default="道友来信", max_length=64)
    body_zh: str = Field(default="", max_length=2000)


class GiftItemLine(BaseModel):
    """赠送物品行。"""

    item_id: str
    quantity: int = Field(ge=1)


class GiftSendRequest(BaseModel):
    """赠送请求。"""

    to_character_id: int | None = Field(default=None)
    to_name: str | None = Field(default=None)
    spirit_stones: int = Field(default=0, ge=0)
    items: list[GiftItemLine] = Field(default_factory=list)
    note_zh: str | None = Field(default=None, max_length=200)
