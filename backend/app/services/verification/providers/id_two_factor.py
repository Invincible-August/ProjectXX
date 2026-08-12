"""
身份核验 Provider B：二要素核验（姓名 + 身份证号一致性），委托第三方厂商完成。

M0 阶段仅提供 stub：真实厂商对接（阿里云 / 腾讯云等）留待后续任务接入，
当前统一表现为「未配置 / 未接入」，通过 ``AppError(50100)`` 明确告知调用方，
避免误判为核验通过。
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.schemas.common import AppError

logger = logging.getLogger(__name__)


class TwoFactorIdentityProvider:
    """
    Two-factor identity adapter (name + ID card) delegating to a third-party vendor.
    """

    async def verify(
        self,
        *,
        real_name: str,
        id_card: str,
        face_token: str | None = None,
    ) -> None:
        """
        Verify name and ID-card consistency via configured vendor.

        Args:
            real_name: Legal name (masked in logs only).
            id_card: 18-digit ID card number.
            face_token: Ignored in two-factor mode.

        Raises:
            AppError: Provider not configured or not integrated (code ``50100``).
        """
        _ = id_card, face_token
        settings = get_settings()

        # DEBUG 环境：跳过真实二要素核验，直接放行，便于本地/测试联调
        if settings.debug:
            logger.info("[DEBUG] 二要素核验已跳过 real_name=%s", _mask_real_name(real_name))
            return

        # 正式环境：无论 provider 配置为 stub 还是其他尚未实现的厂商标识，
        # 均视为「未真正接入」，统一抛出 50100，绝不能默认放行
        if settings.id_two_factor_provider == "stub":
            raise AppError(50100, "二要素 Provider 未配置", http_status=501)
        raise AppError(50100, "二要素 Provider 尚未接入", http_status=501)


_default_provider = TwoFactorIdentityProvider()


async def verify_two_factor(*, real_name: str, id_card: str) -> None:
    """
    执行二要素核验：校验姓名与身份证号是否一致（模块级兼容包装）。

    Args:
        real_name: 真实姓名（仅用于日志脱敏展示，不落库）。
        id_card: 18 位身份证号原文（本函数不做格式校验，调用前应已由上层校验）。

    Raises:
        AppError: 非 DEBUG 环境下，Provider 未配置或未接入真实厂商时抛出（错误码 50100）。
    """
    await _default_provider.verify(real_name=real_name, id_card=id_card)


def _mask_real_name(real_name: str) -> str:
    """
    对姓名做最小化脱敏，避免日志中出现完整真实姓名。

    Args:
        real_name: 真实姓名原文。

    Returns:
        str: 仅保留首字，其余以 ``*`` 替代；空字符串原样返回。
    """
    if not real_name:
        return real_name
    return real_name[0] + "*" * (len(real_name) - 1)
