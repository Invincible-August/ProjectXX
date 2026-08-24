"""后台玩家角色路由：``/admin/ops/characters/*``。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_api.deps import get_current_admin
from app.db.models import AdminUser
from app.db.session import get_db
from app.schemas.common import success
from app.services.admin_character_service import AdminCharacterService

router = APIRouter(prefix="/ops/characters", tags=["admin-characters"])


class NoteRequest(BaseModel):
    """可选备注。"""

    note: str | None = Field(default=None, max_length=500)


class GrantItemRequest(BaseModel):
    """邮件给予物品种类。"""

    item_id: str = Field(min_length=1, max_length=64, description="物品种类 id")
    quantity: int = Field(default=1, ge=1, description="数量")
    note: str | None = Field(default=None, max_length=500)


class BaseAttrsRequest(BaseModel):
    """基础属性批量写入。"""

    attrs: dict[str, float | int] = Field(description="属性键 → 数值")


class StatusRequest(BaseModel):
    """条件状态。"""

    status: str = Field(min_length=1, max_length=32)


class InventoryUpdateRequest(BaseModel):
    """背包行修改。"""

    quantity: int | None = Field(default=None, ge=1)
    meta: dict[str, Any] | None = None
    delete: bool = False


class TechniqueLevelRequest(BaseModel):
    """功法等级。"""

    level: int = Field(ge=0)


class LearnTechniqueRequest(BaseModel):
    """学会功法。"""

    technique_id: str = Field(min_length=1, max_length=64)
    level: int = Field(default=0, ge=0)


class RealmUpdateRequest(BaseModel):
    """境界修改。"""

    track: str = Field(description="cultivation | body")
    major: str | None = None
    stage: int | None = Field(default=None, ge=1)
    progress: int | None = Field(default=None, ge=0)
    pool_points: int | None = Field(default=None, ge=0)


class CraftLevelsRequest(BaseModel):
    """制造业等级。"""

    levels: dict[str, int] = Field(description="branch → level")


class LearnRecipeRequest(BaseModel):
    """学会配方。"""

    recipe_id: str = Field(min_length=1, max_length=64)


class CurrenciesRequest(BaseModel):
    """货币绝对值（整数 ≥0）。"""

    amounts: dict[str, int] = Field(description="currency key → amount")


def get_admin_character_service(
    session: AsyncSession = Depends(get_db),
) -> AdminCharacterService:
    """注入角色运营服务。"""
    return AdminCharacterService(session)


@router.get("/schema", response_model=None)
async def character_ops_schema(
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """角色运营字段中文契约。权限：viewer+。"""
    return success(svc.get_ops_schema(admin))


@router.get("", response_model=None)
async def list_characters(
    q: str | None = Query(default=None, description="道号/user_id/邮箱关键字"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20),
    user_db_id: int | None = Query(default=None, description="按账号数据库 id 过滤"),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """角色分页列表。权限：viewer+。"""
    return success(
        await svc.list_characters(
            admin,
            q=q,
            page=page,
            page_size=page_size,
            user_db_id=user_db_id,
        ),
    )


@router.get("/{character_id}", response_model=None)
async def get_character(
    character_id: int,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """角色详情。权限：viewer+。"""
    return success(await svc.get_detail(admin, character_id))


@router.post("/{character_id}/soft-delete", response_model=None)
async def soft_delete_character(
    character_id: int,
    body: NoteRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """软删角色。权限：publisher/admin。"""
    payload = body or NoteRequest()
    return success(await svc.soft_delete(admin, character_id, note=payload.note))


@router.post("/{character_id}/kill", response_model=None)
async def kill_character(
    character_id: int,
    body: NoteRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """死亡 → 待引渡。权限：publisher/admin。"""
    payload = body or NoteRequest()
    return success(await svc.kill_to_ferry(admin, character_id, note=payload.note))


@router.post("/{character_id}/reincarnate", response_model=None)
async def reincarnate_character(
    character_id: int,
    body: NoteRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """强制轮回。权限：publisher/admin。"""
    payload = body or NoteRequest()
    return success(await svc.force_reincarnation(admin, character_id, note=payload.note))


@router.post("/{character_id}/breakthrough/cultivation", response_model=None)
async def breakthrough_cultivation(
    character_id: int,
    body: NoteRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修为强制小境界突破。权限：publisher/admin。"""
    payload = body or NoteRequest()
    return success(
        await svc.breakthrough_cultivation(admin, character_id, note=payload.note),
    )


@router.post("/{character_id}/breakthrough/body", response_model=None)
async def breakthrough_body(
    character_id: int,
    body: NoteRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """炼体强制小境界突破。权限：publisher/admin。"""
    payload = body or NoteRequest()
    return success(
        await svc.breakthrough_body_temper(admin, character_id, note=payload.note),
    )


@router.post("/{character_id}/grant-item", response_model=None)
async def grant_item(
    character_id: int,
    body: GrantItemRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """邮件给予物品种类。权限：publisher/admin。"""
    return success(
        await svc.grant_item_mail(
            admin,
            character_id,
            item_id=body.item_id,
            quantity=body.quantity,
            note=body.note,
        ),
    )


@router.post("/{character_id}/base-attrs", response_model=None)
async def update_base_attrs(
    character_id: int,
    body: BaseAttrsRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改基础属性。权限：publisher/admin。"""
    return success(await svc.update_base_attrs(admin, character_id, attrs=body.attrs))


@router.post("/{character_id}/status", response_model=None)
async def update_status(
    character_id: int,
    body: StatusRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改条件状态。权限：publisher/admin。"""
    return success(await svc.update_status(admin, character_id, status=body.status))


@router.post("/{character_id}/inventory/{item_row_id}", response_model=None)
async def update_inventory(
    character_id: int,
    item_row_id: int,
    body: InventoryUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改/删除背包物品。权限：publisher/admin。"""
    return success(
        await svc.update_inventory_item(
            admin,
            character_id,
            item_row_id,
            quantity=body.quantity,
            meta=body.meta,
            delete=body.delete,
        ),
    )


@router.post("/{character_id}/techniques/learn", response_model=None)
async def learn_technique(
    character_id: int,
    body: LearnTechniqueRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """学会功法。权限：publisher/admin。"""
    return success(
        await svc.learn_technique(
            admin,
            character_id,
            technique_id=body.technique_id,
            level=body.level,
        ),
    )


@router.post("/{character_id}/techniques/{technique_id}/forget", response_model=None)
async def forget_technique(
    character_id: int,
    technique_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """遗忘功法。权限：publisher/admin。"""
    return success(await svc.forget_technique(admin, character_id, technique_id))


@router.post("/{character_id}/techniques/{technique_id}", response_model=None)
async def update_technique(
    character_id: int,
    technique_id: str,
    body: TechniqueLevelRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改功法等级。权限：publisher/admin。"""
    return success(
        await svc.update_technique_level(
            admin,
            character_id,
            technique_id,
            level=body.level,
        ),
    )

@router.post("/{character_id}/realm", response_model=None)
async def update_realm(
    character_id: int,
    body: RealmUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改境界。权限：publisher/admin。"""
    return success(
        await svc.update_realm(
            admin,
            character_id,
            track=body.track,
            major=body.major,
            stage=body.stage,
            progress=body.progress,
            pool_points=body.pool_points,
        ),
    )


@router.post("/{character_id}/craft-levels", response_model=None)
async def update_craft_levels(
    character_id: int,
    body: CraftLevelsRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改制造业等级。权限：publisher/admin。"""
    return success(
        await svc.update_craft_levels(admin, character_id, levels=body.levels),
    )


@router.post("/{character_id}/recipes/learn", response_model=None)
async def learn_recipe(
    character_id: int,
    body: LearnRecipeRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """学会配方。权限：publisher/admin。"""
    return success(
        await svc.learn_recipe(admin, character_id, recipe_id=body.recipe_id),
    )


@router.post("/{character_id}/recipes/{recipe_id}/forget", response_model=None)
async def forget_recipe(
    character_id: int,
    recipe_id: str,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """遗忘配方。权限：publisher/admin。"""
    return success(await svc.forget_recipe(admin, character_id, recipe_id))


@router.post("/{character_id}/currencies", response_model=None)
async def update_currencies(
    character_id: int,
    body: CurrenciesRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminCharacterService = Depends(get_admin_character_service),
) -> dict:
    """修改货币（不含仙缘）。权限：publisher/admin。"""
    return success(
        await svc.update_currencies(admin, character_id, amounts=body.amounts),
    )
