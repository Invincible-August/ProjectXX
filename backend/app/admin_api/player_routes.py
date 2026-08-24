"""后台玩家账号路由：``/admin/ops/players/*``。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_api.deps import get_current_admin
from app.db.models import AdminUser
from app.db.session import get_db
from app.schemas.common import success
from app.services.admin_player_service import AdminPlayerService

router = APIRouter(prefix="/ops/players", tags=["admin-players"])


class BanPlayerRequest(BaseModel):
    """封号 / 解封。"""

    banned: bool = Field(default=True, description="True=封号，False=解封")
    note: str | None = Field(default=None, max_length=500)


class ResetPasswordRequest(BaseModel):
    """重置密码备注。"""

    note: str | None = Field(default=None, max_length=500)


class UpdateContactsRequest(BaseModel):
    """修改邮箱 / 手机。省略的字段不改；空串清空。"""

    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=500)


class GrantFateLuckRequest(BaseModel):
    """派发仙缘。"""

    amount: int = Field(ge=1, description="派发数量（正整数）")
    note: str | None = Field(default=None, max_length=500)


class CreateTipRequest(BaseModel):
    """记录打赏。"""

    paid_at: str = Field(description="打赏时间 YYYY-MM-DD HH:MM:SS")
    channel: str = Field(min_length=1, max_length=64, description="路径：微信/支付宝/自填")
    order_no: str = Field(min_length=1, max_length=128, description="订单号")
    amount: int = Field(ge=1, description="金额（正整数）")
    note: str | None = Field(default=None, max_length=500)


def get_admin_player_service(session: AsyncSession = Depends(get_db)) -> AdminPlayerService:
    """注入玩家账号运营服务。"""
    return AdminPlayerService(session)


@router.get("/schema", response_model=None)
async def player_ops_schema(
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """
    玩家运营字段中文契约（label_zh / help_zh）。

    对齐开发计划 §0.0.1；权限：viewer 及以上。
    """
    return success(svc.get_ops_schema(admin))


@router.get("", response_model=None)
async def list_players(
    q: str | None = Query(default=None, description="邮箱/手机/user_id 关键字"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, description="10/20/50/100"),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """玩家账号分页列表。权限：viewer 及以上。"""
    return success(await svc.list_accounts(admin, q=q, page=page, page_size=page_size))


@router.post("/{user_id}/ban", response_model=None)
async def ban_player(
    user_id: int,
    body: BanPlayerRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """封号或解封（路径 user_id=数据库自增 id）。权限：publisher / admin。"""
    payload = body or BanPlayerRequest()
    data = await svc.ban_account(
        admin,
        user_id=user_id,
        banned=payload.banned,
        note=payload.note,
    )
    return success(data)


class SoftDeleteRequest(BaseModel):
    """软删账号备注。"""

    note: str | None = Field(default=None, max_length=500)


class SetGmRequest(BaseModel):
    """设为 / 取消 GM。"""

    is_gm: bool = Field(default=True, description="True=设为GM，False=取消")
    note: str | None = Field(default=None, max_length=500)


@router.post("/{user_id}/soft-delete", response_model=None)
async def soft_delete_player(
    user_id: int,
    body: SoftDeleteRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """软删账号（is_active=false）。权限：publisher / admin。"""
    payload = body or SoftDeleteRequest()
    data = await svc.soft_delete_account(admin, user_id=user_id, note=payload.note)
    return success(data)


@router.post("/{user_id}/set-gm", response_model=None)
async def set_player_gm(
    user_id: int,
    body: SetGmRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """设为/取消 GM（功能暂未开放）。权限：publisher / admin。"""
    payload = body or SetGmRequest()
    data = await svc.set_gm(
        admin,
        user_id=user_id,
        is_gm=payload.is_gm,
        note=payload.note,
    )
    return success(data)


@router.post("/{user_id}/reset-password", response_model=None)
async def reset_player_password(
    user_id: int,
    body: ResetPasswordRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """重置密码为 12345678。权限：publisher / admin。"""
    payload = body or ResetPasswordRequest()
    data = await svc.reset_password(admin, user_id=user_id, note=payload.note)
    return success(data)


@router.post("/{user_id}/contacts", response_model=None)
async def update_player_contacts(
    user_id: int,
    body: UpdateContactsRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """修改邮箱 / 手机号。权限：publisher / admin。"""
    data = await svc.update_contacts(
        admin,
        user_id=user_id,
        email=body.email,
        phone=body.phone,
        note=body.note,
    )
    return success(data)


@router.post("/{user_id}/grant-fate-luck", response_model=None)
async def grant_player_fate_luck(
    user_id: int,
    body: GrantFateLuckRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """派发仙缘（同时写入派发流水）。权限：publisher / admin。"""
    data = await svc.grant_fate_luck(
        admin,
        user_id=user_id,
        amount=body.amount,
        note=body.note,
    )
    return success(data)


@router.post("/{user_id}/tips", response_model=None)
async def create_player_tip(
    user_id: int,
    body: CreateTipRequest,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """记录打赏并累加总打赏金额。权限：publisher / admin。"""
    data = await svc.create_tip_record(
        admin,
        user_id=user_id,
        paid_at=body.paid_at,
        channel=body.channel,
        order_no=body.order_no,
        amount=body.amount,
        note=body.note,
    )
    return success(data)


@router.get("/{user_id}/tips", response_model=None)
async def list_player_tips(
    user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """查看打赏记录。权限：viewer 及以上。"""
    return success(
        await svc.list_tip_records(admin, user_id=user_id, page=page, page_size=page_size),
    )


@router.get("/{user_id}/fate-luck-grants", response_model=None)
async def list_player_fate_luck_grants(
    user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """查看仙缘派发记录。权限：viewer 及以上。"""
    return success(
        await svc.list_fate_luck_grants(admin, user_id=user_id, page=page, page_size=page_size),
    )


@router.get("/{user_id}/ad-watches", response_model=None)
async def list_player_ad_watches(
    user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20),
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminPlayerService = Depends(get_admin_player_service),
) -> dict:
    """查看广告观看记录（广告未接入前多为空）。权限：viewer 及以上。"""
    return success(
        await svc.list_ad_watch_records(admin, user_id=user_id, page=page, page_size=page_size),
    )
