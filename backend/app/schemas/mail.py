"""邮件 HTTP DTO（M7 L3 · 附物发信并入邮件）。"""

from __future__ import annotations

from typing import Literal, Any

from pydantic import BaseModel, Field, field_validator

from app.domain.int_money import require_non_negative_int


class MailItemLine(BaseModel):
    """附件物品行。"""

    item_id: str
    quantity: int = Field(ge=1)


class MailSendRequest(BaseModel):
    """玩家发信（可附灵石/道具；可群发）。"""

    to_character_id: int | None = Field(default=None, description="收件人角色 id")
    to_name: str | None = Field(default=None, description="收件人道号")
    subject_zh: str = Field(default="", max_length=64, description="标题；空则（无题）")
    body_zh: str = Field(default="", max_length=2000)
    spirit_stones: int = Field(default=0, ge=0)
    items: list[MailItemLine] = Field(default_factory=list)
    # sect=宗门门众；disciples=徒弟；与单发互斥时优先群发
    broadcast: Literal["sect", "disciples"] | None = Field(default=None)

    @field_validator("spirit_stones", mode="before")
    @classmethod
    def _stones_int(cls, value: Any) -> int:
        return require_non_negative_int(value, field_zh="灵石")


class GiftItemLine(BaseModel):
    """兼容旧赠送物品行。"""

    item_id: str
    quantity: int = Field(ge=1)


class GiftSendRequest(BaseModel):
    """兼容旧赠送请求（转发统一发信）。"""

    to_character_id: int | None = Field(default=None)
    to_name: str | None = Field(default=None)
    spirit_stones: int = Field(default=0, ge=0)
    items: list[GiftItemLine] = Field(default_factory=list)
    note_zh: str | None = Field(default=None, max_length=200)

    @field_validator("spirit_stones", mode="before")
    @classmethod
    def _stones_int(cls, value: Any) -> int:
        return require_non_negative_int(value, field_zh="灵石")
