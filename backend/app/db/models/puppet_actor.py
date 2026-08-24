"""傀儡战斗体 ORM（S1-4 双切面 · 模型 A：一物一灵）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PuppetActor(Base):
    """
    傀儡行动体行：与背包 ``InventoryItem`` 一对一绑定（试炼木傀可无背包）。

    Attributes:
        inventory_item_id: 绑定的背包行；试炼木傀为 None。
        def_id: 配置模板 id（如 puppet_wood_v1）。
        ephemeral: True 表示试炼木傀（无背包、可按 trial_index 区分）。
    """

    __tablename__ = "puppet_actors"
    __table_args__ = (
        UniqueConstraint("inventory_item_id", name="uq_puppet_actors_inventory_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 真傀：指向背包行；试炼木傀为空
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    def_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 模板/物品定义 id
    ephemeral: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 试炼木傀
    trial_index: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)  # 试炼序号 1..N
    label_zh: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)  # 展示名
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)  # 扩展 JSON
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
