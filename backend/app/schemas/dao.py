"""大道 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DaoOpenChooseRequest(BaseModel):
    """POST /dao/open/choose。"""

    dao_id: str = Field(..., description="选定本命道 id")
    session_id: str | None = Field(default=None, description="开道会话 id（可选校验）")


class DaoUsagePreviewRequest(BaseModel):
    """POST /dao/usage/preview。"""

    kind: str = Field(..., description="battle | craft")
