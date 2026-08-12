"""资源分配 HTTP 路由（M2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_allocate_service, get_current_user
from app.db.models import User
from app.schemas.allocate import AllocateRequest
from app.schemas.common import success
from app.services.allocate_service import AllocateService

router = APIRouter(tags=["allocate"])


@router.post("/allocate", response_model=None)
async def allocate(
    payload: AllocateRequest,
    service: AllocateService = Depends(get_allocate_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """手动分配池资源到境界进度或功法。"""
    data = await service.allocate_resources(
        current_user,
        target_type=payload.target_type,
        target_id=payload.target_id,
        amount=payload.amount,
    )
    return success(data)
