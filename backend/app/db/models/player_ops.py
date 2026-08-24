"""
玩家运营流水表：打赏、仙缘派发、广告观看。

广告系统未接入前，``player_ad_watch_records`` 仅供后台查看；写入待广告回调。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlayerTipRecord(Base):
    """打赏（充值）流水：运营手工录入。"""

    __tablename__ = "player_tip_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 打赏发生时刻（运营填写的年月日时分秒）
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # 支付路径：微信 / 支付宝 / 运营自填
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    order_no: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # 金额（与 users.total_recharge_amount 同单位，整数）
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_admin_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FateLuckGrantRecord(Base):
    """运营派发仙缘流水。"""

    __tablename__ = "fate_luck_grant_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 派发时刻
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    # 派发数量（正整数）
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    before_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    after_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_admin_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PlayerAdWatchRecord(Base):
    """
    观看广告流水。

    广告系统接入前仅建表与后台只读列表；写入由后续广告回调完成。
    """

    __tablename__ = "player_ad_watch_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 观看时刻
    watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    # 广告平台标识（如穿山甲 / 优量汇 等；接入前可为空列表）
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 预留：广告位 / 创意 id 等
    ad_unit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
