"""
M4 背包 ORM 模型（最小经济；堆叠规则见 inventory.yaml）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InventoryItem(Base):
    """角色背包一行（按 item_id + item_type 堆叠）。"""

    __tablename__ = "inventory_items"
    __table_args__ = (
        # 扣材料 / 堆叠查找：character + item 复合键
        Index(
            "ix_inventory_items_char_item",
            "character_id",
            "item_id",
            "item_type",
            "bag_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_uid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # normal=普通储物袋（入轮回清空）；reincarnation=轮回袋（可带入）
    bag_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="normal",
    )
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
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
