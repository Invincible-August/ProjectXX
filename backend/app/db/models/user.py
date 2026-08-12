"""
用户 ORM 模型（M0 §3.2）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """账号实体，用于注册 / 登录。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 内部唯一标识（由邮箱/手机派生，如 m138…）；登录对外使用 email / phone，不再暴露用户名
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 以下字段服务于账号核验特性（邮箱 / 手机 / 实名认证），均允许为空以兼容存量账号
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    real_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 身份证号仅存哈希，原文绝不落库；id_card_masked 用于前端展示脱敏后的号码
    id_card_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    id_card_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 实名核验等级：none / format / two_factor / real_person 等，具体取值由 Task 3+ 定义
    id_verified_level: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
