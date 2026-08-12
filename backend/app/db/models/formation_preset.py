"""
布阵预设 ORM 模型（M3战斗成型设计.md §4）。

每角色 ≥3 槽（进攻 / 防守 / 临时）；坐标一律按进攻方视角存储，
防守侧开战时由引擎做 x 镜像。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FormationPreset(Base):
    """角色布阵预设：``(character_id, slot)`` 唯一。"""

    __tablename__ = "formation_presets"
    __table_args__ = (
        UniqueConstraint("character_id", "slot", name="uq_formation_character_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 槽位号：0..N-1（默认 3 槽）
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    # 玩家可改名；默认「进攻 / 防守 / 临时」
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    # 角色定位：attack / defense / temp
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="attack")
    # 阵法配置键；none 表示无阵
    formation_id: Mapped[str] = mapped_column(String(64), nullable=False, default="none")
    # 棋子占位 JSON：[{unit_uid, unit_kind, x, y}, ...]（进攻方视角坐标）
    units_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
