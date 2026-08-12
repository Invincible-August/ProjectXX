"""布阵与快照 API Schema（M3）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UnitPlacement(BaseModel):
    """单个棋子的占位（进攻方视角坐标）。"""

    unit_uid: str = Field(description="棋子唯一标识（main / puppet_1 / pet_3 / ...）")
    unit_kind: str = Field(description="棋子种类：main / puppet / pet / avatar / prop")
    x: int = Field(ge=0, le=6, description="横坐标（左下为 0）")
    y: int = Field(ge=0, le=6, description="纵坐标（左下为 0）")
    # M4：灵宠 / 化身 / 真傀儡持有物引用；试炼木傀可空
    ref_id: int | None = Field(default=None, description="持有物主键（pet.id / avatar.id / inventory.id）")


class SavePresetRequest(BaseModel):
    """``PUT /formation/presets/{slot}`` 请求体。"""

    name: str = Field(default="", max_length=20, description="预设名（空则保留原名）")
    role: str = Field(default="attack", description="定位：attack / defense / temp")
    formation_id: str = Field(default="none", description="阵法 id（none 表示无阵法）")
    units: list[UnitPlacement] = Field(description="占位列表（必须含唯一本体）")


class ValidatePlacementRequest(BaseModel):
    """``POST /formation/validate`` 请求体（编辑器干跑校验）。"""

    formation_id: str = Field(default="none", description="阵法 id")
    units: list[UnitPlacement] = Field(description="待校验占位列表")
