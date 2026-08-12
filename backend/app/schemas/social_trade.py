"""道友 / 交易 HTTP DTO（M7 L2）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FriendApplyRequest(BaseModel):
    """申请道友。"""

    target_character_id: int | None = Field(default=None, description="目标角色 id")
    target_name: str | None = Field(default=None, description="目标道号（与 id 二选一）")


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


class AuctionCreateRequest(BaseModel):
    """上架拍卖。"""

    offer_items: list[TradeItemLine] = Field(default_factory=list)
    start_price: int = Field(default=1, ge=1)
    duration_sec: int | None = Field(default=None, ge=60)


class AuctionBidRequest(BaseModel):
    """拍卖出价。"""

    amount: int = Field(ge=1)


class FaceTradeInviteRequest(BaseModel):
    """发起面交。"""

    peer_character_id: int | None = None
    peer_name: str | None = None


class FaceTradeOfferRequest(BaseModel):
    """更新面交报价。"""

    items: list[TradeItemLine] = Field(default_factory=list)
    spirit_stones: int = Field(default=0, ge=0)
    version: int = Field(ge=1, description="客户端持有的会话版本")


class FaceTradeConfirmRequest(BaseModel):
    """确认面交。"""

    version: int = Field(ge=1)


class FaceTradeLockRequest(BaseModel):
    """锁定己方面交报价（托管）。"""

    version: int = Field(ge=1, description="客户端持有的会话版本")
