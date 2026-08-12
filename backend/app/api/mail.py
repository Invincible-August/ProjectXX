"""邮件 / 赠送 HTTP 路由（M7 L3）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_mail_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.mail import GiftSendRequest, MailSendRequest
from app.services.mail_service import MailService

router = APIRouter(tags=["mail"])


@router.get("/mail", response_model=None)
async def mail_list(
    svc: MailService = Depends(get_mail_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """收件箱列表。"""
    return success(await svc.list_mail(current_user))


@router.post("/mail", response_model=None)
async def mail_send(
    body: MailSendRequest,
    svc: MailService = Depends(get_mail_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发送无附件玩家信。"""
    return success(
        await svc.send_player_mail(
            current_user,
            to_character_id=body.to_character_id,
            to_name=body.to_name,
            subject_zh=body.subject_zh,
            body_zh=body.body_zh,
        ),
    )


@router.post("/mail/{mail_id}/read", response_model=None)
async def mail_read(
    mail_id: int,
    svc: MailService = Depends(get_mail_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """标记已读。"""
    return success(await svc.mark_read(current_user, mail_id))


@router.post("/mail/{mail_id}/claim", response_model=None)
async def mail_claim(
    mail_id: int,
    svc: MailService = Depends(get_mail_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """领取附件（幂等 40120）。"""
    return success(await svc.claim(current_user, mail_id))


@router.post("/gifts", response_model=None)
async def gifts_send(
    body: GiftSendRequest,
    svc: MailService = Depends(get_mail_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """赠送道友（附件入对方邮箱）。"""
    return success(
        await svc.send_gift(
            current_user,
            to_character_id=body.to_character_id,
            to_name=body.to_name,
            spirit_stones=body.spirit_stones,
            items=[row.model_dump() for row in body.items],
            note_zh=body.note_zh,
        ),
    )
