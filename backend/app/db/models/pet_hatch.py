"""
N5 灵兽蛋孵化会话 ORM。

惰性 settle：hatching → ready；claim 后写入 claimed 并生成灵宠。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PetHatchJob(Base):
    """角色的一次孵化会话。"""

    __tablename__ = "pet_hatch_jobs"
    __table_args__ = (
        Index("ix_pet_hatch_jobs_character_status", "character_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 消耗的蛋道具 id（与 pet_eggs / inventory 对齐）
    egg_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 预定孵出物种（开工时锁定，防配置热更漂移）
    species_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # hatching → ready → claimed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="hatching", index=True)
    # 领取后写入新生宠 id
    result_pet_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
