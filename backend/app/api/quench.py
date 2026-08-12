"""炼体淬体 HTTP 路由（与修为 /breakthrough 分立）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_quench_service
from app.db.models import User
from app.schemas.common import success
from app.services.quench_service import QuenchService

router = APIRouter(prefix="/quench", tags=["quench"])


@router.get("/preview", response_model=None)
async def preview_quench(
    service: QuenchService = Depends(get_quench_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    淬体预览。

    Args:
        service: 淬体服务。
        current_user: 当前用户。

    Returns:
        dict: 预览信封。
    """
    data = await service.preview_quench(current_user)
    return success(data)


@router.post("/attempt", response_model=None)
async def attempt_quench(
    service: QuenchService = Depends(get_quench_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    发起淬体（炼体境晋级）。

    Args:
        service: 淬体服务。
        current_user: 当前用户。

    Returns:
        dict: 结果信封（含 character）。
    """
    data = await service.attempt_quench(current_user)
    return success(data)
