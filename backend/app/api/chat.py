"""聊天 / 队伍 HTTP 路由（M7 L4）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_chat_service, get_current_user
from app.db.models import User
from app.schemas.chat import ChatDmClearRequest, ChatReadRequest, ChatSendRequest, PartyActionRequest
from app.schemas.common import success
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


@router.get("/chat/channels", response_model=None)
async def chat_channels(
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """可进频道目录。"""
    return success(await svc.list_channels(current_user))


@router.get("/chat/history", response_model=None)
async def chat_history(
    channel_ref: str = Query(..., description="频道引用"),
    limit: int | None = Query(default=None, ge=1, le=200),
    before_id: int | None = Query(default=None),
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """短历史。"""
    return success(
        await svc.history(
            current_user,
            channel_ref=channel_ref,
            limit=limit,
            before_id=before_id,
        ),
    )


@router.post("/chat/send", response_model=None)
async def chat_send(
    body: ChatSendRequest,
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发送消息。"""
    return success(
        await svc.send(
            current_user,
            channel_type=body.channel_type,
            body_zh=body.body_zh,
            channel_ref=body.channel_ref,
            peer_character_id=body.peer_character_id,
            peer_name=body.peer_name,
        ),
    )


@router.post("/chat/read", response_model=None)
async def chat_read(
    body: ChatReadRequest,
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """清零未读。"""
    return success(await svc.mark_read(current_user, channel_ref=body.channel_ref))


@router.post("/chat/dm/clear", response_model=None)
async def chat_dm_clear(
    body: ChatDmClearRequest,
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """清空私聊会话历史（双方）。"""
    return success(
        await svc.clear_dm(
            current_user,
            channel_ref=body.channel_ref,
            peer_character_id=body.peer_character_id,
            peer_name=body.peer_name,
        ),
    )


@router.get("/party/me", response_model=None)
async def party_me(
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """当前队伍。"""
    return success(await svc.party_me(current_user))


@router.post("/party", response_model=None)
async def party_action(
    body: PartyActionRequest,
    svc: ChatService = Depends(get_chat_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """组队 / 离队。"""
    return success(
        await svc.party_action(
            current_user,
            action=body.action,
            peer_character_id=body.peer_character_id or body.target_character_id,
            peer_name=body.peer_name,
            invite_id=body.invite_id,
        ),
    )
