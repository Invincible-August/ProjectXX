"""聊天 / 队伍 HTTP DTO（M7 L4）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatSendRequest(BaseModel):
    """发送聊天。"""

    channel_type: str = Field(description="world|sect|dm|mentor|party")
    body_zh: str = Field(min_length=1, max_length=2000)
    channel_ref: str | None = None
    peer_character_id: int | None = None
    peer_name: str | None = None


class ChatReadRequest(BaseModel):
    """标记频道已读。"""

    channel_ref: str


class ChatDmClearRequest(BaseModel):
    """清空与某道友的私聊会话（双方可见历史均删）。"""

    channel_ref: str | None = None
    peer_character_id: int | None = None
    peer_name: str | None = None


class PartyActionRequest(BaseModel):
    """组队 / 邀请 / 应答 / 离队 / 踢人 / 转团队。"""

    action: str = Field(
        description="create|invite|accept|reject|leave|kick|convert_to_team|convert_to_party",
    )
    peer_character_id: int | None = None
    peer_name: str | None = None
    # accept / reject 时必填
    invite_id: int | None = None
    # kick 时目标（与 peer_* 二选一）
    target_character_id: int | None = None
