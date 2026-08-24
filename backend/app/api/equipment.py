"""Equipment HTTP routes (M8 R0 · 17-zone + puppet loadout)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.constants.avatar import LOADOUT_ACTOR_AVATAR, normalize_loadout_actor

from app.core.deps import get_character_service, get_current_user, get_equipment_service, get_play_gate
from app.db.models import User
from app.domain.activity_mutex import ERR_STATUS_BLOCKS
from app.schemas.common import success
from app.schemas.equipment import (
    AvatarDeployRequest,
    EquipmentEquipRequest,
    EquipmentUnequipRequest,
    PuppetLoadoutReplaceRequest,
    PuppetLoadoutRequest,
    TalismanLoadoutReplaceRequest,
)
from app.services.character_service import CharacterService
from app.services.equipment_service import EquipmentService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/equipment", tags=["equipment"])


async def _combat_for_wearer(
    characters: CharacterService,
    character,
    wearer: str,
) -> dict:
    """Build ATTR block for 本体 or 化身 wear pointers."""
    if wearer != LOADOUT_ACTOR_AVATAR:
        return await characters.build_combat_attrs(character)
    from app.services.avatar_repo import fetch_avatar_row

    avatar = await fetch_avatar_row(characters._session, character.id)
    if avatar is None:
        return await characters.build_combat_attrs(character)
    return await characters.build_combat_attrs(
        character,
        entity_kind="avatar",
        apply_reincarnation_attr_bonus=False,
        realm_major=str(avatar.major_realm),
        realm_stage=int(avatar.realm_stage or 1),
        loadout_actor=LOADOUT_ACTOR_AVATAR,
    )


@router.get("/slots", response_model=None)
async def equipment_slots(
    actor: str = Query(default="main"),
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pointer slots + bag + puppet loadout + channel flags."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    wearer = normalize_loadout_actor(actor)
    state = await service.get_slots_state(character, actor=wearer)
    combat = await _combat_for_wearer(characters, character, wearer)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.post("/equip", response_model=None)
async def equipment_equip(
    payload: EquipmentEquipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Wear item from bag."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    wearer = normalize_loadout_actor(payload.actor)
    state = await service.equip_item(
        character,
        slot=payload.slot,
        item_uid=payload.item_uid,
        actor=wearer,
    )
    combat = await _combat_for_wearer(characters, character, wearer)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.post("/unequip", response_model=None)
async def equipment_unequip(
    payload: EquipmentUnequipRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove item from slot."""
    character = await gate.require_character(current_user)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    wearer = normalize_loadout_actor(payload.actor)
    state = await service.unequip_slot(character, slot=payload.slot, actor=wearer)
    combat = await _combat_for_wearer(characters, character, wearer)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.post("/puppet-loadout/add", response_model=None)
async def puppet_loadout_add(
    payload: PuppetLoadoutRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Add a puppet inventory row onto the loadout board (occupancy=deployed)."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    state = await service.add_puppet_to_loadout(character, item_uid=payload.item_uid)
    combat = await characters.build_combat_attrs(character)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.post("/puppet-loadout/remove", response_model=None)
async def puppet_loadout_remove(
    payload: PuppetLoadoutRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a puppet from the loadout board back to idle."""
    character = await gate.require_character(current_user)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    state = await service.remove_puppet_from_loadout(character, item_uid=payload.item_uid)
    combat = await characters.build_combat_attrs(character)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.put("/puppet-loadout", response_model=None)
async def puppet_loadout_replace(
    payload: PuppetLoadoutReplaceRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace deployed puppets; never rejects for divine-sense overload."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    state = await service.replace_puppet_loadout(character, item_uids=payload.item_uids)
    combat = await characters.build_combat_attrs(character)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.post("/avatar-deploy", response_model=None)
async def equipment_avatar_deploy(
    payload: AvatarDeployRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Mark condensed avatar as deployed (sense + formation bench)."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    state = await service.set_avatar_deployed(character, deployed=payload.deployed)
    combat = await characters.build_combat_attrs(character)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.put("/talisman-loadout", response_model=None)
async def talisman_loadout_replace(
    payload: TalismanLoadoutReplaceRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: EquipmentService = Depends(get_equipment_service),
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace equipped talismans (same persistence as workshop preload)."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="穿戴装备", code=ERR_STATUS_BLOCKS)
    state = await service.replace_talisman_loadout(
        character,
        inventory_item_ids=payload.inventory_item_ids,
        item_uids=payload.item_uids,
    )
    combat = await characters.build_combat_attrs(character)
    return success({"equipment": state, "combat": combat.get("combat")})


@router.get("/catalog", response_model=None)
async def equipment_catalog(
    service: EquipmentService = Depends(get_equipment_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Official sample catalog (read-only)."""
    _ = current_user
    catalog = await service.get_catalog()
    return success({"items": catalog})
