"""待引渡 HTTP 路由（M5）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_ferry_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.mentor import FerryRescueRequest
from app.services.ferry_service import FerryService

router = APIRouter(prefix="/ferry", tags=["ferry"])


@router.get("/me", response_model=None)
async def ferry_me(
    svc: FerryService = Depends(get_ferry_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """待引渡状态与倒计时。"""
    return success(await svc.get_me(current_user))


@router.get("/rescue-targets", response_model=None)
async def ferry_rescue_targets(
    category: str = "universal",
    svc: FerryService = Depends(get_ferry_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    引渡救援名单。

    category: universal=普渡众生（道友）· sect=同门 · kin=亲友（道友/道侣/师徒/炉鼎）
    """
    return success(await svc.list_rescue_targets(current_user, category=category))


@router.post("/self-rescue", response_model=None)
async def ferry_self_rescue(
    svc: FerryService = Depends(get_ferry_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """自救。"""
    return success(await svc.self_rescue(current_user))


@router.post("/rescue", response_model=None)
async def ferry_social_rescue(
    body: FerryRescueRequest,
    svc: FerryService = Depends(get_ferry_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """普渡/道友 / 同门 / 亲友引渡。"""
    return success(
        await svc.social_rescue(
            current_user,
            target_character_id=body.target_character_id,
            target_name=body.target_name,
            mode=body.mode,
        ),
    )


@router.post("/enter-reincarnation", response_model=None)
async def ferry_enter_reincarnation(
    svc: FerryService = Depends(get_ferry_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """自选轮回。"""
    return success(await svc.enter_reincarnation(current_user))
