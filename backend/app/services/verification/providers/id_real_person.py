"""
身份核验 Provider C：实人核验（活体检测 + 人脸比对），委托第三方厂商完成。

M0 阶段仅提供 stub：真实厂商对接（腾讯云慧眼 / 阿里云实人认证等）留待后续任务接入，
接口预留 ``face_token`` 用于接收前端 SDK 认证结果，当前统一表现为「未配置 / 未接入」。
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.schemas.common import AppError

logger = logging.getLogger(__name__)


class RealPersonIdentityProvider:
    """
    Real-person identity adapter (liveness + face match) delegating to a vendor.
    """

    async def verify(
        self,
        *,
        real_name: str,
        id_card: str,
        face_token: str | None = None,
    ) -> None:
        """
        Verify name, ID card, and face authentication result.

        Args:
            real_name: Legal name (masked in logs only).
            id_card: 18-digit ID card number.
            face_token: Face-verification token from frontend SDK.

        Raises:
            AppError: Provider not configured or not integrated (code ``50100``).
        """
        settings = get_settings()

        # DEBUG 环境：跳过真实实人核验，直接放行，便于本地/测试联调
        if settings.debug:
            logger.info(
                "[DEBUG] 实人核验已跳过 real_name=%s face_token_present=%s",
                _mask_real_name(real_name),
                face_token is not None,
            )
            return

        # 正式环境：stub 与其他尚未实现的厂商标识均视为「未真正接入」，统一抛出 50100
        if settings.id_real_person_provider == "stub":
            raise AppError(50100, "实人核验 Provider 未配置", http_status=501)
        raise AppError(50100, "实人核验 Provider 尚未接入", http_status=501)


_default_provider = RealPersonIdentityProvider()


async def verify_real_person(
    *,
    real_name: str,
    id_card: str,
    face_token: str | None = None,
) -> None:
    """
    执行实人核验：校验姓名、身份证号与人脸认证结果是否一致（模块级兼容包装）。

    Args:
        real_name: 真实姓名（仅用于日志脱敏展示，不落库）。
        id_card: 18 位身份证号原文（本函数不做格式校验，调用前应已由上层校验）。
        face_token: 前端人脸核身 SDK 返回的认证凭证；stub 阶段仅接收，不做实际校验。

    Raises:
        AppError: 非 DEBUG 环境下，Provider 未配置或未接入真实厂商时抛出（错误码 50100）。
    """
    await _default_provider.verify(
        real_name=real_name,
        id_card=id_card,
        face_token=face_token,
    )


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
