"""大道 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_dao_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.dao import DaoOpenChooseRequest, DaoOpenRollRequest, DaoUsagePreviewRequest
from app.services.dao_service import DaoService

router = APIRouter(prefix="/dao", tags=["dao"])


@router.get("/catalog")
async def dao_catalog(
    actor: str = Query(default="main"),
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """样本图鉴（该主体须真仙）。"""
    return success(await service.get_catalog(user, actor=actor))


@router.get("/me")
async def dao_me(
    actor: str = Query(default="main"),
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """本命与道资源（该主体须真仙）。"""
    return success(await service.get_me(user, actor=actor))


@router.get("/pool")
async def dao_pool(
    actor: str = Query(default="main"),
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """道池列表（该主体须真仙）。"""
    return success(await service.get_pool(user, actor=actor))


@router.post("/open/roll")
async def dao_open_roll(
    payload: DaoOpenRollRequest | None = None,
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """生成三选项会话。"""
    actor = payload.actor if payload is not None else "main"
    return success(await service.roll_open(user, actor=actor))


@router.post("/open/choose")
async def dao_open_choose(
    payload: DaoOpenChooseRequest,
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """确认本命道。"""
    return success(
        await service.choose_open(
            user,
            dao_id=payload.dao_id,
            session_id=payload.session_id,
            actor=payload.actor,
        ),
    )


@router.post("/usage/preview")
async def dao_usage_preview(
    payload: DaoUsagePreviewRequest,
    user: User = Depends(get_current_user),
    service: DaoService = Depends(get_dao_service),
) -> dict:
    """预览运用消耗。"""
    return success(await service.preview_usage(user, kind=payload.kind, actor=payload.actor))
