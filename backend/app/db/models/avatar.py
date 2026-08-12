"""
M4 化身 ORM 模型（1:1 character）。

化身独立挂机方向与三池；灵石由本体 characters 表统一扣除。
AVATAR-D03：体力槽与日行动（元婴起功能解锁后生效）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Avatar(Base):
    """玩家化身：每角色最多一行（character_id UNIQUE；永久单化身）。"""

    __tablename__ = "avatars"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 一对一：每角色最多一个化身
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False)  # 化身道号/名
    # 状态：idle / crafting / disabled（渡劫禁上阵等）
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    # 化身独立挂机方向（与本体并行；灵石由本体扣）
    idle_direction: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    cultivation_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 化身修灵池
    body_tempering_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 化身炼体池（不可回传本体）
    crafting_exp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 化身制造业经验（不可回传）
    # 凝练时刻快照的战斗属性 JSON（约本体 50% + 材料修正）
    base_stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # —— AVATAR-D03 体力 / 日行动 ——
    stamina: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 当前体力
    daily_actions_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 今日已用行动
    daily_actions_day: Mapped[str] = mapped_column(String(16), nullable=False, default="")  # UTC 日键 YYYY-MM-DD
    stamina_recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )  # 体力恢复锚点
    # 道友助战开关：1=允许好友在离线时自动借入；在线时仍须主人确认
    assist_friends_enabled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    # 化身挂机 settle 锚点
    last_settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
