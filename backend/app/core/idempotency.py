"""
请求幂等缓存（M1-D30）：同一用户 + Idempotency-Key 复用首次成功响应。

个人版默认内存表；进程重启后清空（可接受）。测试可调用 ``clear_idempotency_store``。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)

# (user_id, key) → 首次成功信封（dict）
_store: dict[tuple[int, str], dict[str, Any]] = {}
# 防膨胀：单用户最多保留条数
_MAX_KEYS_PER_USER = 64


def clear_idempotency_store() -> None:
    """清空幂等缓存（单测 / GM）。"""
    _store.clear()


def _trim_user(user_id: int) -> None:
    """Keep at most ``_MAX_KEYS_PER_USER`` entries per user (drop oldest insertion order)."""
    keys = [k for k in _store if k[0] == user_id]
    overflow = len(keys) - _MAX_KEYS_PER_USER
    if overflow <= 0:
        return
    for stale in keys[:overflow]:
        _store.pop(stale, None)


async def run_with_idempotency(
    *,
    request: Request,
    user_id: int,
    action: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """
    若请求带 ``Idempotency-Key``，则对同一用户复用首次成功结果。

    Args:
        request: FastAPI request（读 header）。
        user_id: 当前用户 id。
        action: 实际业务协程，须返回可 JSON 序列化的信封 dict。

    Returns:
        dict: 业务响应（首次或缓存）。
    """
    raw_key = request.headers.get("Idempotency-Key") or request.headers.get(
        "idempotency-key",
    )
    key = (raw_key or "").strip()
    if not key:
        return await action()

    cache_key = (int(user_id), key[:128])
    cached = _store.get(cache_key)
    if cached is not None:
        logger.info("idempotency hit user_id=%s key=%s", user_id, key[:32])
        return cached

    result = await action()
    # 仅缓存业务成功信封（code==0）；业务失败（如突破失败）也缓存，避免双扣费
    _store[cache_key] = result
    _trim_user(int(user_id))
    return result
