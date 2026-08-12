"""
核验相关请求 / 响应 Schema（verification API 与服务层共用）。

HTTP 路由（Task 5）将直接复用这些模型；本模块不依赖 FastAPI。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# 大陆手机号粗检：1 开头共 11 位数字（服务层可再做规范化）
_PHONE_PATTERN = re.compile(r"^1\d{10}$")
# 验证码：4–8 位数字（DEBUG 固定码与随机码均覆盖）
_CODE_PATTERN = re.compile(r"^\d{4,8}$")


class SmsSendRequest(BaseModel):
    """POST /verification/sms/send 请求体。"""

    phone: str = Field(min_length=11, max_length=20, description="手机号")

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        """
        规范化并粗检手机号。

        Args:
            value: 客户端原始手机号。

        Returns:
            str: strip 后的手机号。

        Raises:
            ValueError: 格式明显不合法时抛出。
        """
        normalized = value.strip()
        if not _PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("phone must be an 11-digit mainland mobile number")
        return normalized


class SmsConfirmRequest(BaseModel):
    """POST /verification/sms/confirm 请求体。"""

    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=4, max_length=8, description="短信验证码")

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        """规范化手机号（规则同 SmsSendRequest）。"""
        normalized = value.strip()
        if not _PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("phone must be an 11-digit mainland mobile number")
        return normalized

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """去掉首尾空白并校验为纯数字验证码。"""
        normalized = value.strip()
        if not _CODE_PATTERN.fullmatch(normalized):
            raise ValueError("code must be 4-8 digits")
        return normalized


class EmailSendRequest(BaseModel):
    """POST /verification/email/send 请求体。"""

    email: str = Field(min_length=3, max_length=255, description="邮箱地址")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """
        规范化邮箱：strip + 小写。

        Args:
            value: 原始邮箱。

        Returns:
            str: 规范化后的邮箱。

        Raises:
            ValueError: 缺少 ``@`` 等明显非法格式时抛出。
        """
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email format is invalid")
        return normalized


class EmailConfirmRequest(BaseModel):
    """POST /verification/email/confirm 请求体。"""

    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=8, description="邮箱验证码")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """规范化邮箱（规则同 EmailSendRequest）。"""
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email format is invalid")
        return normalized

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """去掉首尾空白并校验为纯数字验证码。"""
        normalized = value.strip()
        if not _CODE_PATTERN.fullmatch(normalized):
            raise ValueError("code must be 4-8 digits")
        return normalized


class IdSubmitRequest(BaseModel):
    """POST /verification/id/submit 请求体。"""

    real_name: str = Field(default="", max_length=64, description="真实姓名")
    id_card: str = Field(min_length=15, max_length=18, description="身份证号")
    face_token: str | None = Field(
        default=None,
        max_length=512,
        description="实人核验凭证（C 模式；A/B 可忽略）",
    )

    @field_validator("real_name")
    @classmethod
    def normalize_real_name(cls, value: str) -> str:
        """去掉姓名首尾空白。"""
        return value.strip()

    @field_validator("id_card")
    @classmethod
    def normalize_id_card(cls, value: str) -> str:
        """去掉证件号空白；末位 x 统一为大写 X 便于后续校验。"""
        normalized = value.strip()
        if normalized and normalized[-1] in ("x", "X"):
            return normalized[:-1] + "X"
        return normalized


class TicketData(BaseModel):
    """确认 / 身份核验成功后信封 data 中的票据载荷。"""

    ticket: str = Field(description="一次性核验票据")


class ModesData(BaseModel):
    """GET /verification/modes 成功时 data 载荷。"""

    debug: bool
    id_verify_mode: str
    sms_provider: str
    email_provider: str
    id_two_factor_provider: str
    id_real_person_provider: str
    # 注册 UI / 服务端共用的材料开关（与 Settings 对齐）
    register_require_phone: bool
    register_require_real_name: bool
    register_require_email_code: bool
