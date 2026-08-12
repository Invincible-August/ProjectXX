"""
M4 灵宠 ORM 模型（持有与上阵占位；PET-D01 词条 JSON）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Pet(Base):
    """角色持有的灵宠。"""

    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    species_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 物种/模板 id
    # 个体品阶（1～7；N4）；影响基础乘区与词条槽上限
    grade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 等级占位
    nickname: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)  # 昵称
    # 是否优先上阵（编成/神识占用）
    is_deploy_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # PET-D01：词条实例 JSON 数组（slot_index / affix_type_id / affix_tier / rolled_value）
    affixes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # PET-D01：各槽数值洗炼次数 JSON 对象（"0": k, ...）
    value_reroll_counts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # PET-D06：各槽改词条类型次数 JSON 对象（"0": k, ...）；与数值洗炼分计
    type_reroll_counts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # PET-D02：已学技能 id 列表 JSON；已装备最多 4 槽（null 为空槽）
    skills_learned_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    skills_equipped_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # PET-D03：种族天赋 id（捕获时从 race 锁定）；独立被动 id 列表 JSON（可空）
    racial_talent_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    passives_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # PET-D04：各兽丹已喂次数 JSON（"pet_pill_atk_minor": n, ...）
    feed_counts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
