"""突破 API Schema（M1 + M5-D05 真读条）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BreakthroughAttemptRequest(BaseModel):
    """``POST /breakthrough/attempt`` / ``channel/start`` 请求体（可选确认）。"""

    confirm: bool = Field(default=True, description="前端确认标记")
