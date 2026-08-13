"""
道侣 / 炉鼎关系 ORM（社交双修口子）。

道侣：申请→确认，流程同道友，独立类目。
炉鼎：列表口子已开；玩家侧暂不可直接邀请添加（后续玩法完善）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# companion=道侣 · vessel=炉鼎
BOND_KIND_COMPANION = "companion"
BOND_KIND_VESSEL = "vessel"
VALID_BOND_KINDS = frozenset({BOND_KIND_COMPANION, BOND_KIND_VESSEL})


class CharacterBond(Base):
    """
    角色间道侣/炉鼎关系。

    与 Friendship 独立；同一对角色可同时是道友与道侣。
    """

    __tablename__ = "character_bonds"
    __table_args__ = (
        UniqueConstraint(
            "character_low_id",
            "character_high_id",
            "bond_kind",
            name="uq_character_bonds_pair_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_low_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_high_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # companion | vessel
    bond_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 炉鼎主人；道侣为 null。炉鼎视角：owner=主人，另一方=炉鼎。
    owner_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # pending / active / rejected / cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
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
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # 炉鼎期限（现实小时）；道侣为 null；到期惰性解除
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
