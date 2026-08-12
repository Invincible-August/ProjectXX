"""突破 HTTP 路由：预览 / 同步 attempt / 异步真读条（M5-D05）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.deps import get_breakthrough_service, get_current_user
from app.core.idempotency import run_with_idempotency
from app.db.models import User
from app.schemas.breakthrough import BreakthroughAttemptRequest
from app.schemas.common import success
from app.services.breakthrough_service import BreakthroughService

router = APIRouter(prefix="/breakthrough", tags=["breakthrough"])


@router.get("/preview", response_model=None)
async def preview_breakthrough(
    service: BreakthroughService = Depends(get_breakthrough_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    突破预览（settle + 懒结算读条后只读）。

    Args:
        service: 突破应用服务。
        current_user: 当前用户。

    Returns:
        dict: preview 信封（可含 ``channel``）。
    """
    data = await service.preview_breakthrough(current_user)
    return success(data)


@router.post("/attempt", response_model=None)
async def attempt_breakthrough(
    request: Request,
    payload: BreakthroughAttemptRequest | None = None,
    service: BreakthroughService = Depends(get_breakthrough_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    突破入口：``async_channel.enabled`` 时等价开读条，否则同步掷骰。

    支持 ``Idempotency-Key``：同一 Key 重复提交复用首次响应，不二次扣费。

    Args:
        request: 原始请求（读幂等头）。
        payload: 可选确认体。
        service: 突破应用服务。
        current_user: 当前用户。

    Returns:
        dict: attempt / channel-start 信封。
    """
    _ = payload

    async def _action() -> dict:
        data = await service.attempt_breakthrough(current_user)
        return success(data)

    return await run_with_idempotency(
        request=request,
        user_id=int(current_user.id),
        action=_action,
    )


@router.post("/channel/start", response_model=None)
async def start_breakthrough_channel(
    request: Request,
    payload: BreakthroughAttemptRequest | None = None,
    service: BreakthroughService = Depends(get_breakthrough_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    开异步真读条（闭关）；扣灵石并置 ``breaking_through``。

    Args:
        request: 原始请求（幂等）。
        payload: 可选确认体。
        service: 突破应用服务。
        current_user: 当前用户。

    Returns:
        dict: channel 进度 + character。
    """
    _ = payload

    async def _action() -> dict:
        data = await service.start_channel(current_user)
        return success(data)

    return await run_with_idempotency(
        request=request,
        user_id=int(current_user.id),
        action=_action,
    )


@router.get("/channel", response_model=None)
async def get_breakthrough_channel(
    service: BreakthroughService = Depends(get_breakthrough_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    查询读条进度；到期则懒结算并返回结果。

    Args:
        service: 突破应用服务。
        current_user: 当前用户。

    Returns:
        dict: ``channel`` + ``character``。
    """
    data = await service.get_channel(current_user)
    return success(data)


@router.post("/channel/resolve", response_model=None)
async def resolve_breakthrough_channel(
    request: Request,
    service: BreakthroughService = Depends(get_breakthrough_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    显式结算到期读条；未到期返回 409/40028。

    Args:
        request: 原始请求（幂等）。
        service: 突破应用服务。
        current_user: 当前用户。

    Returns:
        dict: 成败结果信封。
    """

    async def _action() -> dict:
        data = await service.resolve_channel(current_user)
        return success(data)

    return await run_with_idempotency(
        request=request,
        user_id=int(current_user.id),
        action=_action,
    )


@router.get("/grades/history", response_model=None)
async def grade_history(
    service: BreakthroughService = Depends(get_breakthrough_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """跨境品阶历史（最近 N 条）。"""
    items = await service.list_grade_history(current_user)
    return success({"items": items})
