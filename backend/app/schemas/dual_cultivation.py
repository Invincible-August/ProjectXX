"""双修 HTTP DTO（M7 L7）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DualInviteRequest(BaseModel):
    """发起双修邀约（仅道侣/炉鼎 + 角色 id）。"""

    technique_id: str = Field(description="双修功法 id")
    target_character_id: int = Field(description="对方角色 id")
    bond_kind: str = Field(description="companion | vessel")
    inviter_role: str | None = Field(
        default="number_one",
        description="邀请方角色位 number_one|zero，默认主动",
    )
    # 兼容旧客户端：若传入则服务端拒绝
    target_name: str | None = None
    # 测用可选种子；线上可忽略
    dice_seed: int | None = None


class DualSetGenderRequest(BaseModel):
    """存量角色一次性补选性别。"""

    gender: str = Field(description="male | female")


class DualRollRequest(BaseModel):
    """掷骰（可选强制种子，仅测/GM）。"""

    dice_seed: int | None = None
