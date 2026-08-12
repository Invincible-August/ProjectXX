"""
道友 / 交易相关 ORM（M7 L2）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Friendship(Base):
    """道友关系：申请→确认→active；一对角色唯一。"""

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint(
            "character_low_id",
            "character_high_id",
            name="uq_friendships_pair",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 规范化小/大 id，便于唯一约束
    character_low_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_high_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 申请方
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # pending / active / rejected / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class TradeListing(Base):
    """交易行一口价 / 以物易物挂单。"""

    __tablename__ = "trade_listings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # fixed_price | barter
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="fixed_price")
    # 卖方托管物品 JSON：[{item_id, quantity}]
    offer_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 一口价灵石；易物可为 0
    price_spirit_stones: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 易物索要物品 JSON
    ask_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # open / sold / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    fee_paid: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    buyer_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AuctionLot(Base):
    """拍卖行拍品（仅灵石出价）。"""

    __tablename__ = "auction_lots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offer_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    start_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    current_price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    current_bidder_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # open / sold / unsold / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class AuctionBid(Base):
    """拍卖出价流水（审计）。"""

    __tablename__ = "auction_bids"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lot_id: Mapped[int] = mapped_column(
        ForeignKey("auction_lots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bidder_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FaceTradeSession(Base):
    """面对面交易会话。"""

    __tablename__ = "face_trade_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    initiator_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    peer_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # pending_invite / browsing / locking / confirming / committed / cancelled / expired
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending_invite",
        index=True,
    )
    # 乐观锁版本：改草稿报价 / 锁定 / 确认 时 +1
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    initiator_offer_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    peer_offer_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 0/1：锁定后才托管；草稿阶段仅写 JSON
    initiator_locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peer_locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    initiator_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peer_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class CurrencyLedger(Base):
    """六币种流水占位（L2 先写 spirit_stones；系统回收 character_id 为空）。"""

    __tablename__ = "currency_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # null = 系统回收池
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(32), nullable=False, default="spirit_stones")
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    note_zh: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
