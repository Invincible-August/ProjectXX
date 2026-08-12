"""战斗 HTTP 路由（M1 教学 PVE → M3 棋盘化 + PVP + 体力）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.deps import (
    get_autochess_service,
    get_current_user,
    get_play_gate,
    get_stamina_service,
)
from app.core.idempotency import run_with_idempotency
from app.db.models import User
from app.schemas.battle import PveBattleRequest, PvpAttackRequest
from app.schemas.common import success
from app.services.autochess_service import AutochessService
from app.services.play_gate import PlayGate
from app.services.stamina_service import StaminaService

router = APIRouter(prefix="/battle", tags=["battle"])


@router.post("/pve", response_model=None)
async def start_pve(
    request: Request,
    payload: PveBattleRequest | None = None,
    service: AutochessService = Depends(get_autochess_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    发起棋盘化 PVE 讨伐（M3 战报 schema；体力不足 → 40049）。

    支持 ``Idempotency-Key``：同一 Key 不二次扣体力/发奖。

    参数:
        request: 原始请求（读幂等头）。
        payload: ``{monster_id, preset_slot?}``；缺省打教学怪、取进攻预设。

    返回:
        dict: ``{result, seed, report, rewards, stamina, character}``（响应即战报，零持久化）。
    """
    body = payload or PveBattleRequest()

    async def _action() -> dict:
        data = await service.start_pve(
            current_user,
            monster_id=body.monster_id,
            preset_slot=body.preset_slot,
            use_dao=bool(body.use_dao),
        )
        return success(data)

    return await run_with_idempotency(
        request=request,
        user_id=int(current_user.id),
        action=_action,
    )


@router.post("/pvp/attack", response_model=None)
async def start_pvp_attack(
    request: Request,
    payload: PvpAttackRequest,
    service: AutochessService = Depends(get_autochess_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    攻打目标玩家的防守快照（异步非对称；对方零打扰）。

    支持 ``Idempotency-Key``。

    参数:
        request: 原始请求（读幂等头）。
        payload: ``{target_character_id, preset_slot?}``。

    返回:
        dict: 同 PVE 结构，另含 ``target`` 摘要。
    """

    async def _action() -> dict:
        data = await service.start_pvp(
            current_user,
            target_character_id=payload.target_character_id,
            preset_slot=payload.preset_slot,
        )
        return success(data)

    return await run_with_idempotency(
        request=request,
        user_id=int(current_user.id),
        action=_action,
    )


@router.get("/pve/monsters", response_model=None)
async def list_monsters(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    可挑战怪物列表（含体力消耗、编成规模、嘲讽光环摘要，供选怪面板展示）。

    返回:
        dict: ``{monsters: [...]}``；每项可含 ``taunt_auras``（§0.7）。
    """
    _ = current_user  # 鉴权门禁；列表本身只读配置
    return success({"monsters": AutochessService.list_pve_monsters_public()})


@router.get("/pvp/opponents", response_model=None)
async def list_opponents(
    service: AutochessService = Depends(get_autochess_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    可攻打对手列表（M3 占位：全服除自己外前 20 个角色）。

    返回:
        dict: ``{opponents: [...]}``。
    """
    character = await gate.require_character(current_user)
    return success({"opponents": await service.list_opponents(character)})


@router.get("/stamina", response_model=None)
async def read_stamina(
    service: StaminaService = Depends(get_stamina_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    当前体力读数（惰性恢复后）+ 上限 + 恢复速率。

    返回:
        dict: ``{left, cap, next_point_in_seconds, regen_per_minute}``。
    """
    character = await gate.require_character(current_user)
    return success(service.read(character))
