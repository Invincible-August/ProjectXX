"""
化身独立穿戴槽：装备 / 功法 / 神通，与本体槽分表，破除时 CASCADE。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvatarEquipmentSlot(Base):
    """化身一件装备指针；背包实例仍挂在角色 inventory。"""

    __tablename__ = "avatar_equipment_slots"
    __table_args__ = (
        UniqueConstraint("avatar_id", "slot", name="uq_avatar_equipment_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    avatar_id: Mapped[int] = mapped_column(
        ForeignKey("avatars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot: Mapped[str] = mapped_column(String(32), nullable=False)
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
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


class AvatarTechniqueSlot(Base):
    """化身主功法 / 技法格。"""

    __tablename__ = "avatar_technique_slots"
    __table_args__ = (
        UniqueConstraint(
            "avatar_id",
            "slot_type",
            "slot_index",
            name="uq_avatar_technique_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    avatar_id: Mapped[int] = mapped_column(
        ForeignKey("avatars.id", ondelete="CASCADE"),
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


class AvatarDivineAbilitySlot(Base):
    """化身神通装备格。"""

    __tablename__ = "avatar_divine_ability_slots"
    __table_args__ = (
        UniqueConstraint(
            "avatar_id",
            "slot_index",
            name="uq_avatar_divine_ability_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    avatar_id: Mapped[int] = mapped_column(
        ForeignKey("avatars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ability_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
