"""玩家账号页：摘要与打赏账单（只读）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.constants.admin_player import PLAYER_DEFAULT_PAGE_SIZE
from app.core.deps import get_account_service, get_current_user
from app.db.models import User
from app.schemas.common import success
from app.services.account_service import AccountService

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/summary", response_model=None)
async def account_summary(
    svc: AccountService = Depends(get_account_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """仙缘余额、累计打赏、累计观看广告次数。"""
    return success(await svc.get_summary(current_user))


@router.get("/tips", response_model=None)
async def account_tips(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=PLAYER_DEFAULT_PAGE_SIZE, ge=1),
    svc: AccountService = Depends(get_account_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """当前账号打赏记录账单。"""
    return success(await svc.list_tips(current_user, page=page, page_size=page_size))
