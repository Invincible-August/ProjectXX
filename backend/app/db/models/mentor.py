"""师徒 ORM（M7 L6）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
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
    requester_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # apprentice=拜师申请；master=收徒邀请
    intent: Mapped[str] = mapped_column(String(16), nullable=False, default="apprentice")
    # 亲传弟子标记（师傅点名，最多见配置）
    is_direct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 指定为亲传的日历日（YYYY-MM-DD）；隔日方可解除
    direct_set_day_key: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    # 解除亲传的日历日；当日不可再指定同一人
    direct_cleared_day_key: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
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
    """
    师徒日课 / 传授日计数。

    ``lesson_kind``：最近一次日课类型（兼容）。
    ``lesson_*_count``：当日各类型日课次数。
    ``teach_count``：当日已传授次数。
    ``study_count``：当日徒弟请学次数。
    ``pass_count``：兼容旧传功计数。
    """

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
    # dao | craft | technique | empty
    lesson_kind: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    lesson_dao_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_craft_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lesson_technique_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    teach_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    study_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MentorTransmission(Base):
    """多日传授进度（功法 / 配方图纸）。"""

    __tablename__ = "mentor_transmissions"
    __table_args__ = (
        UniqueConstraint(
            "bond_id",
            "item_kind",
            "item_id",
            name="uq_mentor_transmission_item",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bond_id: Mapped[int] = mapped_column(
        ForeignKey("mentor_bonds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # technique | recipe
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    required_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # active | completed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    # 师傅最近一次传授日（与徒弟请学日分开，同日可各推进一次）
    last_day_key: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    # 徒弟最近一次请学日
    last_study_day_key: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CharacterCraftKnowledge(Base):
    """角色已学会的配方 / 图纸（传授解锁）。"""

    __tablename__ = "character_craft_knowledge"
    __table_args__ = (
        UniqueConstraint("character_id", "recipe_id", name="uq_character_craft_recipe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipe_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="mentor")
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
