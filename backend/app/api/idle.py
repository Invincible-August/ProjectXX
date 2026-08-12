"""挂机 HTTP 路由：切换方向 / 同步结算。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_idle_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.idle import IdleDirectionRequest
from app.services.idle_service import IdleService

router = APIRouter(prefix="/idle", tags=["idle"])


@router.post("/direction", response_model=None)
async def set_idle_direction(
    payload: IdleDirectionRequest,
    idle: IdleService = Depends(get_idle_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    切换挂机方向（先 settle）。

    Args:
        payload: 含 ``direction``。
        idle: 挂机应用服务。
        current_user: 当前用户。

    Returns:
        dict: 角色 + 结算摘要信封。
    """
    data = await idle.set_direction(current_user, payload.direction)
    return success(data)


@router.post("/sync", response_model=None)
async def sync_idle(
    idle: IdleService = Depends(get_idle_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    惰性结算并返回最新角色。

    Args:
        idle: 挂机应用服务。
        current_user: 当前用户。

    Returns:
        dict: 角色 + 结算摘要信封。
    """
    data = await idle.sync(current_user)
    return success(data)


@router.get("/offline/preview", response_model=None)
async def preview_offline(
    idle: IdleService = Depends(get_idle_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """离线收益预览（幂等生成 pending）。"""
    data = await idle.preview_offline(current_user)
    return success(data)


@router.post("/offline/claim", response_model=None)
async def claim_offline(
    idle: IdleService = Depends(get_idle_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """领取离线 pending 收益。"""
    data = await idle.claim_offline(current_user)
    return success(data)
