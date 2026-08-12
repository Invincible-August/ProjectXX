"""
道友化身助战会话 ORM（AvatarAssistSession）。

生命周期：invited → active | rejected | expired；active → ended。
同一化身同时最多一条 active；邀请过期由服务惰性清理。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvatarAssistSession(Base):
    """
    Friend-avatar assist session (borrower invites owner's avatar).

    Status: invited | active | ended | rejected | expired.
    """

    __tablename__ = "avatar_assist_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 化身主人（被借方）
    owner_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 借用人（进攻方 / 编成归属）
    borrower_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 被借用的化身行
    avatar_id: Mapped[int] = mapped_column(
        ForeignKey("avatars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # invited | active | ended | rejected | expired
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="invited",
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
