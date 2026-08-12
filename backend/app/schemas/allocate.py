"""资源分配 API Schema（M2）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AllocateRequest(BaseModel):
    """``POST /allocate`` 请求体。"""

    target_type: str = Field(..., description="realm | technique")
    target_id: str | None = None
    amount: int = Field(..., ge=1)
