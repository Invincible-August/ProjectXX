"""师徒 ORM（M7 L6）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MentorBond(Base):
    """师徒键：pending → active → graduated|dissolved。"""

    __tablename__ = "mentor_bonds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    master_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    apprentice_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # pending | active | graduated | dissolved | rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    # 申请人角色 id
    requester_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # apprentice=拜师申请；master=收徒邀请
    intent: Mapped[str] = mapped_column(String(16), nullable=False, default="apprentice")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MentorQuestProgress(Base):
    """师徒任务进度。"""

    __tablename__ = "mentor_quest_progress"
    __table_args__ = (
        UniqueConstraint("bond_id", "quest_id", name="uq_mentor_quest_bond"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bond_id: Mapped[int] = mapped_column(
        ForeignKey("mentor_bonds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MentorPassDaily(Base):
    """传功日次数。"""

    __tablename__ = "mentor_pass_daily"
    __table_args__ = (
        UniqueConstraint("bond_id", "day_key", name="uq_mentor_pass_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bond_id: Mapped[int] = mapped_column(
        ForeignKey("mentor_bonds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_key: Mapped[str] = mapped_column(String(16), nullable=False)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
