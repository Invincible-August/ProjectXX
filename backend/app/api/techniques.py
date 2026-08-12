"""功法 HTTP 路由（M2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_play_gate, get_technique_service
from app.db.models import User
from app.schemas.common import success
from app.services.play_gate import PlayGate
from app.services.technique_service import TechniqueService

router = APIRouter(prefix="/techniques", tags=["techniques"])


@router.get("/me", response_model=None)
async def list_my_techniques(
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueService = Depends(get_technique_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回角色已解锁功法等级列表。"""
    character = await gate.require_character(current_user)
    items = await service.list_my_techniques(character)
    return success({"items": items})
