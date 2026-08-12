"""后台运营路由：``/admin/ops/*``（运行时干预，含剔除道主）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_api.deps import get_current_admin
from app.db.models import AdminUser
from app.db.session import get_db
from app.schemas.common import success
from app.services.admin_ops_service import AdminOpsService

router = APIRouter(prefix="/ops", tags=["admin-ops"])


class RemoveDaoLordRequest(BaseModel):
    """剔除道主请求。"""

    note: str | None = Field(default=None, max_length=500, description="运营备注")


class ForceStartContestRequest(BaseModel):
    """立刻开赛请求。"""

    note: str | None = Field(default=None, max_length=500, description="运营备注")


class ReopenContestRequest(BaseModel):
    """重新开放报名请求。"""

    note: str | None = Field(default=None, max_length=500, description="运营备注")


class AdvanceArenaRequest(BaseModel):
    """跳过等待推进擂台请求。"""

    note: str | None = Field(default=None, max_length=500, description="运营备注")
    until_playing: bool = Field(
        default=True,
        description="True=连续跳过直至对战演出或收口；False=只推进一步",
    )


def get_admin_ops_service(session: AsyncSession = Depends(get_db)) -> AdminOpsService:
    """注入运营服务。"""
    return AdminOpsService(session)


@router.get("/dao-lords", response_model=None)
async def list_dao_lords(
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminOpsService = Depends(get_admin_ops_service),
) -> dict:
    """
    各道道主一览（含虚位）。

    权限：viewer 及以上。
    """
    return success(await svc.list_dao_lords(admin))


@router.post("/dao-lords/{dao_id}/remove", response_model=None)
async def remove_dao_lord(
    dao_id: str,
    body: RemoveDaoLordRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminOpsService = Depends(get_admin_ops_service),
) -> dict:
    """
    剔除该道现任道主，席位变为空缺。

    权限：publisher / admin。写审计 ``ops.dao_lord.remove``。
    """
    payload = body or RemoveDaoLordRequest()
    data = await svc.remove_dao_lord(admin, dao_id=dao_id, note=payload.note)
    return success(data)


@router.get("/dao-contests/current", response_model=None)
async def get_dao_contest(
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminOpsService = Depends(get_admin_ops_service),
) -> dict:
    """当前道主之争赛会状态。"""
    return success(await svc.get_dao_contest(admin))


@router.post("/dao-contests/force-start", response_model=None)
async def force_start_dao_contest(
    body: ForceStartContestRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminOpsService = Depends(get_admin_ops_service),
) -> dict:
    """立刻开赛（关闭报名进入 RSVP/擂台）。须 status=registration。"""
    payload = body or ForceStartContestRequest()
    data = await svc.force_start_dao_contest(admin, note=payload.note)
    return success(data)


@router.post("/dao-contests/reopen", response_model=None)
async def reopen_dao_contest(
    body: ReopenContestRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminOpsService = Depends(get_admin_ops_service),
) -> dict:
    """
    重新开放报名（联调）：清空本场报名/对阵，拉长报名窗。

    权限：publisher / admin。审计 ``ops.dao_contest.reopen``。
    """
    payload = body or ReopenContestRequest()
    data = await svc.reopen_dao_contest(admin, note=payload.note)
    return success(data)


@router.post("/dao-contests/advance-arena", response_model=None)
async def advance_dao_contest_arena(
    body: AdvanceArenaRequest | None = None,
    admin: AdminUser = Depends(get_current_admin),
    svc: AdminOpsService = Depends(get_admin_ops_service),
) -> dict:
    """
    跳过整备/倒计时/轮间/直播等待，推进至对战演出（或收口）。

    权限：publisher / admin。审计 ``ops.dao_contest.advance_arena``。
    """
    payload = body or AdvanceArenaRequest()
    data = await svc.advance_dao_contest_arena(
        admin,
        note=payload.note,
        until_playing=payload.until_playing,
    )
    return success(data)
