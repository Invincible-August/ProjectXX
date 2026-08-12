"""机缘（聊天室红包）HTTP 路由（M7 L5；机读 /heritage）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_heritage_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.heritage import HeritageCreateRequest
from app.services.heritage_service import HeritageService

router = APIRouter(prefix="/heritage", tags=["heritage"])


@router.get("", response_model=None)
async def heritage_list(
    channel_ref: str = Query(..., description="频道引用"),
    svc: HeritageService = Depends(get_heritage_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """进行中机缘包。"""
    return success(await svc.list_active(current_user, channel_ref=channel_ref))


@router.post("", response_model=None)
async def heritage_create(
    body: HeritageCreateRequest,
    svc: HeritageService = Depends(get_heritage_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发机缘。"""
    return success(
        await svc.create(
            current_user,
            channel_ref=body.channel_ref,
            mode=body.mode,
            share_count=body.share_count,
            spirit_stones=body.spirit_stones,
            items=[row.model_dump() for row in body.items],
            note_zh=body.note_zh,
        ),
    )


@router.post("/{packet_id}/claim", response_model=None)
async def heritage_claim(
    packet_id: int,
    svc: HeritageService = Depends(get_heritage_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开缘领取。"""
    return success(await svc.claim(current_user, packet_id))
