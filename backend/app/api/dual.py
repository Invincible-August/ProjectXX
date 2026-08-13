"""双修 HTTP 路由（M7 L7）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_dual_cultivation_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.dual_cultivation import DualInviteRequest, DualRollRequest, DualSetGenderRequest
from app.services.dual_cultivation_service import DualCultivationService

router = APIRouter(prefix="/dual", tags=["dual"])


@router.get("/me", response_model=None)
async def dual_me(
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """当前双修会话与功法目录。"""
    return success(await svc.me(current_user))


@router.post("/set-gender", response_model=None)
async def dual_set_gender(
    body: DualSetGenderRequest,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """存量角色一次性补选性别。"""
    return success(await svc.set_gender(current_user, body.gender))


@router.post("/invite", response_model=None)
async def dual_invite(
    body: DualInviteRequest,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发起双修邀约。"""
    return success(
        await svc.invite(
            current_user,
            technique_id=body.technique_id,
            target_character_id=body.target_character_id,
            bond_kind=body.bond_kind,
            inviter_role=body.inviter_role,
            dice_seed=body.dice_seed,
            target_name=body.target_name,
        ),
    )


@router.post("/{session_id}/confirm", response_model=None)
async def dual_confirm(
    session_id: int,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认邀约。"""
    return success(await svc.confirm(current_user, session_id))


@router.post("/{session_id}/roll", response_model=None)
async def dual_roll(
    session_id: int,
    body: DualRollRequest | None = None,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """掷骰。"""
    seed = body.dice_seed if body else None
    return success(await svc.roll(current_user, session_id, dice_seed=seed))


@router.post("/{session_id}/settle", response_model=None)
async def dual_settle(
    session_id: int,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """结算领取。"""
    return success(await svc.settle(current_user, session_id))


@router.post("/{session_id}/undress", response_model=None)
async def dual_undress(
    session_id: int,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """受邀方宽衣。"""
    return success(await svc.undress(current_user, session_id))


@router.post("/{session_id}/start", response_model=None)
async def dual_start(
    session_id: int,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """邀请方开始双修（高潮循环并结算）。"""
    return success(await svc.start(current_user, session_id))


@router.post("/{session_id}/cancel", response_model=None)
async def dual_cancel(
    session_id: int,
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """取消会话。"""
    return success(await svc.cancel(current_user, session_id))


@router.get("/ranks", response_model=None)
async def dual_ranks(
    board: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    svc: DualCultivationService = Depends(get_dual_cultivation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """时长榜（默认前 100）。"""
    return success(await svc.ranks(current_user, board=board, limit=limit))
