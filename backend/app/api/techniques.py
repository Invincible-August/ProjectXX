"""功法 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.constants.avatar import normalize_loadout_actor
from app.core.deps import get_current_user, get_play_gate, get_technique_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.technique import TechniqueEquipRequest, TechniqueUnequipRequest
from app.services.play_gate import PlayGate
from app.services.technique_service import TechniqueService

router = APIRouter(prefix="/techniques", tags=["techniques"])


@router.get("/me", response_model=None)
async def list_my_techniques(
    actor: str = Query(default="main"),
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueService = Depends(get_technique_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """已学功法 + 主功法/技法装备栏。"""
    character = await gate.require_character(current_user)
    page = await service.get_techniques_page(
        character,
        actor=normalize_loadout_actor(actor),
    )
    return success(page)


@router.post("/equip", response_model=None)
async def equip_technique(
    payload: TechniqueEquipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueService = Depends(get_technique_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """装备已学会的功法。"""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    page = await service.equip_technique(
        character,
        technique_id=payload.technique_id,
        slot_type=payload.slot_type,
        slot_index=payload.slot_index,
        actor=normalize_loadout_actor(payload.actor),
    )
    return success(page)


@router.post("/unequip", response_model=None)
async def unequip_technique(
    payload: TechniqueUnequipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueService = Depends(get_technique_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """卸下功法槽。"""
    character = await gate.require_character(current_user)
    page = await service.unequip_technique(
        character,
        slot_type=payload.slot_type,
        slot_index=payload.slot_index,
        actor=normalize_loadout_actor(payload.actor),
    )
    return success(page)
