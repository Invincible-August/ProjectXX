"""
M4 工坊队列 ORM 模型。

惰性 settle 推进 running → ready；玩家 claim 后入背包或阵法等级。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CraftJob(Base):
    """进行中或待领取的配方任务。"""

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
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 开工时刻
    finish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 预计完成时刻
    # 状态：running → ready → claimed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)  # 产出/失败摘要
    # M5：开工瞬间锁定的 shichen/weather
    env_lock_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
