"""GM HTTP 路由（仅 development）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_gm_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.gm import GmSetCharacterRequest
from app.services.gm_service import GmService

router = APIRouter(prefix="/gm", tags=["gm"])


@router.post("/character/set", response_model=None)
async def gm_set_character(
    payload: GmSetCharacterRequest,
    service: GmService = Depends(get_gm_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    GM 写入角色字段；非 development / GM 关闭 → ``40310``。

    Args:
        payload: 可选字段集合。
        service: GM 应用服务。
        current_user: 当前用户。

    Returns:
        dict: 最新角色信封。
    """
    data = await service.gm_set_character(
        current_user,
        major_realm=payload.major_realm,
        realm_stage=payload.realm_stage,
        cultivation_points=payload.cultivation_points,
        realm_progress=payload.realm_progress,
        body_tempering_points=payload.body_tempering_points,
        crafting_exp=payload.crafting_exp,
        breakthrough_grade=payload.breakthrough_grade,
        membership_tier=payload.membership_tier,
        spirit_stones=payload.spirit_stones,
        idle_direction=payload.idle_direction,
        status=payload.status,
        clear_offline_pending=payload.clear_offline_pending,
        set_stamina=payload.set_stamina,
        trial_puppet_count=payload.trial_puppet_count,
        reset_snapshot_cooldown=payload.reset_snapshot_cooldown,
        force_refresh_snapshot=payload.force_refresh_snapshot,
        divine_sense_capacity_bonus=payload.divine_sense_capacity_bonus,
        array_craft_level=payload.array_craft_level,
        force_jindan=payload.force_jindan,
        grant_craft_materials=payload.grant_craft_materials,
        grant_test_pet=payload.grant_test_pet,
        clear_craft_jobs=payload.clear_craft_jobs,
        clear_divine_sense_backlash=payload.clear_divine_sense_backlash,
        force_shichen=payload.force_shichen,
        force_weather=payload.force_weather,
        start_tribulation=payload.start_tribulation,
        set_awaiting_ferry=payload.set_awaiting_ferry,
        force_ferry_timeout=payload.force_ferry_timeout,
        mark_story_node=payload.mark_story_node,
        fate_luck=payload.fate_luck,
        demonic_nature=payload.demonic_nature,
        force_yuanying_peak=payload.force_yuanying_peak,
        spirit_root_tags=payload.spirit_root_tags,
        force_tribulation_outcome=payload.force_tribulation_outcome,
        grant_acceptance_constitution=payload.grant_acceptance_constitution,
        force_true_immortal=payload.force_true_immortal,
        grant_dao_pool=payload.grant_dao_pool,
        set_dao_lord=payload.set_dao_lord,
        open_dao_challenge_window=payload.open_dao_challenge_window,
        open_dao_contest_now=payload.open_dao_contest_now,
        clear_dao_challenge_cooldown=payload.clear_dao_challenge_cooldown,
        push_world_env=payload.push_world_env,
        set_dao_qi=payload.set_dao_qi,
        set_dao_level=payload.set_dao_level,
        lock_fate_dao=payload.lock_fate_dao,
        m6_quick_kit=payload.m6_quick_kit,
    )
    return success(data)
