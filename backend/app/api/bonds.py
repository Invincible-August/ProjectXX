"""道侣 / 炉鼎 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_bond_service, get_current_user
from app.db.models import User
from app.schemas.common import success
from app.schemas.social_trade import CompanionApplyRequest
from app.services.bond_service import BondService

router = APIRouter(prefix="/bonds", tags=["bonds"])


@router.get("", response_model=None)
async def bonds_list(
    svc: BondService = Depends(get_bond_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """道侣 / 炉鼎列表。"""
    return success(await svc.list_bonds(current_user))


@router.post("/companions", response_model=None)
async def companion_apply(
    body: CompanionApplyRequest,
    svc: BondService = Depends(get_bond_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """申请道侣。"""
    return success(
        await svc.apply_companion(
            current_user,
            target_character_id=body.target_character_id,
            target_name=body.target_name,
        ),
    )


@router.post("/vessels", response_model=None)
async def vessel_apply(
    body: CompanionApplyRequest,
    svc: BondService = Depends(get_bond_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """炉鼎申请口子（当前拒绝）。"""
    return success(
        await svc.apply_vessel(
            current_user,
            target_character_id=body.target_character_id,
            target_name=body.target_name,
        ),
    )


@router.post("/{bond_id}/accept", response_model=None)
async def bond_accept(
    bond_id: int,
    svc: BondService = Depends(get_bond_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认道侣。"""
    return success(await svc.accept(current_user, bond_id))


@router.post("/{bond_id}/reject", response_model=None)
async def bond_reject(
    bond_id: int,
    svc: BondService = Depends(get_bond_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拒绝道侣。"""
    return success(await svc.reject(current_user, bond_id))


@router.delete("/{bond_id}", response_model=None)
async def bond_remove(
    bond_id: int,
    svc: BondService = Depends(get_bond_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """解除道侣/炉鼎。"""
    return success(await svc.remove(current_user, bond_id))
