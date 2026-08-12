"""M4 工坊 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_craft_service, get_current_user, get_play_gate
from app.db.models import User
from app.schemas.craft import CraftClaimRequest, CraftStartRequest
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
    """开工配方。"""
    data = await service.start(
        current_user,
        recipe_id=payload.recipe_id,
        actor=payload.actor,
        use_dao=bool(payload.use_dao),
    )
    return success(data)


@router.post("/claim", response_model=None)
async def claim_craft(
    payload: CraftClaimRequest,
    service: CraftService = Depends(get_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """领取完成品。"""
    data = await service.claim(current_user, payload.job_id)
    return success(data)
