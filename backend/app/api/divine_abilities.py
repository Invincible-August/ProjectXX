"""神通 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.constants.avatar import normalize_loadout_actor
from app.core.deps import get_current_user, get_divine_ability_service, get_play_gate
from app.db.models import User
from app.schemas.common import success
from app.schemas.divine_ability import DivineAbilityEquipRequest, DivineAbilityUnequipRequest
from app.services.divine_ability_service import DivineAbilityService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/divine-abilities", tags=["divine-abilities"])


@router.get("/me", response_model=None)
async def list_my_divine_abilities(
    actor: str = Query(default="main"),
    gate: PlayGate = Depends(get_play_gate),
    service: DivineAbilityService = Depends(get_divine_ability_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """已学神通 + 品阶槽装备栏。"""
    character = await gate.require_character(current_user)
    page = await service.get_page(character, actor=normalize_loadout_actor(actor))
    return success(page)


@router.post("/equip", response_model=None)
async def equip_divine_ability(
    payload: DivineAbilityEquipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: DivineAbilityService = Depends(get_divine_ability_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """装备已学会的神通。"""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    page = await service.equip_ability(
        character,
        ability_id=payload.ability_id,
        slot_index=payload.slot_index,
        actor=normalize_loadout_actor(payload.actor),
    )
    return success(page)


@router.post("/unequip", response_model=None)
async def unequip_divine_ability(
    payload: DivineAbilityUnequipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: DivineAbilityService = Depends(get_divine_ability_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """卸下神通槽。"""
    character = await gate.require_character(current_user)
    page = await service.unequip_ability(
        character,
        slot_index=payload.slot_index,
        actor=normalize_loadout_actor(payload.actor),
    )
    return success(page)
