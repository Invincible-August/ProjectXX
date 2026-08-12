"""
邮件 ORM（M7 L3）。

附件领取幂等：``claimed_at`` 非空则不可再领。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MailMessage(Base):
    """系统信 / 玩家信；附件 JSON 托管至领取。"""

    __tablename__ = "mail_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # system | player | gift
    mail_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="system", index=True)
    # 收件人
    to_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 发件人；系统信可为 null
    from_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 机读原因：gift / auction_unsold / trade_refund / player_mail / gift_receipt …
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    subject_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    body_zh: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 附件：{"spirit_stones": N, "items": [{"item_id","quantity"}]}
    attachments_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 是否已读（打开列表可标读；与领取独立）
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 附件领取时刻；幂等键
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class GiftDailyCounter(Base):
    """赠送日限额计数（按角色+UTC 日）。"""

    __tablename__ = "gift_daily_counters"
    __table_args__ = (
        UniqueConstraint("character_id", "day_key", name="uq_gift_daily_character_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # YYYY-MM-DD UTC
    day_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    gift_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spirit_value_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
