"""道友 HTTP 路由（M7 L2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_friend_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.social_trade import FriendApplyRequest
from app.services.friend_service import FriendService

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=None)
async def friends_list(
    svc: FriendService = Depends(get_friend_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """道友列表与申请。"""
    return success(await svc.list_friends(current_user))


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
