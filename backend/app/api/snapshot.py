"""防守快照 HTTP 路由（M3 · S6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_play_gate, get_snapshot_service
from app.db.models import User
from app.schemas.common import success
from app.services.play_gate import PlayGate
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


@router.get("/defense/me", response_model=None)
async def my_snapshot(
    service: SnapshotService = Depends(get_snapshot_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    我的防守快照摘要（读取路径触发惰性每日补刷）。

    返回:
        dict: ``{snapshot, updated_at, cooldown_remaining_seconds}``。
    """
    character = await gate.require_character(current_user)
    return success(await service.my_summary(character))


@router.post("/defense/update", response_model=None)
async def manual_update(
    service: SnapshotService = Depends(get_snapshot_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    手动更新防守快照（冷却 1 小时；渡劫等禁止态 → 40046）。

    返回:
        dict: 新快照 + 冷却剩余。
    """
    character = await gate.require_character(current_user)
    return success(await service.manual_update(character))


@router.get("/defense/{character_id}", response_model=None)
async def preview_snapshot(
    character_id: int,
    service: SnapshotService = Depends(get_snapshot_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    攻打前预览目标快照（公开战斗用字段；无快照 → 40048）。

    参数:
        character_id: 目标角色 id。
    """
    return success(await service.preview_for_attack(character_id))
