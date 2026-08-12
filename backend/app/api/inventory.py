"""M4 背包 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_inventory_service, get_play_gate
from app.db.models import User
from app.schemas.common import success
from app.schemas.inventory import InventoryMoveBagRequest, InventoryUseRequest
from app.services.inventory_service import InventoryService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=None)
async def list_inventory(
    service: InventoryService = Depends(get_inventory_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """背包列表（含普通袋/轮回袋分栏摘要）。"""
    character = await gate.require_character(current_user)
    data = await service.list_bags(character)
    return success(data)


@router.post("/move-bag", response_model=None)
async def move_inventory_bag(
    payload: InventoryMoveBagRequest,
    service: InventoryService = Depends(get_inventory_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """在普通袋与轮回袋之间移动物品。"""
    character = await gate.require_character(current_user)
    data = await service.move_bag(
        character,
        item_uid=payload.item_uid,
        target_bag=payload.target_bag,
    )
    return success(data)


@router.post("/use", response_model=None)
async def use_inventory_item(
    payload: InventoryUseRequest,
    service: InventoryService = Depends(get_inventory_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """使用背包物品（如体力丹）。"""
    character = await gate.require_character(current_user)
    data = await service.use_item(
        character,
        item_uid=payload.item_uid,
        quantity=payload.quantity,
    )
    return success(data)
