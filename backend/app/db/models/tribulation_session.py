"""
渡劫会话 ORM（M5 §6.11）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TribulationSession(Base):
    """进行中或已结束的渡劫会话（含准备格与双维进度）。"""

    __tablename__ = "tribulation_sessions"
    __table_args__ = (
        # 活跃渡劫：character_id + phase
        Index("ix_tribulation_sessions_character_phase", "character_id", "phase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 所属角色（渡劫仅本体；化身渡劫 → M5-D07）
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 目标大境界键（渡劫成功后写入角色）
    target_major: Mapped[str] = mapped_column(String(32), nullable=False)
    # 目标层/期序号
    target_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 目标层/期标签（如 early / mid）
    target_stage_label: Mapped[str] = mapped_column(String(32), nullable=False, default="early")
    # True=跨大境界；False=同境层进阶（均可能需渡劫）
    is_cross_major: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 预估突破品阶（跨境映射雷劫双维；层进阶可空）
    projected_grade: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    # 威力品阶：apocalypse 遮天 / jealousy 天妒 / normal 普通 / mercy 怜悯
    power_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="mercy")
    # 次数档：nine / eighty_one / thousand / myriad
    count_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="nine")
    # 本次雷劫总击数（由 count_tier 展开）
    strike_total: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    # 已结算雷击数
    strike_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 开渡瞬间锁定的时辰（结算用；过程中环境滚动不影响）
    locked_shichen: Mapped[str] = mapped_column(String(32), nullable=False, default="noon")
    # 开渡瞬间锁定的世界天气（劫云表现另算；伤害用锁前天气）
    locked_weather: Mapped[str] = mapped_column(String(32), nullable=False, default="clear")
    # 是否在既有劫云内开渡 → 基础伤害翻倍
    in_cloud_double: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 开渡后劫云半径（随威力档；真邻区覆盖 → M5-D08）
    cloud_radius: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 准备格 JSON：护劫道具顺序与引用
    prep_slots_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 下一枚待消耗准备格下标
    prep_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 渡劫阵法（轴 A 乘区）
    formation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    # 是否选择遮天道具（成功降威力档）
    veil_chosen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 遮天检定是否已结算
    veil_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 开渡时固化的轴 A 乘区摘要（阵法/气运/魔性/遮天）
    axis_a_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 开渡时固化的轴 B 承伤摘要（功法/护劫/法宝）
    axis_b_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 渡劫会话当前 HP
    hp_current: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    # 渡劫会话最大 HP
    hp_max: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    # 灵宝护主是否已触发（每会话至多一次）
    guardian_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 怜悯档护主后的后续伤害乘区（可降至 0.01）
    mercy_damage_mult: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # 可复现 RNG 种子
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 阶段：preparing | committed | running | won | failed | fallen
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="preparing")
    # 终局结果 JSON（胜/败/陨落摘要）
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 雷击事件日志 JSON（千/万劫可压缩）
    events_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
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
