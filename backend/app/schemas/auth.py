"""
鉴权相关请求 / 响应 Schema。

注册以邮箱 + 手机号为主标识（无用户名）；登录支持：
邮箱+密码、手机号+密码、手机号+短信验证码。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# 与 verification Schema 对齐的手机粗检
_PHONE_PATTERN = re.compile(r"^1\d{10}$")

LoginMethod = Literal["password", "sms"]


class RegisterRequest(BaseModel):
    """
    POST /auth/register 的请求体。

    不再接收用户名；以邮箱 + 手机号作为账号标识。
    核验相关字段在 DEBUG 下 ticket 可空；正式模式由服务层检查齐全性。
    """

    password: str = Field(min_length=8, max_length=64)
    # 邮箱与手机号：业务上注册必填（服务层强制）；Schema 允许 None 以便统一空串转 None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    real_name: str | None = Field(default=None, max_length=64)
    id_card: str | None = Field(default=None, max_length=18)
    sms_ticket: str | None = Field(default=None, max_length=64)
    email_ticket: str | None = Field(default=None, max_length=64)
    id_ticket: str | None = Field(default=None, max_length=64)

    @field_validator(
        "email",
        "phone",
        "real_name",
        "id_card",
        "sms_ticket",
        "email_ticket",
        "id_ticket",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        """把空字符串视为未提供，便于 DEBUG 跳过与前端可选字段。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """
        规范化邮箱：strip + 小写；明显非法格式拒绝。

        Args:
            value: 可选邮箱。

        Returns:
            str | None: 规范化邮箱或 None。

        Raises:
            ValueError: 缺少 ``@`` 等明显非法格式。
        """
        if value is None:
            return None
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email format is invalid")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """
        规范化并粗检手机号（大陆 11 位）。

        Args:
            value: 可选手机号。

        Returns:
            str | None: strip 后的手机号或 None。

        Raises:
            ValueError: 格式明显不合法。
        """
        if value is None:
            return None
        normalized = value.strip()
        if not _PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("phone must be an 11-digit mainland mobile number")
        return normalized

    @field_validator("real_name")
    @classmethod
    def normalize_real_name(cls, value: str | None) -> str | None:
        """去掉姓名首尾空白。"""
        if value is None:
            return None
        return value.strip()

    @field_validator("id_card")
    @classmethod
    def normalize_id_card(cls, value: str | None) -> str | None:
        """
        规范化身份证号：去空白；末位 x→X（与 IdSubmitRequest / 服务层一致）。

        Args:
            value: 可选证件号原文。

        Returns:
            str | None: 规范化后的证件号或 None。
        """
        if value is None:
            return None
        normalized = value.strip()
        if normalized and normalized[-1] in ("x", "X"):
            return normalized[:-1] + "X"
        return normalized


class RegisterResult(BaseModel):
    """注册成功时信封 data 中的载荷。"""

    user_id: int
    email: str | None
    phone: str | None
    display_name: str
    created_at: datetime


class LoginRequest(BaseModel):
    """
    POST /auth/login 的请求体。

    - ``password``：``account``（邮箱或手机号）+ ``password``
    - ``sms``：``phone`` + ``sms_code``
    """

    login_method: LoginMethod = "password"
    # 密码登录：邮箱或手机号（二选一填写在同一字段）
    account: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=64)
    # 短信登录
    phone: str | None = Field(default=None, max_length=20)
    sms_code: str | None = Field(default=None, min_length=1, max_length=8)
    # 记住登录：True 时签发默认长效 refresh；False 时短效会话 refresh
    remember_me: bool = True

    @field_validator("account", "password", "phone", "sms_code", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        """空字符串视为未提供。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("account")
    @classmethod
    def normalize_account(cls, value: str | None) -> str | None:
        """
        规范化登录账号：邮箱转小写；手机号仅 strip。

        Args:
            value: 原始账号。

        Returns:
            str | None: 规范化后的账号。
        """
        if value is None:
            return None
        normalized = value.strip()
        # 含 @ 按邮箱处理（小写）；否则保留原样（手机号由服务层再校验）
        if "@" in normalized:
            return normalized.lower()
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """
        规范化短信登录手机号。

        Args:
            value: 可选手机号。

        Returns:
            str | None: 规范化手机号。

        Raises:
            ValueError: 格式不合法。
        """
        if value is None:
            return None
        normalized = value.strip()
        if not _PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("phone must be an 11-digit mainland mobile number")
        return normalized

    @model_validator(mode="after")
    def validate_login_fields(self) -> LoginRequest:
        """
        按登录方式校验必填字段组合。

        Returns:
            LoginRequest: 通过校验的自身。

        Raises:
            ValueError: 字段组合不完整。
        """
        if self.login_method == "password":
            if not self.account or not self.password:
                raise ValueError("password login requires account and password")
        elif self.login_method == "sms":
            if not self.phone or not self.sms_code:
                raise ValueError("sms login requires phone and sms_code")
        return self


class RefreshRequest(BaseModel):
    """POST /auth/refresh 的请求体。"""

    refresh_token: str = Field(min_length=1)


class AuthUserBrief(BaseModel):
    """登录 / 刷新响应中的精简用户信息。"""

    id: int
    email: str | None = None
    phone: str | None = None
    display_name: str


class TokenPayload(BaseModel):
    """登录与刷新成功时 data 中的令牌载荷。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserBrief
    # 与 /auth/me 同语义：登录/换票时一并返回，避免前端再打一枪只为分流
    has_character: bool


class AuthMeResult(BaseModel):
    """GET /auth/me 成功时 data 中的载荷。"""

    id: int
    email: str | None = None
    phone: str | None = None
    display_name: str
    has_character: bool
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    """POST /auth/change-password。"""

    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=8, max_length=64)
