"""
邮件 Provider：debug 实现。

不调用任何真实邮件网关，仅通过日志「模拟发送」，供本地开发与自动化测试使用。
"""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DebugEmailProvider:
    """
    Debug email adapter that logs instead of calling a real mail gateway.
    """

    async def send_code(self, email: str, code: str) -> None:
        """
        Simulate sending an email verification code.

        Args:
            email: Target mailbox address.
            code: Plaintext verification code.
        """
        # 生产日志（INFO 级）只提示「已发送」，不泄露验证码明文
        logger.info("[EMAIL-DEBUG] 验证码已发送 target=%s", email)
        settings = get_settings()
        if settings.debug:
            logger.debug("[EMAIL-DEBUG] target=%s code=%s", email, code)


_default_provider = DebugEmailProvider()


async def send_code(target: str, code: str) -> None:
    """
    模拟发送邮件验证码：写日志代替真实调用（模块级兼容包装）。

    Args:
        target: 目标邮箱地址。
        code: 明文验证码。
    """
    await _default_provider.send_code(target, code)
