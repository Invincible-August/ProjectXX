"""渡劫 HTTP 路由（M5）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_tribulation_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.tribulation import TribulationPrepRequest, TribulationResolveBatchRequest
from app.services.tribulation_service import TribulationService

router = APIRouter(prefix="/tribulation", tags=["tribulation"])


@router.get("/me", response_model=None)
async def tribulation_me(
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """当前渡劫会话。"""
    return success(await svc.get_me(current_user))


@router.post("/start-prep", response_model=None)
async def tribulation_start_prep(
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """创建 preparing 会话。"""
    return success(await svc.start_prep(current_user))


@router.put("/prep", response_model=None)
async def tribulation_save_prep(
    payload: TribulationPrepRequest,
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """保存准备格。"""
    return success(
        await svc.save_prep(
            current_user,
            slots=payload.slots,
            formation_id=payload.formation_id,
            veil_chosen=payload.veil_chosen,
        ),
    )


@router.post("/commit-prep", response_model=None)
async def tribulation_commit_prep(
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认准备。"""
    return success(await svc.commit_prep(current_user))


@router.post("/veil-check", response_model=None)
async def tribulation_veil_check(
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """遮天检定。"""
    return success(await svc.veil_check(current_user))


@router.post("/begin", response_model=None)
async def tribulation_begin(
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开渡。"""
    return success(await svc.begin(current_user))


@router.post("/resolve-batch", response_model=None)
async def tribulation_resolve_batch(
    payload: TribulationResolveBatchRequest | None = None,
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """结算下一批雷击。"""
    batch_size = payload.batch_size if payload else None
    return success(await svc.resolve_batch(current_user, batch_size=batch_size))


@router.post("/auto-resolve", response_model=None)
async def tribulation_auto_resolve(
    svc: TribulationService = Depends(get_tribulation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """一键结算至结束。"""
    return success(await svc.auto_resolve(current_user))
