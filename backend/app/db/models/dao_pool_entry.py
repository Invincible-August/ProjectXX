"""
道池收藏 ORM：跨轮回保留。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DaoPoolEntry(Base):
    """角色道池一条收藏。"""

    __tablename__ = "dao_pool_entries"
    __table_args__ = (
        UniqueConstraint("character_id", "dao_id", name="uq_dao_pool_character_dao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
