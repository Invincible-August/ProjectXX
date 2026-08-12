"""商业化 HTTP DTO（M7 L8）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommerceMembershipRequest(BaseModel):
    """开通 / 续费会员。"""

    tier: str = Field(description="tier1 | tier2")


class CommerceBuyRequest(BaseModel):
    """天道商店购买。"""

    item_id: str = Field(description="货架 id")


class CommerceSandboxGrantRequest(BaseModel):
    """沙盒发放天道点。"""

    amount: int = Field(default=500, ge=1, description="发放数量")
