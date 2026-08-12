"""
N4 灵宠图鉴进度 ORM（遇见 / 捕获）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PetDexEntry(Base):
    """角色对某物种的图鉴状态。"""

    __tablename__ = "pet_dex_entries"
    __table_args__ = (
        UniqueConstraint("character_id", "species_id", name="uq_pet_dex_character_species"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    species_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    caught: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
