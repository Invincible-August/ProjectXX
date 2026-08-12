"""世界事件骨架 HTTP。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_world_event_service
from app.db.models import User
from app.schemas.common import success
from app.services.world_event_service import WorldEventService

router = APIRouter(prefix="/world-events", tags=["world-events"])


@router.get("/current")
async def world_events_current(
    user: User = Depends(get_current_user),
    service: WorldEventService = Depends(get_world_event_service),
) -> dict:
    """当前事件骨架。"""
    return success(await service.list_current(user))


@router.post("/{event_id}/register")
async def world_events_register(
    event_id: str,
    user: User = Depends(get_current_user),
    service: WorldEventService = Depends(get_world_event_service),
) -> dict:
    """报名占位。"""
    return success(await service.register(user, event_id))
