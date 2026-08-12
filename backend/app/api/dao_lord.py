"""道主 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_dao_contest_service, get_dao_lord_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.dao_lord import (
    DaoContestArenaLeaveRequest,
    DaoContestRsvpRequest,
    DaoLordClaimRequest,
)
from app.services.dao_contest_service import DaoContestService
from app.services.dao_lord_service import DaoLordService

router = APIRouter(prefix="/dao-lord", tags=["dao-lord"])


@router.get("/board")
async def dao_lord_board(
    user: User = Depends(get_current_user),
    service: DaoLordService = Depends(get_dao_lord_service),
) -> dict:
    """道主榜。"""
    return success(await service.get_board(user))


@router.get("/windows")
async def dao_lord_windows(
    user: User = Depends(get_current_user),
    contest_svc: DaoContestService = Depends(get_dao_contest_service),
    lord_svc: DaoLordService = Depends(get_dao_lord_service),
) -> dict:
    """开窗状态（优先映射赛会日程）。"""
    try:
        payload = await contest_svc.get_current(user)
        return success({"window": contest_svc.window_compat_payload(payload)})
    except Exception:  # noqa: BLE001
        return success({"window": await lord_svc.get_windows(user)})


@router.get("/contests/current")
async def dao_contest_current(
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """本场道主之争状态与报名摘要。"""
    return success(await service.get_current(user))


@router.post("/contests/current/register")
async def dao_contest_register(
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """报名道主之争。"""
    return success(await service.register(user))


@router.delete("/contests/current/register")
async def dao_contest_unregister(
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """取消报名。"""
    return success(await service.unregister(user))


@router.post("/contests/current/rsvp")
async def dao_contest_rsvp(
    payload: DaoContestRsvpRequest,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """开赛入席确认：accept=true 进擂台；报名者拒绝=弃权；道主拒绝=快照。"""
    return success(await service.submit_rsvp(user, accept=payload.accept))


@router.get("/contests/current/arena")
async def dao_contest_arena(
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """擂台页状态。"""
    return success(await service.get_arena(user))


@router.post("/contests/current/arena/enter")
async def dao_contest_arena_enter(
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """标记进入擂台。"""
    return success(await service.arena_enter(user))


@router.post("/contests/current/arena/leave")
async def dao_contest_arena_leave(
    payload: DaoContestArenaLeaveRequest | None = None,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """离开擂台；判负与否由服务端根据场次状态权威决定（忽略客户端开关）。"""
    _ = payload
    return success(await service.arena_leave(user))


@router.get("/contests/current/bracket")
async def dao_contest_bracket(
    dao_id: str | None = None,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """本场对阵树（可选按道过滤）。"""
    return success(await service.get_bracket(user, dao_id=dao_id))


@router.get("/contests/matches/{match_id}")
async def dao_contest_match(
    match_id: int,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """单场对阵摘要。"""
    return success(await service.get_match(user, match_id))


@router.get("/contests/matches/{match_id}/report")
async def dao_contest_match_report(
    match_id: int,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """单场战报（回放 / 直播同源日志）。"""
    return success(await service.get_match_report(user, match_id))


@router.get("/contests/matches/{match_id}/live")
async def dao_contest_match_live(
    match_id: int,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """直播时钟：准备倒计时 / 对战节拍；观众准备阶段无布阵。"""
    return success(await service.get_live_state(user, match_id))


@router.post("/contests/matches/{match_id}/spectate")
async def dao_contest_spectate(
    match_id: int,
    user: User = Depends(get_current_user),
    service: DaoContestService = Depends(get_dao_contest_service),
) -> dict:
    """占用单直播槽观战（半决/决赛/道主战直播窗内）。"""
    return success(await service.spectate_match(user, match_id))


@router.post("/claim")
async def dao_lord_claim(
    payload: DaoLordClaimRequest,
    user: User = Depends(get_current_user),
    service: DaoLordService = Depends(get_dao_lord_service),
) -> dict:
    """空位自动就任（兼容）。"""
    data = await service.claim(user, dao_id=payload.dao_id)
    return success(data)
