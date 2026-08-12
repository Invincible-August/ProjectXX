"""
短信 Provider：腾讯云短信服务骨架。

函数签名与其他短信 Provider 对齐，便于工厂函数统一调用；真实的腾讯云 SDK 接入
（SecretId/SecretKey、签名、模板等）留待后续任务实现，目前统一抛出 ``AppError(50100)``。
"""

from __future__ import annotations

import logging

from app.schemas.common import AppError

logger = logging.getLogger(__name__)


class TencentSmsProvider:
    """
    Tencent Cloud SMS adapter skeleton (SDK not yet integrated).
    """

    async def send_code(self, phone: str, code: str) -> None:
        """
        Send verification code via Tencent SMS (not implemented).

        Args:
            phone: Target mobile number.
            code: Plaintext verification code.

        Raises:
            AppError: Always raised with code ``50100`` until SDK is wired.
        """
        # TODO(Task 4+): 接入腾讯云短信 SDK（SecretId/SecretKey 从环境变量读取，禁止硬编码）
        _ = phone, code
        logger.warning("[SMS-TENCENT] Provider 尚未接入，拒绝发送")
        raise AppError(50100, "腾讯云短信 Provider 尚未接入", http_status=501)


_default_provider = TencentSmsProvider()


async def send_code(target: str, code: str) -> None:
    """
    通过腾讯云短信服务发送验证码（骨架，尚未接入真实 SDK）（模块级兼容包装）。

    Args:
        target: 目标手机号。
        code: 明文验证码。

    Raises:
        AppError: 恒定抛出，提示腾讯云短信 Provider 尚未接入（错误码 50100）。
    """
    await _default_provider.send_code(target, code)
