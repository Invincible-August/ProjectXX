"""
世界天气状态 ORM（可选持久化；memory 后端可不写库）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorldWeatherState(Base):
    """单区天气权威行（M5 仅 default）。"""

    __tablename__ = "world_weather_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default="default",
    )  # 区域；M5 仅 default
    weather_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="clear",
    )  # 当前权威天气键
    next_roll_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )  # 下次加权滚动时刻
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorldCloudOverlay(Base):
    """劫云覆盖标记（M5 无真地图；同区翻倍判定钩子）。"""

    __tablename__ = "world_cloud_overlay"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="default",
        index=True,
    )  # 劫云所在区域
    source_character_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 开渡角色（来源）
    cloud_radius: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )  # 半径（真邻区覆盖 → M5-D08）
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )  # 劫云过期；空=随会话清理
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
