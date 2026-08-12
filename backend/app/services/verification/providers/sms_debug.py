"""
短信 Provider：debug 实现。

不调用任何真实短信网关，仅通过日志「模拟发送」，供本地开发与自动化测试使用。
"""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DebugSmsProvider:
    """
    Debug SMS adapter that logs instead of calling a real gateway.

    INFO logs omit the plaintext code; DEBUG logs include it when ``settings.debug``.
    """

    async def send_code(self, phone: str, code: str) -> None:
        """
        Simulate sending an SMS verification code.

        Args:
            phone: Target mobile number.
            code: Plaintext verification code.
        """
        # 生产日志（INFO 级）只提示「已发送」，不泄露验证码明文
        logger.info("[SMS-DEBUG] 验证码已发送 target=%s", phone)
        settings = get_settings()
        if settings.debug:
            # 仅 DEBUG 环境下按 DEBUG 级别打印明文码，便于本地联调
            logger.debug("[SMS-DEBUG] target=%s code=%s", phone, code)


_default_provider = DebugSmsProvider()


async def send_code(target: str, code: str) -> None:
    """
    模拟发送短信验证码：写日志代替真实调用（模块级兼容包装）。

    Args:
        target: 目标手机号。
        code: 明文验证码。
    """
    await _default_provider.send_code(target, code)
