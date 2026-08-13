"""道友 / 交易 HTTP DTO（M7 L2）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.int_money import require_non_negative_int


class FriendApplyRequest(BaseModel):
    """申请道友。"""

    target_character_id: int | None = Field(default=None, description="目标角色 id")
    target_name: str | None = Field(default=None, description="目标道号（与 id 二选一）")


class CompanionApplyRequest(BaseModel):
    """申请道侣。"""

    target_character_id: int | None = Field(default=None, description="目标角色 id")
    target_name: str | None = Field(default=None, description="目标道号（与 id 二选一）")


class FriendPrivacyUpdateRequest(BaseModel):
    """道友资料可见开关。"""

    friend_profile_visible: bool = Field(description="True=允许道友查看；False=遮掩天机")


class TradeItemLine(BaseModel):
    """物品行。"""

    item_id: str
    quantity: int = Field(ge=1)


class TradeListingCreateRequest(BaseModel):
    """上架交易行。"""

    mode: str = Field(default="fixed_price", description="fixed_price | barter")
    offer_items: list[TradeItemLine] = Field(default_factory=list)
    price_spirit_stones: int = Field(default=0, ge=0)
    ask_items: list[TradeItemLine] = Field(default_factory=list)

    @field_validator("price_spirit_stones", mode="before")
    @classmethod
    def _price_int(cls, value: Any) -> int:
        return require_non_negative_int(value, field_zh="灵石标价")


class AuctionCreateRequest(BaseModel):
    """上架拍卖。"""

    offer_items: list[TradeItemLine] = Field(default_factory=list)
    start_price: int = Field(default=1, ge=1)
    duration_sec: int | None = Field(default=None, ge=60)

    @field_validator("start_price", mode="before")
    @classmethod
    def _start_price_int(cls, value: Any) -> int:
        n = require_non_negative_int(value, field_zh="起拍灵石")
        if n < 1:
            raise ValueError("起拍灵石须 ≥ 1")
        return n


class AuctionBidRequest(BaseModel):
    """拍卖出价。"""

    amount: int = Field(ge=1)

    @field_validator("amount", mode="before")
    @classmethod
    def _bid_int(cls, value: Any) -> int:
        n = require_non_negative_int(value, field_zh="出价灵石")
        if n < 1:
            raise ValueError("出价灵石须 ≥ 1")
        return n


class FaceTradeInviteRequest(BaseModel):
    """发起面交。"""

    peer_character_id: int | None = None
    peer_name: str | None = None


class FaceTradeVesselOffer(BaseModel):
    """面交炉鼎条款：愿为对方炉鼎 / 延长时限（现实小时）。"""

    hours: int = Field(ge=0, description="现实小时数（须为整数 ≥ 0）")

    @field_validator("hours", mode="before")
    @classmethod
    def _hours_int(cls, value: Any) -> int:
        return require_non_negative_int(value, field_zh="炉鼎时限")


class FaceTradeOfferRequest(BaseModel):
    """更新面交报价。"""

    items: list[TradeItemLine] = Field(default_factory=list)
    spirit_stones: int = Field(default=0, ge=0)
    vessel_offer: FaceTradeVesselOffer | None = Field(
        default=None,
        description="可选：愿为对方炉鼎（或延长）N 现实小时；双方至多一侧可设",
    )
    version: int = Field(ge=1, description="客户端持有的会话版本")

    @field_validator("spirit_stones", mode="before")
    @classmethod
    def _stones_int(cls, value: Any) -> int:
        return require_non_negative_int(value, field_zh="灵石")


class FaceTradeConfirmRequest(BaseModel):
    """确认面交。"""

    version: int = Field(ge=1)


class FaceTradeLockRequest(BaseModel):
    """锁定己方面交报价（托管）。"""

    version: int = Field(ge=1, description="客户端持有的会话版本")


class BazaarDealRequest(BaseModel):
    """坊市购买或出售。"""

    item_id: str = Field(min_length=1, description="物品目录 id")
    quantity: int = Field(default=1, ge=1, description="数量")
