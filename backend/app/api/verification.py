"""核验相关 HTTP 路由（发码 / 确认 / 身份核验 / 模式查询）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_verification_service
from app.schemas.common import success
from app.schemas.verification import (
    EmailConfirmRequest,
    EmailSendRequest,
    IdSubmitRequest,
    SmsConfirmRequest,
    SmsSendRequest,
)
from app.services.verification.service import VerificationService

router = APIRouter(prefix="/verification", tags=["verification"])


@router.get("/modes", response_model=None)
async def get_modes() -> dict:
    """
    返回当前核验模式与各 Provider 配置（无鉴权）。

    Returns:
        dict: 含 ``debug`` / ``id_verify_mode`` / 各 provider 名的统一信封。
    """
    return success(VerificationService.get_modes())


@router.post("/sms/send", response_model=None)
async def sms_send(
    payload: SmsSendRequest,
    verification: VerificationService = Depends(get_verification_service),
) -> dict:
    """
    向手机号发送短信验证码。

    Args:
        payload: 含规范化后的 ``phone``。
        verification: 核验应用服务。

    Returns:
        dict: 成功时 ``data`` 为 ``None``；过频抛 ``AppError(40011)``。
    """
    await verification.send_sms(payload.phone)
    return success(None)


@router.post("/sms/confirm", response_model=None)
async def sms_confirm(
    payload: SmsConfirmRequest,
    verification: VerificationService = Depends(get_verification_service),
) -> dict:
    """
    确认短信验证码并签发一次性 ``sms_ticket``。

    Args:
        payload: 手机号与验证码。
        verification: 核验应用服务。

    Returns:
        dict: ``data.ticket`` 为一次性票据；错码/过期抛 ``AppError(40010)``。
    """
    ticket = await verification.confirm_sms(payload.phone, payload.code)
    return success({"ticket": ticket})


@router.post("/email/send", response_model=None)
async def email_send(
    payload: EmailSendRequest,
    verification: VerificationService = Depends(get_verification_service),
) -> dict:
    """
    向邮箱发送验证码。

    Args:
        payload: 含规范化后的 ``email``。
        verification: 核验应用服务。

    Returns:
        dict: 成功时 ``data`` 为 ``None``；过频抛 ``AppError(40011)``。
    """
    await verification.send_email(payload.email)
    return success(None)


@router.post("/email/confirm", response_model=None)
async def email_confirm(
    payload: EmailConfirmRequest,
    verification: VerificationService = Depends(get_verification_service),
) -> dict:
    """
    确认邮箱验证码并签发一次性 ``email_ticket``。

    Args:
        payload: 邮箱与验证码。
        verification: 核验应用服务。

    Returns:
        dict: ``data.ticket`` 为一次性票据；错码/过期抛 ``AppError(40010)``。
    """
    ticket = await verification.confirm_email(payload.email, payload.code)
    return success({"ticket": ticket})


@router.post("/id/submit", response_model=None)
async def id_submit(
    payload: IdSubmitRequest,
    verification: VerificationService = Depends(get_verification_service),
) -> dict:
    """
    提交身份核验材料并签发一次性 ``id_ticket``。

    DEBUG 下直接签发；正式模式按 ``id_verify_mode`` 调用对应 Provider。

    Args:
        payload: 姓名、证件号、可选 ``face_token``。
        verification: 核验应用服务。

    Returns:
        dict: ``data.ticket`` 为一次性票据。
    """
    ticket = await verification.submit_id(
        real_name=payload.real_name,
        id_card=payload.id_card,
        face_token=payload.face_token,
    )
    return success({"ticket": ticket})
