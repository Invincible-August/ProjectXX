"""
角色功法等级与装备槽 ORM。

创角默认解锁配置中全部功法，初始 level=0。
装备槽与体质同构：一本功法同一时刻只能占一格。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CharacterTechnique(Base):
    """角色已解锁功法及等级。"""

    __tablename__ = "character_techniques"
    __table_args__ = (
        UniqueConstraint("character_id", "technique_id", name="uq_character_technique"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technique_id: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 五源：system / sect / mentor / research / chance
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
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


class CharacterTechniqueSlot(Base):
    """主功法 / 技法装备格。"""

    __tablename__ = "character_technique_slots"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "slot_type",
            "slot_index",
            name="uq_character_technique_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot_type: Mapped[str] = mapped_column(String(16), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    technique_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
