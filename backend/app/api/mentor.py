"""师徒 HTTP 路由（M7 L6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_mentor_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.mentor import MentorApplyRequest
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
    """传功。"""
    return success(await svc.pass_cultivation(current_user))


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
