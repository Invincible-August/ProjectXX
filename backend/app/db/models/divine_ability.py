"""
角色已学神通与装备槽 ORM。

创角发放配置中的样本神通；可装备格数 = 修为基数 + 品阶加成。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CharacterDivineAbility(Base):
    """角色已学会的神通。"""

    __tablename__ = "character_divine_abilities"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "ability_id",
            name="uq_character_divine_ability",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ability_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CharacterDivineAbilitySlot(Base):
    """神通装备格（格数随修为与品阶变化）。"""

    __tablename__ = "character_divine_ability_slots"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "slot_index",
            name="uq_character_divine_ability_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
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
