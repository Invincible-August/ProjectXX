"""
轮回结算流水 ORM（M5 §7.4）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReincarnationLog(Base):
    """每次轮回结算一行审计日志。"""

    __tablename__ = "reincarnation_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # forced=超时强制 | self=自选入轮回 | altar=祭坛轮回
    path: Mapped[str] = mapped_column(String(32), nullable=False)
    from_major: Mapped[str] = mapped_column(String(32), nullable=False)  # 轮回前大境界
    to_major: Mapped[str] = mapped_column(String(32), nullable=False)  # 重置后大境界
    points_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 本次获得轮回点
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)  # 结算摘要 JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
