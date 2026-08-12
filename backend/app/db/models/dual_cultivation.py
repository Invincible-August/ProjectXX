"""双修 ORM（M7 L7）：会话 + 四榜分。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DualCultivationSession(Base):
    """
    双修会话：inviting → confirmed → running → settled。

    亦可 cancelled / timeout / aborted。
    """

    __tablename__ = "dual_cultivation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technique_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # inviting | confirmed | running | settled | cancelled | timeout | aborted
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inviting", index=True)
    invite_expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 掷骰快照
    roll_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roll_lo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roll_hi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effect_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    yield_mult: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dice_label_zh: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rerolls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 结算摘要 JSON
    settle_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 可选复现种子（测用）
    dice_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DualRankScore(Base):
    """四榜累计分（按角色 + 榜键唯一）。"""

    __tablename__ = "dual_rank_scores"
    __table_args__ = (
        UniqueConstraint("character_id", "board_key", name="uq_dual_rank_board"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # male_number_one | male_zero | female_number_one | female_zero
    board_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
