"""
核验领域服务包（verification）。

对外暴露：

- Provider 工厂：``get_sms_provider`` / ``get_email_provider`` / ``get_identity_provider``；
- 兼容包装：``send_sms_code`` / ``send_email_code`` / ``verify_identity``；
- 证件工具：``hash_id_card`` / ``mask_id_card``。

编排与 ticket 逻辑见 ``service.VerificationService``。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.schemas.common import AppError
from app.services.verification.id_card_util import hash_id_card, mask_id_card
from app.services.verification.protocols import EmailProvider, IdentityProvider, SmsProvider
from app.services.verification.providers import (
    email_aliyun,
    email_debug,
    email_resend,
    id_format,
    id_real_person,
    id_two_factor,
    sms_aliyun,
    sms_debug,
    sms_tencent,
)

__all__ = [
    "EmailProvider",
    "IdentityProvider",
    "SmsProvider",
    "get_email_provider",
    "get_identity_provider",
    "get_sms_provider",
    "hash_id_card",
    "mask_id_card",
    "send_email_code",
    "send_sms_code",
    "verify_identity",
]

# 短信 Provider 单例：key 对应 Settings.sms_provider 的取值
_SMS_PROVIDER_INSTANCES: dict[str, SmsProvider] = {
    "debug": sms_debug.DebugSmsProvider(),
    "aliyun": sms_aliyun.AliyunSmsProvider(),
    "tencent": sms_tencent.TencentSmsProvider(),
}

# 邮件 Provider 单例：key 对应 Settings.email_provider 的取值
_EMAIL_PROVIDER_INSTANCES: dict[str, EmailProvider] = {
    "debug": email_debug.DebugEmailProvider(),
    "resend": email_resend.ResendEmailProvider(),
    "aliyun": email_aliyun.AliyunEmailProvider(),
}

# 身份核验 Provider 单例：key 对应 Settings.id_verify_mode 的取值
_IDENTITY_PROVIDER_INSTANCES: dict[str, IdentityProvider] = {
    "format": id_format.FormatIdentityProvider(),
    "two_factor": id_two_factor.TwoFactorIdentityProvider(),
    "real_person": id_real_person.RealPersonIdentityProvider(),
}


def get_sms_provider() -> SmsProvider:
    """
    Resolve the configured SMS provider instance.

    Returns:
        SmsProvider: Adapter matching ``settings.sms_provider``.

    Raises:
        AppError: Unknown provider name (code ``50100``).
    """
    settings = get_settings()
    provider = _SMS_PROVIDER_INSTANCES.get(settings.sms_provider)
    if provider is None:
        raise AppError(
            50100,
            f"未知的短信 Provider: {settings.sms_provider}",
            http_status=501,
        )
    return provider


def get_email_provider() -> EmailProvider:
    """
    Resolve the configured email provider instance.

    Returns:
        EmailProvider: Adapter matching ``settings.email_provider``.

    Raises:
        AppError: Unknown provider name (code ``50100``).
    """
    settings = get_settings()
    provider = _EMAIL_PROVIDER_INSTANCES.get(settings.email_provider)
    if provider is None:
        raise AppError(
            50100,
            f"未知的邮件 Provider: {settings.email_provider}",
            http_status=501,
        )
    return provider


def get_identity_provider() -> IdentityProvider:
    """
    Resolve the configured identity verification provider instance.

    Returns:
        IdentityProvider: Adapter matching ``settings.id_verify_mode``.

    Raises:
        AppError: Unknown mode (code ``50100``).
    """
    settings = get_settings()
    provider = _IDENTITY_PROVIDER_INSTANCES.get(settings.id_verify_mode)
    if provider is None:
        raise AppError(50100, f"未知的身份核验模式: {settings.id_verify_mode}", http_status=501)
    return provider


async def send_sms_code(phone: str, code: str) -> None:
    """
    按当前配置的短信 Provider 发送验证码（模块级兼容包装）。

    Args:
        phone: 目标手机号（未做格式校验，调用方应先行校验）。
        code: 明文验证码。

    Raises:
        AppError: 配置了未知/未实现的 Provider 时抛出（错误码 50100）。
    """
    await get_sms_provider().send_code(phone, code)


async def send_email_code(email: str, code: str) -> None:
    """
    按当前配置的邮件 Provider 发送验证码（模块级兼容包装）。

    Args:
        email: 目标邮箱地址（未做格式校验，调用方应先行校验）。
        code: 明文验证码。

    Raises:
        AppError: 配置了未知/未实现的 Provider 时抛出（错误码 50100）。
    """
    await get_email_provider().send_code(email, code)


async def verify_identity(
    *,
    real_name: str,
    id_card: str,
    face_token: str | None = None,
) -> None:
    """
    身份核验工厂：按 ``settings.id_verify_mode`` 路由到 A/B/C Provider（模块级兼容包装）。

    Args:
        real_name: 真实姓名（B/C 必填，A 仅用于日志辅助，不参与校验位计算）。
        id_card: 18 位身份证号原文（本函数不落库，调用方负责后续哈希/脱敏）。
        face_token: 实人核验（C）所需的前端 SDK 认证凭证；A/B 忽略该参数。

    Raises:
        AppError: 核验失败或对应 Provider 未配置/未实现时抛出。
    """
    await get_identity_provider().verify(
        real_name=real_name,
        id_card=id_card,
        face_token=face_token,
    )
