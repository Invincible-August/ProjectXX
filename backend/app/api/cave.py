"""Cave (洞府) HTTP: hub rooms + lab (研究室) research desk."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.research import router as lab_router
from app.constants.cave import CAVE_LABEL_ZH, CAVE_ROOMS
from app.core.deps import get_current_user, get_play_gate
from app.db.models import User
from app.schemas.common import success
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/cave", tags=["cave"])


@router.get("", response_model=None)
async def cave_overview(
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """洞府枢纽：当前开放的房间列表。"""
    await gate.require_character(current_user)
    return success(
        {
            "label_zh": CAVE_LABEL_ZH,
            "rooms": [dict(row) for row in CAVE_ROOMS],
        }
    )


router.include_router(lab_router, prefix="/lab")
