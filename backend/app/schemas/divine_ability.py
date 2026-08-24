"""神通 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DivineAbilityEquipRequest(BaseModel):
    """装备已学神通。"""

    ability_id: str
    slot_index: int = Field(default=0, ge=0)
    actor: str = Field(default="main")


class DivineAbilityUnequipRequest(BaseModel):
    """卸下神通槽。"""

    slot_index: int = Field(default=0, ge=0)
    actor: str = Field(default="main")
