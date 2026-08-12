"""
邮件 Provider：阿里云邮件推送服务骨架。

函数签名与其他邮件 Provider 对齐，便于工厂函数统一调用；真实的阿里云邮件推送 SDK 接入
（AccessKey、发信地址、模板等）留待后续任务实现，目前统一抛出 ``AppError(50100)``。
"""

from __future__ import annotations

import logging

from app.schemas.common import AppError

logger = logging.getLogger(__name__)


class AliyunEmailProvider:
    """
    Aliyun mail-push adapter skeleton (SDK not yet integrated).
    """

    async def send_code(self, email: str, code: str) -> None:
        """
        Send verification code via Aliyun mail push (not implemented).

        Args:
            email: Target mailbox address.
            code: Plaintext verification code.

        Raises:
            AppError: Always raised with code ``50100`` until SDK is wired.
        """
        # TODO(Task 4+): 接入阿里云邮件推送 SDK（AccessKeyId/Secret 从环境变量读取，禁止硬编码）
        _ = email, code
        logger.warning("[EMAIL-ALIYUN] Provider 尚未接入，拒绝发送")
        raise AppError(50100, "阿里云邮件 Provider 尚未接入", http_status=501)


_default_provider = AliyunEmailProvider()


async def send_code(target: str, code: str) -> None:
    """
    通过阿里云邮件推送发送验证码邮件（骨架，尚未接入真实 SDK）（模块级兼容包装）。

    Args:
        target: 目标邮箱地址。
        code: 明文验证码。

    Raises:
        AppError: 恒定抛出，提示阿里云邮件 Provider 尚未接入（错误码 50100）。
    """
    await _default_provider.send_code(target, code)
