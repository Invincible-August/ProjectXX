"""体质 API Schema（M2）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConstitutionEquipRequest(BaseModel):
    """镶嵌请求。"""

    item_id: int
    slot_type: str
    slot_index: int = Field(default=0, ge=0)


class ConstitutionUnequipRequest(BaseModel):
    """卸下请求。"""

    slot_type: str
    slot_index: int = Field(default=0, ge=0)


class ConstitutionUpgradeRequest(BaseModel):
    """升品占位请求。"""

    item_id: int


class ConstitutionFuseRequest(BaseModel):
    """融合占位请求。"""

    item_ids: list[int] = Field(..., min_length=2)
