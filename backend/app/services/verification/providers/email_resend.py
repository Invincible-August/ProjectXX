"""
邮件 Provider：Resend 服务骨架。

函数签名与其他邮件 Provider 对齐，便于工厂函数统一调用；真实的 Resend API 接入
（API Key、发件域名、模板等）留待后续任务实现，目前统一抛出 ``AppError(50100)``。
"""

from __future__ import annotations

import logging

from app.schemas.common import AppError

logger = logging.getLogger(__name__)


class ResendEmailProvider:
    """
    Resend API email adapter skeleton (API not yet integrated).
    """

    async def send_code(self, email: str, code: str) -> None:
        """
        Send verification code via Resend (not implemented).

        Args:
            email: Target mailbox address.
            code: Plaintext verification code.

        Raises:
            AppError: Always raised with code ``50100`` until API is wired.
        """
        # TODO(Task 4+): 接入 Resend API（API Key 从环境变量读取，禁止硬编码）
        _ = email, code
        logger.warning("[EMAIL-RESEND] Provider 尚未接入，拒绝发送")
        raise AppError(50100, "Resend 邮件 Provider 尚未接入", http_status=501)


_default_provider = ResendEmailProvider()


async def send_code(target: str, code: str) -> None:
    """
    通过 Resend 发送验证码邮件（骨架，尚未接入真实 API）（模块级兼容包装）。

    Args:
        target: 目标邮箱地址。
        code: 明文验证码。

    Raises:
        AppError: 恒定抛出，提示 Resend Provider 尚未接入（错误码 50100）。
    """
    await _default_provider.send_code(target, code)
