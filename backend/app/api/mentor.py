"""师徒 HTTP 路由（M7 L6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_mentor_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.mentor import (
    MentorApplyRequest,
    MentorDirectRequest,
    MentorLessonRequest,
    MentorStudyRequest,
    MentorTeachRequest,
)
from app.services.mentor_service import MentorService

router = APIRouter(prefix="/mentor", tags=["mentor"])


@router.get("/me", response_model=None)
async def mentor_me(
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """师徒名录与任务。"""
    return success(await svc.me(current_user))


@router.post("/apply", response_model=None)
async def mentor_apply(
    body: MentorApplyRequest,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拜师或收徒申请。"""
    return success(
        await svc.apply(
            current_user,
            target_character_id=body.target_character_id,
            target_name=body.target_name,
            intent=body.intent,
        ),
    )


@router.post("/{bond_id}/accept", response_model=None)
async def mentor_accept(
    bond_id: int,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认申请。"""
    return success(await svc.accept(current_user, bond_id))


@router.post("/{bond_id}/reject", response_model=None)
async def mentor_reject(
    bond_id: int,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拒绝申请。"""
    return success(await svc.reject(current_user, bond_id))


@router.post("/quests/{quest_id}/progress", response_model=None)
async def mentor_quest_progress(
    quest_id: str,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """推进任务。"""
    return success(await svc.progress_quest(current_user, quest_id))


@router.post("/pass", response_model=None)
async def mentor_pass(
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兼容旧传功：等价传道·修为。"""
    return success(await svc.pass_cultivation(current_user))


@router.post("/lesson", response_model=None)
async def mentor_lesson(
    body: MentorLessonRequest,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """日课三选一：传道 / 授业 / 解惑。"""
    return success(
        await svc.teach_lesson(
            current_user,
            kind=body.kind,
            resource=body.resource,
            target_id=body.target_id,
        ),
    )


@router.post("/teach", response_model=None)
async def mentor_teach(
    body: MentorTeachRequest,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """传授功法或配方图纸（多日累计）。"""
    return success(
        await svc.teach_item(
            current_user,
            item_kind=body.item_kind,
            item_id=body.item_id,
        ),
    )


@router.post("/study", response_model=None)
async def mentor_study(
    body: MentorStudyRequest,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """徒弟请学师傅功法（每日一次，可叠加未完成传授进度）。"""
    return success(
        await svc.study_technique(
            current_user,
            technique_id=body.technique_id,
        ),
    )


@router.post("/direct", response_model=None)
async def mentor_set_direct(
    body: MentorDirectRequest,
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """师傅设置亲传弟子（最多三人；授业/解惑日课 +1）。"""
    return success(
        await svc.set_direct_disciples(
            current_user,
            apprentice_character_ids=list(body.apprentice_character_ids or []),
        ),
    )


@router.post("/graduate", response_model=None)
async def mentor_graduate(
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """出师。"""
    return success(await svc.graduate(current_user))


@router.post("/dissolve", response_model=None)
async def mentor_dissolve(
    svc: MentorService = Depends(get_mentor_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """解除。"""
    return success(await svc.dissolve(current_user))
