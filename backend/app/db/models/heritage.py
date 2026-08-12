"""传承（红包）ORM（M7 L5）。"""

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


class HeritagePacket(Base):
    """频道内机缘包。"""

    __tablename__ = "heritage_packets"
    # SQLite 须 AUTOINCREMENT，避免 purge 后复用 id 导致客户端「已领完」脏缓存盖住新包
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    channel_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sender_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # random | fixed
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="fixed")
    share_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shares_claimed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spirit_stones_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 原始物品 JSON
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 预计算份列表 JSON：[{spirit_stones, items}]
    shares_plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 下一份下标（0-based）
    next_share_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # open | exhausted | expired
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    note_zh: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HeritageClaim(Base):
    """传承领取记录（同人限领靠唯一约束）。"""

    __tablename__ = "heritage_claims"
    __table_args__ = (
        UniqueConstraint("packet_id", "character_id", name="uq_heritage_claim_packet_char"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    packet_id: Mapped[int] = mapped_column(
        ForeignKey("heritage_packets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    share_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spirit_stones: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class HeritageDailyCounter(Base):
    """发传承日限额。"""

    __tablename__ = "heritage_daily_counters"
    __table_args__ = (
        UniqueConstraint("character_id", "day_key", name="uq_heritage_daily_char_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spirit_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
