"""道友 HTTP 路由（M7 L2 · 含资料隐私与查看）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_friend_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.social_trade import FriendApplyRequest, FriendPrivacyUpdateRequest
from app.services.friend_service import FriendService

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=None)
async def friends_list(
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """道友列表与申请。"""
    return success(await svc.list_friends(current_user))


@router.get("/privacy", response_model=None)
async def friends_privacy_get(
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """读取本人道友资料可见开关。"""
    return success(await svc.get_privacy(current_user))


@router.put("/privacy", response_model=None)
async def friends_privacy_put(
    body: FriendPrivacyUpdateRequest,
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """设置是否允许道友查看修为/功法/属性。"""
    return success(
        await svc.set_privacy(
            current_user,
            friend_profile_visible=body.friend_profile_visible,
        ),
    )


@router.get("/profile/{character_id}", response_model=None)
async def friends_profile(
    character_id: int,
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """查看道友资料（在线实时 / 离线快照；遮掩则 40130）。"""
    return success(await svc.get_friend_profile(current_user, character_id))


@router.post("", response_model=None)
async def friends_apply(
    body: FriendApplyRequest,
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """申请道友。"""
    return success(
        await svc.apply(
            current_user,
            target_character_id=body.target_character_id,
            target_name=body.target_name,
        ),
    )


@router.post("/{friendship_id}/accept", response_model=None)
async def friends_accept(
    friendship_id: int,
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认道友。"""
    return success(await svc.accept(current_user, friendship_id))


@router.post("/{friendship_id}/reject", response_model=None)
async def friends_reject(
    friendship_id: int,
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拒绝道友。"""
    return success(await svc.reject(current_user, friendship_id))


@router.delete("/{friendship_id}", response_model=None)
async def friends_remove(
    friendship_id: int,
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """解除道友。"""
    return success(await svc.remove(current_user, friendship_id))
