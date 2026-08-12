"""宗门 HTTP 路由（M7 L1）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_sect_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.sect import (
    SectCreateRequest,
    SectJoinRequest,
    SectPetExchangeRequest,
    SectQuestAcceptRequest,
    SectQuestCompleteRequest,
    SectShopBuyRequest,
)
from app.services.sect_service import SectService

router = APIRouter(prefix="/sect", tags=["sect"])


@router.get("/me", response_model=None)
async def sect_me(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """我的宗门摘要。"""
    return success(await svc.get_me(current_user))


@router.get("/npc", response_model=None)
async def sect_npc_list(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """NPC 宗门列表。"""
    return success(await svc.list_npc(current_user))


@router.post("/join", response_model=None)
async def sect_join(
    body: SectJoinRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拜入 NPC 宗门。"""
    return success(await svc.join(current_user, template_id=body.template_id))


@router.post("/create", response_model=None)
async def sect_create(
    body: SectCreateRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """自建宗门。"""
    return success(await svc.create(current_user, name=body.name, motto=body.motto))


@router.get("/quests", response_model=None)
async def sect_quests(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """宗门任务列表。"""
    return success(await svc.list_quests(current_user))


@router.post("/quests/{quest_id}/accept", response_model=None)
async def sect_quest_accept(
    quest_id: str,
    body: SectQuestAcceptRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """接取宗门任务。"""
    return success(
        await svc.accept_quest(
            current_user,
            quest_id=quest_id,
            assignee=body.assignee,
        ),
    )


@router.post("/quests/{quest_id}/complete", response_model=None)
async def sect_quest_complete(
    quest_id: str,
    body: SectQuestCompleteRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """完成宗门任务。"""
    return success(
        await svc.complete_quest(
            current_user,
            quest_id=quest_id,
            assignee=body.assignee,
        ),
    )


@router.get("/shop", response_model=None)
async def sect_shop(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """贡献商店列表。"""
    return success(await svc.list_shop(current_user))


@router.post("/shop/buy", response_model=None)
async def sect_shop_buy(
    body: SectShopBuyRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """贡献商店购买。"""
    return success(await svc.buy_shop(current_user, item_id=body.item_id))


@router.get("/soul-lamps", response_model=None)
async def sect_soul_lamps(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """魂灯列表。"""
    return success(await svc.list_soul_lamps(current_user))


@router.get("/exchange/catalog", response_model=None)
async def sect_exchange_catalog(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兑宠目录。"""
    return success(await svc.exchange_catalog(current_user))


@router.post("/exchange/pet", response_model=None)
async def sect_exchange_pet(
    body: SectPetExchangeRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """宗门兑宠。"""
    return success(await svc.exchange_pet(current_user, species_id=body.species_id))
