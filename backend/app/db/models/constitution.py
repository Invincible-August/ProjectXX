"""
体质背包与镶嵌槽 ORM（M2 骨架）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConstitutionItem(Base):
    """角色体质背包中的实例物品。"""

    __tablename__ = "character_constitution_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    def_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False, default="mortal")
    grade: Mapped[str] = mapped_column(String(32), nullable=False, default="mortal")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="body")
    is_equipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ConstitutionSlot(Base):
    """角色主/副镶嵌格。"""

    __tablename__ = "character_constitution_slots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot_type: Mapped[str] = mapped_column(String(16), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    item_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("character_constitution_items.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
