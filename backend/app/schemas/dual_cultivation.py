"""双修 HTTP DTO（M7 L7）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DualInviteRequest(BaseModel):
    """发起双修邀约。"""

    technique_id: str = Field(description="双修功法 id")
    target_character_id: int | None = None
    target_name: str | None = None
    # 测用可选种子；线上可忽略
    dice_seed: int | None = None


class DualSetGenderRequest(BaseModel):
    """存量角色一次性补选性别。"""

    gender: str = Field(description="male | female")


class DualRollRequest(BaseModel):
    """掷骰（可选强制种子，仅测/GM）。"""

    dice_seed: int | None = None
