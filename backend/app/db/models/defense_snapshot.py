"""
防守快照 ORM 模型（M3战斗成型设计.md §6.2）。

每角色仅保留一行「当前有效防守快照」；PVP 攻打读取此行，
不触碰对方实时养成数据。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DefenseSnapshot(Base):
    """角色当前防守快照（character_id 主键，一角色一行）。"""

    __tablename__ = "defense_snapshots"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 快照 payload JSON（结构见设计 §6.1；不含挂机瞬时进度）
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    # 冗余内容哈希，便于列表比对是否变化
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # 手动更新冷却锚点；NULL 表示从未手动更新过
    last_manual_update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # 最近一次惰性定点补刷的槽位标记（如 "2026-08-05T10"），防同槽重复刷
    last_auto_slot: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        default=None,
    )
