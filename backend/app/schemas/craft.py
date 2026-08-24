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


class TalismanScribeRequest(BaseModel):
    """POST /craft/talisman/scribe."""

    template_id: str
    quantity: int = Field(default=1, ge=1, le=99)


class TalismanPreloadRequest(BaseModel):
    """PUT /craft/talisman/preload."""

    inventory_item_ids: list[int] = Field(default_factory=list)
