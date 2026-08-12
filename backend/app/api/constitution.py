"""体质 HTTP 路由（M2 骨架）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_constitution_service, get_current_user, get_play_gate
from app.db.models import User
from app.schemas.common import success
from app.schemas.constitution import (
    ConstitutionEquipRequest,
    ConstitutionFuseRequest,
    ConstitutionUnequipRequest,
    ConstitutionUpgradeRequest,
)
from app.services.constitution_service import ConstitutionService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/constitution", tags=["constitution"])


@router.get("/me", response_model=None)
async def constitution_me(
    gate: PlayGate = Depends(get_play_gate),
    service: ConstitutionService = Depends(get_constitution_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """背包 + 格子 + 已镶嵌。"""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    state = await service.get_constitution_state(character)
    return success(state)


@router.post("/equip", response_model=None)
async def constitution_equip(
    payload: ConstitutionEquipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ConstitutionService = Depends(get_constitution_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """镶嵌体质物品。"""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    state = await service.equip_constitution_item(
        character,
        item_id=payload.item_id,
        slot_type=payload.slot_type,
        slot_index=payload.slot_index,
    )
    return success({"constitution": state})


@router.post("/unequip", response_model=None)
async def constitution_unequip(
    payload: ConstitutionUnequipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ConstitutionService = Depends(get_constitution_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """卸下体质物品。"""
    character = await gate.require_character(current_user)
    state = await service.unequip_constitution_item(
        character,
        slot_type=payload.slot_type,
        slot_index=payload.slot_index,
    )
    return success({"constitution": state})


@router.post("/upgrade", response_model=None)
async def constitution_upgrade(
    payload: ConstitutionUpgradeRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ConstitutionService = Depends(get_constitution_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """升品占位。"""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    data = await service.upgrade_constitution_item(
        character,
        item_id=payload.item_id,
    )
    return success(data)


@router.post("/fuse", response_model=None)
async def constitution_fuse(
    payload: ConstitutionFuseRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ConstitutionService = Depends(get_constitution_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """融合占位。"""
    character = await gate.require_character(current_user)
    data = await service.fuse_constitution_items(
        character,
        item_ids=payload.item_ids,
    )
    return success(data)
