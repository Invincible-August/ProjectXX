"""
突破异步真读条会话 ORM（M5-D05 / M1-D20）。

与渡劫 ``tribulation_sessions`` 分离：仅承载无劫突破的闭关占用与锁定意图。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BreakthroughSession(Base):
    """
    突破闭关读条会话。

    同一角色至多一条 ``status=active``；到期后由懒结算写入结果并标 ``resolved``。
    """

    __tablename__ = "breakthrough_sessions"
    __table_args__ = (
        # 高频：按角色查 active 会话
        Index("ix_breakthrough_sessions_character_status", "character_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 所属角色（Phase A 仅本体）
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # active | resolved | cancelled（Phase A 不用 cancel）
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    # layer | major
    advance_type: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    # 开读条已扣灵石（结算时不再重复扣；失败且 fail_still_charge=false 时退回）
    spirit_stones_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 锁定的有效成功率（含轮回加成与钳制）
    effective_success_rate: Mapped[float] = mapped_column(Float, nullable=False)
    # 规则与门槛快照 JSON（keep_ratio / cost / required 等）
    rule_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 开读条时境界审计
    from_major: Mapped[str] = mapped_column(String(32), nullable=False)
    from_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    realm_progress_at_start: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # 结算结果缓存（success/dice/deltas），便于幂等重读
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
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
