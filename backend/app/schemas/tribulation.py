"""渡劫 API Schema（M5）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class TribulationPrepRequest(BaseModel):
    """``PUT /tribulation/prep`` 请求体。"""

    slots: list[dict[str, Any]] | None = Field(
        default=None,
        description="准备格列表：护劫道具顺序与引用（轴 B 承伤）",
    )
    formation_id: str | None = Field(default=None, description="渡劫阵法 id（轴 A 威力）")
    veil_chosen: bool | None = Field(default=None, description="是否启用遮天道具")
    # 前端别名，归一到 veil_chosen
    veil_selected: bool | None = Field(default=None, description="veil_chosen 前端别名")

    @model_validator(mode="after")
    def merge_veil_alias(self) -> TribulationPrepRequest:
        """Accept ``veil_selected`` as alias of ``veil_chosen``."""
        if self.veil_chosen is None and self.veil_selected is not None:
            self.veil_chosen = self.veil_selected
        return self


class TribulationResolveBatchRequest(BaseModel):
    """``POST /tribulation/resolve-batch`` 可选批次大小。"""

    batch_size: int | None = Field(
        default=None,
        ge=1,
        le=10000,
        description="本批结算雷击数；空则服务端默认",
    )
