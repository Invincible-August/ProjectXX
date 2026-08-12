"""
核验挑战（VerificationChallenge）ORM 模型。

用于承载邮箱验证码、短信验证码、实名核验（二要素 / 人脸）等各类核验流程的
临时状态，具体业务逻辑（发送验证码、校验、生成 ticket）由 Task 3+ 实现，
本模型仅定义数据结构。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VerificationChallenge(Base):
    """一次核验挑战记录（验证码 / 实名核验等）。"""

    __tablename__ = "verification_challenges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 核验渠道：email / sms / id_two_factor / id_real_person 等，由 Task 3+ 定义具体取值
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 核验目标：邮箱地址 / 手机号 / 身份证哈希等，随 channel 不同而含义不同
    target: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 验证码哈希（不存明文），部分核验方式（如第三方实名核验）可能不涉及验证码，故允许为空
    code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 核验通过后签发的一次性凭证，供后续接口（如注册/绑定）校验使用
    ticket: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # 附加数据（JSON 文本），如第三方回调的原始结果、限流计数等，具体结构由使用方约定
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 已被消费（核验通过并使用过）的时间，None 表示尚未消费
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
