"""M4 工坊 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CraftStartRequest(BaseModel):
    """POST /craft/start 请求体。"""

    recipe_id: str
    actor: str = Field(default="main", description="main | avatar")
    use_dao: bool = Field(default=False, description="是否耗道值运用本命道（M6）")


class CraftClaimRequest(BaseModel):
    """POST /craft/claim 请求体。"""

    job_id: int
