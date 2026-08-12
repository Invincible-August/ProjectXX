"""布阵 HTTP 路由（M3 · S1/S2/S5）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_formation_service, get_play_gate
from app.db.models import User
from app.schemas.common import success
from app.schemas.formation import SavePresetRequest, ValidatePlacementRequest
from app.services.formation_service import FormationService
from app.services.play_gate import PlayGate

router = APIRouter(prefix="/formation", tags=["formation"])


@router.get("/board-meta", response_model=None)
async def board_meta(
    service: FormationService = Depends(get_formation_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    棋盘只读元数据（尺寸 / 三区 / 默认部署格 / 镜像规则 / 种类闸门）。

    参数:
        service: 布阵应用服务。
        current_user: 当前用户（仅鉴权，不读角色）。

    返回:
        dict: 前端画盘与高亮所需的全部配置。
    """
    return success(service.board_meta())


@router.get("/presets", response_model=None)
async def list_presets(
    service: FormationService = Depends(get_formation_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    列出预设三槽 + 已解锁阵法 + 可上阵棋子清单 + 上阵上限。

    返回:
        dict: ``{presets, formations, bench, max_units}``。
    """
    character = await gate.require_character(current_user)
    return success(await service.list_presets(character))


@router.put("/presets/{slot}", response_model=None)
async def save_preset(
    slot: int,
    payload: SavePresetRequest,
    service: FormationService = Depends(get_formation_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    保存一个预设槽（占位校验失败 → 40041/40042/40043）。

    参数:
        slot: 槽位（0=进攻 / 1=防守 / 2=临时，可改名换定位）。
        payload: 预设内容。

    返回:
        dict: 保存后的预设。
    """
    character = await gate.require_character(current_user)
    data = await service.save_preset(
        character,
        slot,
        name=payload.name,
        role=payload.role,
        formation_id=payload.formation_id,
        units=[unit.model_dump() for unit in payload.units],
    )
    return success(data)


@router.post("/validate", response_model=None)
async def validate_placement(
    payload: ValidatePlacementRequest,
    service: FormationService = Depends(get_formation_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    干跑校验占位（编辑器实时反馈用；不落库）。

    返回:
        dict: ``{valid: true}``；非法时按业务码抛错。
    """
    character = await gate.require_character(current_user)
    await service.validate_units(
        character,
        [unit.model_dump() for unit in payload.units],
        payload.formation_id,
    )
    return success({"valid": True})


@router.get("/bench", response_model=None)
async def bench_units(
    service: FormationService = Depends(get_formation_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    可上阵棋子源（M4：本体 / 化身 / 灵宠 / 傀儡）。

    Returns:
        dict: ``{bench: [...]}``。
    """
    character = await gate.require_character(current_user)
    bench = await service.bench_units(character)
    return success({"bench": bench})
