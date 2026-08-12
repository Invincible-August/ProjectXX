"""
角色 ORM 模型（M0 §3.3）。

含 M1 挂机 / 修为等占位字段；M0 仅创角写入默认值并只读展示。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Character(Base):
    """玩家角色：一账号一角色（``user_id`` UNIQUE）。"""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 一对一：每个 user 最多一个角色
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    # 全服唯一道号
    name: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)

    # 境界：M0 固定锻体一层；后续由突破系统改写
    major_realm: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="body_tempering",
    )
    realm_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    realm_stage_label: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="layer_1",
    )

    # 成长资源池（M2：挂机只涨池；境界进度见 realm_progress）
    cultivation_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    body_tempering_points: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    crafting_exp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    spirit_stones: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1000)

    # M2：已投入当前档的境界进度（突破门槛读此字段）
    realm_progress: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 最近一次跨境品阶；无跨境过为 none
    breakthrough_grade: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    # 由品阶推导的神通槽位数（占位）
    divine_ability_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 会员档位：free / tier1 / tier2（开通流程见 M7 L8）
    membership_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    # 付费会员过期时刻；free 或未开通为 null
    membership_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # 天道点（不可玩家直转；沙盒/商店）
    tiandao_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 待领取离线明细 JSON；无则 null
    pending_offline_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 最近一次因离线帽截断的时刻（审计/展示）
    offline_capped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # 挂机方向与状态机（M0 仅 none / normal）
    idle_direction: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")

    # M3 体力（§12.9）：上次结算整点值 + 结算锚点（惰性恢复，无定时器）
    stamina: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    stamina_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    # M3 试炼木傀数量（S5 多子编成样本；GM 可调）
    trial_puppet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # M4 神识 / 阵法 / 反噬
    divine_sense_capacity_bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    array_craft_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    divine_sense_backlash: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # M5 轮回 / 待引渡 / 气运魔性占位
    reincarnation_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 轮回点
    # 历史最高大境界（发轮回点 / 商店 require / 结算加成用）
    peak_major_realm: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="body_tempering",
    )
    growth_attrs_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )  # 剧情/兼容占位 JSON（真数值见 character_reincarnation_bonuses）
    story_flags_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )  # 剧情已历节点等 flag（无正文）
    ferry_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )  # 待引渡截止；非 awaiting_ferry 为 null
    reincarnation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 已轮回次数
    legacy_items_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )  # 传承道具栏占位 JSON
    fate_luck: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 气运（渡劫轴 A：高↓威力）
    demonic_nature: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 魔性（渡劫轴 A：高↑威力）
    # 灵根环境标签 JSON 列表（如 ["thunder_root"]）；null 视为 []
    spirit_root_tags_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 自救冷却锚点（可选）
    last_self_rescue_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # M7 L1：当前宗门（散修为 null；与 sect_members 同步）
    sect_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        index=True,
    )
    # M7 L7：道途阴阳（male|female）；存量可空，进双修前补选
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)

    # M1 挂机切片锚点：创角时写入当前 UTC
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
