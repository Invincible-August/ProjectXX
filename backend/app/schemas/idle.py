"""挂机 API 请求 / 响应 Schema（M1）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IdleDirectionRequest(BaseModel):
    """``POST /idle/direction`` 请求体。"""

    direction: Literal["none", "spirit", "body", "crafting"] = Field(
        ...,
        description="挂机方向",
    )


class IdleSyncResponseData(BaseModel):
    """挂机 sync / direction 响应 data（文档用；实际由 dict 返回）。"""

    character: dict[str, Any]
    settled_ticks: int
    gained_cultivation: int
    spent_spirit_stones: int
    next_tick_at: str | None = None
