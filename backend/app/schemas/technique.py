"""功法 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TechniqueEquipRequest(BaseModel):
    """装备主功法或技法。"""

    technique_id: str
    slot_type: str
    slot_index: int = Field(default=0, ge=0)
    actor: str = Field(default="main")


class TechniqueUnequipRequest(BaseModel):
    """卸下功法槽。"""

    slot_type: str
    slot_index: int = Field(default=0, ge=0)
    actor: str = Field(default="main")
