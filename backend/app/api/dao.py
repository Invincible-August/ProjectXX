"""大道 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_dao_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.dao import DaoOpenChooseRequest, DaoUsagePreviewRequest
from app.services.dao_service import DaoService

router = APIRouter(prefix="/dao", tags=["dao"])


@router.get("/catalog")
async def dao_catalog(
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """样本图鉴。"""
    return success(await service.get_catalog(user))


@router.get("/me")
async def dao_me(
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """本命与道资源。"""
    return success(await service.get_me(user))


@router.get("/pool")
async def dao_pool(
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """道池列表。"""
    return success(await service.get_pool(user))


@router.post("/open/roll")
async def dao_open_roll(
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """生成三选项会话。"""
    return success(await service.roll_open(user))


@router.post("/open/choose")
async def dao_open_choose(
    payload: DaoOpenChooseRequest,
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """确认本命道。"""
    return success(
        await service.choose_open(user, dao_id=payload.dao_id, session_id=payload.session_id),
    )


@router.post("/usage/preview")
async def dao_usage_preview(
    payload: DaoUsagePreviewRequest,
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """预览运用消耗。"""
    return success(await service.preview_usage(user, kind=payload.kind))
