"""
M4 工坊队列 ORM 模型。

入队即冻资源；惰性 settle 到期后直入背包（claimed|failed）；可取消退冻。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CraftJob(Base):
    """排队中的配方任务（完成即结算，无需领取）。"""

    __tablename__ = "craft_jobs"
    __table_args__ = (
        # PlayGate / 工坊：按角色筛 running
        Index("ix_craft_jobs_character_status", "character_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 执行者：main（本体）或 avatar（化身）
    actor: Mapped[str] = mapped_column(String(16), nullable=False, default="main")
    recipe_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 配方 id
    # 一次开工件数；耗时与费用均 × quantity
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 开工时刻
    finish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 预计完成时刻
    # 状态：running → claimed | failed；cancelled 为取消退冻
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)  # 产出/失败摘要
    # 入队冻结快照：materials / spirit_stones / stamina（取消时退回）
    cost_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # M5：开工瞬间锁定的 shichen/weather
    env_lock_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
