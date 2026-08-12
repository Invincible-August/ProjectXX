"""化身 HTTP 路由（功能解锁 / 互传折扣 / 探索·任务桩 / 道友助战）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import (
    get_avatar_assist_service,
    get_avatar_service,
    get_current_user,
    get_play_gate,
)
from app.db.models import User
from app.schemas.avatar import (
    AvatarAssistInviteRequest,
    AvatarAssistSettingsRequest,
    AvatarIdleRequest,
    AvatarQuestAcceptRequest,
    AvatarTransferRequest,
)
from app.schemas.common import success
from app.services.avatar_assist_service import AvatarAssistService
from app.services.avatar_service import AvatarService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/avatar", tags=["avatar"])


@router.get("/me", response_model=None)
async def avatar_me(
    service: AvatarService = Depends(get_avatar_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """化身面板；无化身时 data=null。含 features / stamina / unlock_preview。"""
    character = await gate.require_character(current_user)
    data = await service.get_me(character)
    return success(data)


@router.get("/features", response_model=None)
async def avatar_features(
    service: AvatarService = Depends(get_avatar_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """当前解锁功能 + 下一档预告（含凝练权威闸 condense）。"""
    character = await gate.require_character(current_user)
    data = await service.get_features(character)
    return success(data)


@router.post("/condense", response_model=None)
async def condense_avatar(
    service: AvatarService = Depends(get_avatar_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """凝练化身（金丹门槛；永久单化身）。"""
    data = await service.condense(current_user)
    return success(data)


@router.post("/idle", response_model=None)
async def set_avatar_idle(
    payload: AvatarIdleRequest,
    service: AvatarService = Depends(get_avatar_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """设置化身挂机方向（方向须已解锁 idle_*）。"""
    data = await service.set_idle(current_user, payload.direction)
    return success(data)


@router.post("/transfer/preview", response_model=None)
async def transfer_preview(
    payload: AvatarTransferRequest,
    service: AvatarService = Depends(get_avatar_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """互传预览：gross / net / retention_ratio（不扣池）。"""
    data = await service.transfer_preview(
        current_user,
        direction=payload.direction,
        resource=payload.resource,
        amount=payload.amount,
    )
    return success(data)


@router.post("/transfer", response_model=None)
async def transfer_cultivation(
    payload: AvatarTransferRequest,
    service: AvatarService = Depends(get_avatar_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """修为互传（按保留率到账；回包含 gross/net）。"""
    data = await service.transfer(
        current_user,
        direction=payload.direction,
        resource=payload.resource,
        amount=payload.amount,
    )
    return success(data)


@router.get("/sense", response_model=None)
async def avatar_sense(
    service: AvatarService = Depends(get_avatar_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """神识读数。"""
    character = await gate.require_character(current_user)
    data = await service.get_sense(character)
    return success(data)


@router.get("/explore/status", response_model=None)
async def explore_status(
    service: AvatarService = Depends(get_avatar_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """探索代理桩状态（真地图 → M9）。"""
    data = await service.explore_status(current_user)
    return success(data)


@router.post("/quests/accept", response_model=None)
async def quest_accept(
    payload: AvatarQuestAcceptRequest,
    service: AvatarService = Depends(get_avatar_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """NPC/宗门任务能力闸 + 桩（不改进度；解锁后 50110）。"""
    data = await service.quest_accept_stub(
        current_user,
        quest_kind=payload.quest_kind,
    )
    return success(data)


# ------------------------------------------------------------------
# 道友化身助战
# ------------------------------------------------------------------


@router.post("/assist/settings", response_model=None)
async def assist_settings(
    payload: AvatarAssistSettingsRequest,
    service: AvatarAssistService = Depends(get_avatar_assist_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """主人开关道友助战（须解锁 friend_assist）。"""
    data = await service.set_assist_settings(current_user, enabled=payload.enabled)
    return success(data)


@router.post("/assist/invite", response_model=None)
async def assist_invite(
    payload: AvatarAssistInviteRequest,
    service: AvatarAssistService = Depends(get_avatar_assist_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """道友邀请借入对方化身；主人离线且开关开则自动 accept。"""
    data = await service.invite(
        current_user,
        target_character_id=payload.target_character_id,
        target_name=payload.target_name,
    )
    return success(data)


@router.post("/assist/{session_id}/accept", response_model=None)
async def assist_accept(
    session_id: int,
    service: AvatarAssistService = Depends(get_avatar_assist_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """主人接受助战邀请。"""
    data = await service.accept(current_user, session_id)
    return success(data)


@router.post("/assist/{session_id}/reject", response_model=None)
async def assist_reject(
    session_id: int,
    service: AvatarAssistService = Depends(get_avatar_assist_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """主人拒绝助战邀请。"""
    data = await service.reject(current_user, session_id)
    return success(data)


@router.post("/assist/{session_id}/end", response_model=None)
async def assist_end(
    session_id: int,
    service: AvatarAssistService = Depends(get_avatar_assist_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """主人或借用人结束助战。"""
    data = await service.end(current_user, session_id)
    return success(data)


@router.get("/assist/me", response_model=None)
async def assist_me(
    service: AvatarAssistService = Depends(get_avatar_assist_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """当前角色相关的助战会话（主人侧 / 借用人侧）。"""
    data = await service.list_me(current_user)
    return success(data)
