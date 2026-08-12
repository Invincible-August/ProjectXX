"""
遗留：旧即时单挑会话 ORM（玩家 API 已移除；表保留供清理遗留行）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DaoChallengeSession(Base):
    """Legacy dao-lord single-challenge session row (no longer created by player APIs)."""

    __tablename__ = "dao_challenge_sessions"
    __table_args__ = (
        Index("ix_dao_challenge_dao_phase", "dao_id", "phase"),
        Index("ix_dao_challenge_challenger", "challenger_character_id", "phase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    challenger_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    lord_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # pending | running | finished
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # challenger_win | lord_win | abort | disconnect_loss | null
    result: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    battle_report_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
