"""
道主席位 ORM：每道至多一名现任道主。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DaoLordship(Base):
    """某道现任道主。"""

    __tablename__ = "dao_lordships"
    __table_args__ = (
        UniqueConstraint("dao_id", name="uq_dao_lordship_dao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 就任时绑定的防守快照引用：存角色 character_id（DefenseSnapshot 主键即此）
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    privileges_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    claimed_at: Mapped[datetime] = mapped_column(
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
