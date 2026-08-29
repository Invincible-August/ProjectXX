"""M4 工坊 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_craft_service, get_current_user, get_play_gate
from app.db.models import User
from app.schemas.craft import (
    CraftCancelRequest,
    CraftClaimRequest,
    CraftStartRequest,
    TalismanPreloadRequest,
    TalismanScribeRequest,
)
from app.schemas.common import success
from app.services.craft_service import CraftService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/craft", tags=["craft"])


@router.get("/recipes", response_model=None)
async def list_recipes(
    service: CraftService = Depends(get_craft_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """配方列表。"""
    character = await gate.require_character(current_user)
    return success({"recipes": service.list_recipes(character)})


@router.get("/jobs", response_model=None)
async def list_jobs(
    service: CraftService = Depends(get_craft_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """我的工坊队列。"""
    character = await gate.require_character(current_user)
    jobs = await service.list_jobs(character)
    return success({"jobs": jobs})


@router.post("/start", response_model=None)
async def start_craft(
    payload: CraftStartRequest,
    service: CraftService = Depends(get_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开工配方（入队冻资源；可带数量）。"""
    data = await service.start(
        current_user,
        recipe_id=payload.recipe_id,
        actor=payload.actor,
        use_dao=bool(payload.use_dao),
        quantity=int(payload.quantity),
    )
    return success(data)


@router.post("/claim", response_model=None)
async def claim_craft(
    payload: CraftClaimRequest,
    service: CraftService = Depends(get_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兼容旧领取；完成已在 settle 直入包。"""
    data = await service.claim(current_user, payload.job_id)
    return success(data)


@router.post("/cancel", response_model=None)
async def cancel_craft(
    payload: CraftCancelRequest,
    service: CraftService = Depends(get_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """取消排队中的任务并退回冻结资源。"""
    data = await service.cancel(current_user, payload.job_id)
    return success(data)


@router.post("/talisman/scribe", response_model=None)
async def scribe_talisman(
    payload: TalismanScribeRequest,
    service: CraftService = Depends(get_craft_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Paint private talisman copies into the bag."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="画符")
    data = await service.scribe_talisman(
        character,
        template_id=payload.template_id,
        quantity=payload.quantity,
    )
    return success(data)


@router.get("/talisman/preload", response_model=None)
async def get_talisman_preload(
    service: CraftService = Depends(get_craft_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Preload bar for the next battle."""
    character = await gate.require_character(current_user)
    data = await service.list_talisman_preload(character)
    return success(data)


@router.put("/talisman/preload", response_model=None)
async def put_talisman_preload(
    payload: TalismanPreloadRequest,
    service: CraftService = Depends(get_craft_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace talisman preload slots."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="画符")
    data = await service.set_talisman_preload(character, payload.inventory_item_ids)
    return success(data)
