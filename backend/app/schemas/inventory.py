"""M4 背包 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InventoryUseRequest(BaseModel):
    """POST /inventory/use 请求体。"""

    item_uid: str
    quantity: int = Field(default=1, ge=1)


class InventoryMoveBagRequest(BaseModel):
    """POST /inventory/move-bag 请求体。"""

    item_uid: str = Field(..., min_length=1, description="物品 uid")
    target_bag: str = Field(
        ...,
        description="目标袋：normal / reincarnation",
    )
