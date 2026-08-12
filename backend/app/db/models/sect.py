"""
宗门相关 ORM（M7 L1）。

含：宗门行、成员、贡献流水、任务进度。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class Sect(Base):
    """宗门主表：NPC 模板实例或玩家自建。"""

    __tablename__ = "sects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # npc = 配置驱动；player = 自建
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="npc", index=True)
    # NPC 对应 sects.yaml npc_sects 键；自建可为 null
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    motto: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    # 祖师（创建者）；NPC 宗可为 null
    founder_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 宗主（可≠祖师）
    leader_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
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


class SectMember(Base):
    """宗门成员：一角色同时最多隶属一个宗门。"""

    __tablename__ = "sect_members"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_sect_members_character"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # founder / leader / elder / member
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    contribution: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SectContributionLedger(Base):
    """贡献流水：入宗奖励/任务/商店/兑宠/轮回归零均可审计。"""

    __tablename__ = "sect_contribution_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    # 机读原因键：join_bonus / quest_reward / shop_buy / pet_exchange / reincarnation_zero …
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    # 玩家可见中文摘要
    note_zh: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class SectQuestProgress(Base):
    """宗门任务进度：同角色同任务按接取方唯一；完成后可再接。"""

    __tablename__ = "sect_quest_progress"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "quest_id",
            "assignee",
            name="uq_sect_quest_char_quest_assignee",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sect_id: Mapped[int] = mapped_column(
        ForeignKey("sects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # body = 本体；avatar = 化身独立接（M4-D06）
    assignee: Mapped[str] = mapped_column(String(16), nullable=False, default="body")
    # accepted / completed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
