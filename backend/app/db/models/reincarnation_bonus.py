"""
角色跨世永久轮回加成 ORM（一对一）。

真数值走本表；growth_attrs_json 仅保留剧情/兼容占位。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CharacterReincarnationBonus(Base):
    """
    跨世永久加成与轮回商店随机货架状态。

    Attributes:
        character_id: 角色主键（一对一）。
        initial_attr_bonus: 新生起效的攻/血初始乘区累加。
        minor_growth_bonus: 小突破成功时写入本世成长的增量。
        major_growth_bonus: 大突破成功时写入本世成长的增量。
        break_rate_bonus: 突破成功率加法修正。
        lifetime_applied_growth: 本世已应用成长乘区（入轮回清零）。
        constitution_slots_bought: 商店购买的体质槽数。
        spirit_root_slots_bought: 商店购买的灵根槽数。
        shop_random_offers_json: 当前随机货架 JSON。
        shop_seed: 最近一次刷新种子（审计）。
        shop_refreshed_at: 最近刷新时刻。
    """

    __tablename__ = "character_reincarnation_bonuses"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    initial_attr_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    minor_growth_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    major_growth_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    break_rate_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 本世突破累计成长（乘区）；轮回结算时清零
    lifetime_applied_growth: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    constitution_slots_bought: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    spirit_root_slots_bought: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    shop_random_offers_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    shop_seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shop_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
