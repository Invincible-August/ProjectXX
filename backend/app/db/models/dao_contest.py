"""
道主之争赛会周期 ORM（M6-D06 + 擂台分阶段）。

含：Contest 周期、报名条目、对阵场次（淘汰 / 道主决战 / 直播窗 / RSVP）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DaoContest(Base):
    """一场道主之争（按配置日切周期）。"""

    __tablename__ = "dao_contests"
    __table_args__ = (
        UniqueConstraint("cycle_date", name="uq_dao_contest_cycle_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 配置时区下的业务日 YYYY-MM-DD
    cycle_date: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # registration | matching | rsvp | arena | settled | cancelled
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registration", index=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    registration_closes_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    fight_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    force_started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 收口摘要 JSON（分道人数、冠军、更替等）
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # 擂台阶段：rsvp | round_countdown | round_gap | adjust | playing | idle
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    phase_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    current_round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 分阶段调度状态（alive 池、道主 RSVP、活跃场次等）
    arena_state_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class DaoContestEntry(Base):
    """赛会报名条目（本命道快照）。"""

    __tablename__ = "dao_contest_entries"
    __table_args__ = (
        UniqueConstraint("contest_id", "character_id", name="uq_dao_contest_entry_char"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("dao_contests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # none | pending | accepted | declined | timeout（报名期为 none）
    rsvp_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    rsvp_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    in_arena: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DaoContestMatch(Base):
    """
    赛会单场对阵（淘汰 / 半决 / 决赛 / 道主决战）。

    分阶段：pending → adjusting → playing → finished；离场可 leave_forfeit。
    """

    __tablename__ = "dao_contest_matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("dao_contests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # early | semi | final | lord
    round_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # 同道内轮次序号（1 起）；道主战固定为 0
    round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 同轮内场次序号
    bracket_slot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 选手 A / B；轮空时 side_b 为空；道主战 A=冠军 B=道主
    side_a_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    side_b_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    winner_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # pending | adjusting | playing | finished | forfeit | void
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="finished")
    # bye | offline_forfeit | leave_forfeit | double_offline | battle | lord_snapshot | lord_realtime | void
    resolve_reason: Mapped[str] = mapped_column(String(32), nullable=False, default="battle")
    result_label_zh: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    # 战报 JSON：{summary, events, ...}；下场开赛可按配置清空
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 是否可直播轮次（落库时按配置标记）
    is_live_round: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    live_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    live_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # 道主战：snapshot | realtime | void
    lord_defense_mode: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    # 道主战是否发生更替
    lordship_transferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    loadout_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    presence_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    side_a_forfeit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    side_b_forfeit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
