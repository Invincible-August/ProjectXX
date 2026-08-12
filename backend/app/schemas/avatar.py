"""化身 API Schema（含功能解锁 / 互传预览 / 任务桩）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AvatarIdleRequest(BaseModel):
    """POST /avatar/idle 请求体。"""

    direction: str = Field(..., description="none/spirit/body/crafting")


class AvatarTransferRequest(BaseModel):
    """POST /avatar/transfer 与 preview 请求体。"""

    direction: str = Field(..., description="main_to_avatar | avatar_to_main")
    resource: str = Field(default="cultivation_points")
    amount: int = Field(..., gt=0)


class AvatarQuestAcceptRequest(BaseModel):
    """POST /avatar/quests/accept 桩请求体。"""

    quest_kind: str = Field(..., description="npc | sect")


class AvatarAssistSettingsRequest(BaseModel):
    """POST /avatar/assist/settings 请求体。"""

    enabled: bool = Field(..., description="是否允许道友借入化身助战")


class AvatarAssistInviteRequest(BaseModel):
    """POST /avatar/assist/invite 请求体（道友角色 id 或道号二选一）。"""

    target_character_id: int | None = Field(default=None, description="主人角色 id")
    target_name: str | None = Field(default=None, description="主人道号")
