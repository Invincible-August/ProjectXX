"""
M1-D30：Idempotency-Key 复用首次响应。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.idempotency import clear_idempotency_store, run_with_idempotency


class _FakeRequest:
    """Minimal request stub with headers."""

    def __init__(self, key: str | None) -> None:
        self.headers = {"Idempotency-Key": key} if key else {}


def test_idempotency_reuses_first_result() -> None:
    clear_idempotency_store()
    calls = {"n": 0}

    async def action() -> dict[str, Any]:
        calls["n"] += 1
        return {"code": 0, "data": {"n": calls["n"]}}

    async def _body() -> None:
        req = _FakeRequest("k-1")
        first = await run_with_idempotency(
            request=req,  # type: ignore[arg-type]
            user_id=1,
            action=action,
        )
        second = await run_with_idempotency(
            request=req,  # type: ignore[arg-type]
            user_id=1,
            action=action,
        )
        assert first == second
        assert calls["n"] == 1

    asyncio.run(_body())
    clear_idempotency_store()


def test_idempotency_without_key_always_runs() -> None:
    clear_idempotency_store()
    calls = {"n": 0}

    async def action() -> dict[str, Any]:
        calls["n"] += 1
        return {"code": 0, "data": {"n": calls["n"]}}

    async def _body() -> None:
        req = _FakeRequest(None)
        await run_with_idempotency(
            request=req,  # type: ignore[arg-type]
            user_id=2,
            action=action,
        )
        await run_with_idempotency(
            request=req,  # type: ignore[arg-type]
            user_id=2,
            action=action,
        )
        assert calls["n"] == 2

    asyncio.run(_body())
    clear_idempotency_store()
