"""轮回 API Schema（M5）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReincarnationPreviewRequest(BaseModel):
    """``POST /reincarnation/preview``。"""

    path: str = Field(default="altar", description="altar / voluntary_ferry / forced（self→voluntary_ferry）")


class ReincarnationAltarRequest(BaseModel):
    """``POST /reincarnation/altar`` 安全确认。"""

    confirm: bool = True


class ReincarnationShopBuyRequest(BaseModel):
    """``POST /reincarnation/shop/buy``。"""

    item_id: str = Field(..., min_length=1, description="商店商品 id")
    source: str = Field(
        default="fixed",
        description="货架来源：fixed=固定 / random=随机",
    )


class ReincarnationShopRefreshRequest(BaseModel):
    """``POST /reincarnation/shop/refresh``。"""

    currency: str = Field(
        default="points",
        description="刷新货币：points=轮回点 / fate_luck=仙缘",
    )


class ReincarnationCompleteNewbornRequest(BaseModel):
    """``POST /reincarnation/complete-newborn``。"""

    spirit_root_ids: list[str] = Field(
        default_factory=list,
        description="所选灵根 catalog id 列表",
    )
    legacy_ids: list[str] = Field(
        default_factory=list,
        description="免费槽所选传承 id（商店已购自动保留）",
    )
    constitution_path: str | None = Field(
        default=None,
        description="本世体质倾向 id；可空",
    )
