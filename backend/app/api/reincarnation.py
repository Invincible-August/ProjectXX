"""轮回 HTTP 路由（M5）：预览 / 祭坛 / 流水 / 新生 / 商店。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_reincarnation_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.reincarnation import (
    ReincarnationAltarRequest,
    ReincarnationCompleteNewbornRequest,
    ReincarnationPreviewRequest,
    ReincarnationShopBuyRequest,
    ReincarnationShopRefreshRequest,
)
from app.services.reincarnation_service import ReincarnationService

router = APIRouter(prefix="/reincarnation", tags=["reincarnation"])


@router.post("/preview", response_model=None)
async def reincarnation_preview(
    payload: ReincarnationPreviewRequest | None = None,
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """预览保留清单。"""
    path = payload.path if payload else "altar"
    return success(await svc.preview(current_user, path=path))


@router.post("/altar", response_model=None)
async def reincarnation_altar(
    payload: ReincarnationAltarRequest,
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """主动祭坛轮回（结算后进入 reincarnating 新生态）。"""
    if not payload.confirm:
        from app.schemas.common import AppError

        raise AppError(code=40068, message="须确认主动轮回", http_status=400)
    return success(await svc.altar(current_user))


@router.get("/logs", response_model=None)
async def reincarnation_logs(
    limit: int = Query(default=20, ge=1, le=100),
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """最近轮回流水。"""
    return success(await svc.list_logs(current_user, limit=limit))


@router.get("/newborn", response_model=None)
async def reincarnation_newborn(
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """新生选角目录（须 status=reincarnating）。"""
    return success(await svc.newborn_options(current_user))


@router.post("/complete-newborn", response_model=None)
async def reincarnation_complete_newborn(
    payload: ReincarnationCompleteNewbornRequest,
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认新生：写入灵根/传承/体质倾向并回 normal。"""
    return success(
        await svc.complete_newborn(
            current_user,
            spirit_root_ids=payload.spirit_root_ids,
            legacy_ids=payload.legacy_ids,
            constitution_path=payload.constitution_path,
        ),
    )


@router.get("/shop", response_model=None)
async def reincarnation_shop(
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """轮回商店目录（仅新生态可访问）。"""
    return success(await svc.shop_catalog(current_user))


@router.post("/shop/buy", response_model=None)
async def reincarnation_shop_buy(
    payload: ReincarnationShopBuyRequest,
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """花费轮回点购买商店商品（固定或随机货架）。"""
    return success(
        await svc.shop_buy(
            current_user,
            item_id=payload.item_id,
            source=payload.source,
        ),
    )


@router.post("/shop/refresh", response_model=None)
async def reincarnation_shop_refresh(
    payload: ReincarnationShopRefreshRequest,
    svc: ReincarnationService = Depends(get_reincarnation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """刷新随机货架（消耗轮回点或仙缘）。"""
    return success(
        await svc.shop_refresh(current_user, currency=payload.currency),
    )
