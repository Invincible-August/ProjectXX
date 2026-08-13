"""双修 ORM（M7 L7）：会话 + 时长/角色榜分。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DualCultivationSession(Base):
    """
    双修会话：inviting → confirmed → running → settled。

    亦可 cancelled / timeout / aborted。
    邀请方默认一号（主动），受邀方为零号（承纳）；时长计入对应榜。
    """

    __tablename__ = "dual_cultivation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technique_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # companion | vessel（须从道侣/炉鼎发起）
    bond_kind: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # number_one | zero — 邀请方角色位；受邀方取对位
    inviter_role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="number_one",
    )
    # 炉鼎强制接纳时为 True（兼容旧字段；新流程炉鼎走自动接受/自动宽衣）
    auto_forced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # inviting | accepted | undressed | running | settled | cancelled | timeout
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inviting", index=True)
    invite_expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 宽衣截止
    undress_expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    invitee_undressed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 掷骰快照
    roll_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roll_lo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roll_hi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effect_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    yield_mult: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dice_label_zh: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rerolls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 结算摘要 JSON
    settle_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 可选复现种子（测用）
    dice_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DualRankScore(Base):
    """
    双修榜累计分（按角色 + 榜键唯一）。

    ``duration_total`` = 累计双修秒数（主时长榜前 100）。
    角色榜（乾/坤 × 一号/零号）亦按秒累计，文案见 YAML。
    """

    __tablename__ = "dual_rank_scores"
    __table_args__ = (
        UniqueConstraint("character_id", "board_key", name="uq_dual_rank_board"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # duration_total | male_number_one | male_zero | female_number_one | female_zero
    board_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
