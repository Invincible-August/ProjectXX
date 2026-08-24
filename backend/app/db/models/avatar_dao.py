"""
化身本命道与道资源 ORM。

与 character_dao 独立：本体与化身可走不同大道、各有道值。
破除化身时随 avatars 行 CASCADE 删除。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvatarDao(Base):
    """化身大道状态：本命道、道值、经验、开道会话。"""

    __tablename__ = "avatar_dao"
    __table_args__ = (
        UniqueConstraint("avatar_id", name="uq_avatar_dao_avatar"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    avatar_id: Mapped[int] = mapped_column(
        ForeignKey("avatars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 本命道 id；未开道为 null
    fate_dao_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dao_qi: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dao_exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dao_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    opening_session_json: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    challenge_cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AvatarDaoPoolEntry(Base):
    """化身道池一条收藏（与本体道池互不影响）。"""

    __tablename__ = "avatar_dao_pool_entries"
    __table_args__ = (
        UniqueConstraint("avatar_id", "dao_id", name="uq_avatar_dao_pool_avatar_dao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    avatar_id: Mapped[int] = mapped_column(
        ForeignKey("avatars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
