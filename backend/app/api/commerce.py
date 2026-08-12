"""商业化 HTTP 路由（M7 L8）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_commerce_service, get_current_user
from app.db.models import User
from app.schemas.commerce import (
    CommerceBuyRequest,
    CommerceMembershipRequest,
    CommerceSandboxGrantRequest,
)
from app.schemas.common import success
from app.services.commerce_service import CommerceService

router = APIRouter(prefix="/commerce", tags=["commerce"])


@router.get("/me", response_model=None)
async def commerce_me(
    svc: CommerceService = Depends(get_commerce_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """会员与天道点摘要。"""
    return success(await svc.me(current_user))


@router.get("/shop", response_model=None)
async def commerce_shop(
    svc: CommerceService = Depends(get_commerce_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """天道商店货架。"""
    return success(await svc.shop(current_user))


@router.post("/membership", response_model=None)
async def commerce_membership(
    body: CommerceMembershipRequest,
    svc: CommerceService = Depends(get_commerce_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开通 / 续费会员。"""
    return success(await svc.activate_membership(current_user, body.tier))


@router.post("/shop/buy", response_model=None)
async def commerce_buy(
    body: CommerceBuyRequest,
    svc: CommerceService = Depends(get_commerce_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """购买货架商品。"""
    return success(await svc.buy(current_user, body.item_id))


@router.post("/sandbox/grant-tiandao", response_model=None)
async def commerce_sandbox_grant(
    body: CommerceSandboxGrantRequest,
    svc: CommerceService = Depends(get_commerce_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """沙盒发放天道点。"""
    return success(await svc.sandbox_grant_tiandao(current_user, body.amount))
