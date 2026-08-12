"""M4 灵宠 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import (
    get_current_user,
    get_pet_duel_service,
    get_pet_explore_service,
    get_pet_hatch_service,
    get_pet_service,
    get_play_gate,
)
from app.db.models import User
from app.schemas.common import AppError, success
from app.schemas.pets import (
    PetAffixRerollValueRequest,
    PetCaptureTestRequest,
    PetDuelAutoRequest,
    PetDuelNpcStartRequest,
    PetDuelTurnRequest,
    PetExploreAutoRequest,
    PetExploreCaptureRequest,
    PetExploreEncounterRequest,
    PetFeedRequest,
    PetHatchStartRequest,
    PetPatchRequest,
    PetSectRerollTypeRequest,
    PetSkillLearnBookRequest,
    PetSkillLearnPoolRequest,
    PetSkillsEquipRequest,
)
from app.services.pet_duel_service import PetDuelService
from app.services.pet_explore_service import PetExploreService
from app.services.pet_hatch_service import PetHatchService
from app.services.pet_service import PetService, spirit_beast_sect_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

router = APIRouter(prefix="/pets", tags=["pets"])


@router.get("", response_model=None)
async def list_pets(
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """灵宠列表。"""
    character = await gate.require_character(current_user)
    pets = await service.list_pets(character)
    cfg = get_game_config().pets
    return success({"pets": pets, "hold_cap": cfg.hold_cap})


@router.get("/catalog", response_model=None)
async def pets_catalog(
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    灵宠图鉴：注册表投影 + seen/caught。

    加 YAML/后台物种后无需改代码即可出现。
    """
    character = await gate.require_character(current_user)
    data = await service.catalog(character)
    return success(data)


@router.get("/hatch", response_model=None)
async def pet_hatch_list(
    service: PetHatchService = Depends(get_pet_hatch_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """孵化面板：蛋目录 + 会话（N5）。"""
    character = await gate.require_character(current_user)
    data = await service.list_state(character)
    return success(data)


@router.post("/hatch/start", response_model=None)
async def pet_hatch_start(
    payload: PetHatchStartRequest,
    service: PetHatchService = Depends(get_pet_hatch_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """消耗蛋开启孵化会话。"""
    character = await gate.require_character(current_user)
    data = await service.start(character, egg_item_id=payload.egg_item_id)
    return success(data)


@router.post("/hatch/{job_id}/claim", response_model=None)
async def pet_hatch_claim(
    job_id: int,
    service: PetHatchService = Depends(get_pet_hatch_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """领取孵化完成的灵宠入园。"""
    character = await gate.require_character(current_user)
    data = await service.claim(character, job_id)
    return success(data)


@router.get("/sect/affix/type-reroll/preview", response_model=None)
async def pet_sect_type_reroll_preview(
    pet_id: int | None = None,
    slot_index: int | None = None,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    灵兽宗改词条类型预览（PET-D06）。

    返回费用公式；可选 ``pet_id`` + ``slot_index`` 给出单槽报价。
    """
    character = await gate.require_character(current_user)
    data = await service.type_reroll_preview_quote(
        character,
        pet_id=pet_id,
        slot_index=slot_index,
    )
    return success(data)


@router.get("/sect/affix/type-reroll/status", response_model=None)
async def pet_sect_type_reroll_status(
    pet_id: int,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """各槽改类型次数与下次费用（PET-D06）。"""
    character = await gate.require_character(current_user)
    data = await service.type_reroll_status(character, pet_id)
    return success(data)


@router.post("/sect/affix/reroll-type", response_model=None)
async def pet_sect_reroll_type(
    payload: PetSectRerollTypeRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    改词条类型：重 roll 指定槽类型/品级/数值并扣灵石。

    Raises:
        AppError: 50110 设施未开放 / 40061 槽不可改 / 40012 灵石不足。
    """
    _ = payload.idempotency_key  # 契约预留；本期不落幂等表
    if not spirit_beast_sect_enabled():
        raise AppError(
            code=50110,
            message="灵兽宗设施未开放（后台 sects.facilities.spirit_beast_sect）",
            http_status=501,
        )
    character = await gate.require_character(current_user)
    data = await service.reroll_affix_type(
        character,
        payload.pet_id,
        slot_index=payload.slot_index,
    )
    return success(data)


@router.post("/capture_test", response_model=None)
async def capture_test_pet(
    payload: PetCaptureTestRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """测试捕获样本宠。"""
    character = await gate.require_character(current_user)
    data = await service.capture_test(character, species_id=payload.species_id)
    return success(data)


@router.get("/explore/preview", response_model=None)
async def pet_explore_preview(
    region_id: str = "default",
    service: PetExploreService = Depends(get_pet_explore_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """野外遭遇池预览（M4-D04c）。"""
    character = await gate.require_character(current_user)
    data = await service.preview(character, region_id=region_id)
    return success(data)


@router.post("/explore/encounter", response_model=None)
async def pet_explore_encounter(
    payload: PetExploreEncounterRequest,
    service: PetExploreService = Depends(get_pet_explore_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """掷一次野外遭遇（区×时×天）。"""
    character = await gate.require_character(current_user)
    data = await service.encounter(
        character,
        region_id=payload.region_id,
        seed=payload.seed,
    )
    return success(data)


@router.post("/explore/capture", response_model=None)
async def pet_explore_capture(
    payload: PetExploreCaptureRequest,
    service: PetExploreService = Depends(get_pet_explore_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """野外捕获（诱灵草 + 全因子骰；成功 wild_capture 入园）。"""
    character = await gate.require_character(current_user)
    data = await service.capture(
        character,
        encounter_id=payload.encounter_id,
        seed=payload.seed,
    )
    return success(data)


@router.post("/explore/auto", response_model=None)
async def pet_explore_auto(
    payload: PetExploreAutoRequest,
    service: PetExploreService = Depends(get_pet_explore_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """自动探索捕：遇可捕灵兽则尝试一次。"""
    character = await gate.require_character(current_user)
    data = await service.auto_capture(
        character,
        region_id=payload.region_id,
        seed=payload.seed,
    )
    return success(data)


@router.post("/duel/npc/start", response_model=None)
async def pet_duel_npc_start(
    payload: PetDuelNpcStartRequest,
    service: PetDuelService = Depends(get_pet_duel_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开启灵宠 vs NPC 回合制对战（PET-D05）。"""
    character = await gate.require_character(current_user)
    data = await service.start_npc(
        character,
        pet_id=payload.pet_id,
        npc_id=payload.npc_id,
        seed=payload.seed,
    )
    return success(data)


@router.post("/duel/npc/auto", response_model=None)
async def pet_duel_npc_auto(
    payload: PetDuelAutoRequest,
    service: PetDuelService = Depends(get_pet_duel_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """一键自动打完 vs NPC（seed 可复现）。"""
    character = await gate.require_character(current_user)
    data = await service.auto_npc(
        character,
        pet_id=payload.pet_id,
        npc_id=payload.npc_id,
        seed=payload.seed,
    )
    return success(data)


@router.get("/duel/{duel_id}", response_model=None)
async def pet_duel_get(
    duel_id: str,
    service: PetDuelService = Depends(get_pet_duel_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """读取对战快照。"""
    character = await gate.require_character(current_user)
    data = await service.get_duel(character, duel_id)
    return success(data)


@router.post("/duel/{duel_id}/turn", response_model=None)
async def pet_duel_turn(
    duel_id: str,
    payload: PetDuelTurnRequest,
    service: PetDuelService = Depends(get_pet_duel_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """提交选招并结算一回合。"""
    character = await gate.require_character(current_user)
    data = await service.turn(character, duel_id, skill_id=payload.skill_id)
    return success(data)


@router.post("/{pet_id}/upgrade", response_model=None)
async def upgrade_pet(
    pet_id: int,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """灵宠升级占位。"""
    character = await gate.require_character(current_user)
    data = await service.upgrade(character, pet_id)
    return success(data)


@router.post("/{pet_id}/grade-up", response_model=None)
async def grade_up_pet(
    pet_id: int,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    升阶：扣灵石、品阶+1、追加 1 条随机词条（PET-D01）。
    """
    character = await gate.require_character(current_user)
    data = await service.grade_up(character, pet_id)
    return success(data)


@router.post("/{pet_id}/feed", response_model=None)
async def feed_pet(
    pet_id: int,
    payload: PetFeedRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """丹药喂养：扣兽丹、涨面板；超上限拒绝（PET-D04）。"""
    character = await gate.require_character(current_user)
    data = await service.feed(
        character,
        pet_id,
        item_id=payload.item_id,
        quantity=payload.quantity,
    )
    return success(data)


@router.post("/{pet_id}/affix/reroll-value", response_model=None)
async def reroll_pet_affix_value(
    pet_id: int,
    payload: PetAffixRerollValueRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    数值-only 洗炼：不改类型与品级（PET-D01）。
    """
    character = await gate.require_character(current_user)
    data = await service.reroll_affix_value(
        character,
        pet_id,
        slot_index=payload.slot_index,
    )
    return success(data)


@router.post("/{pet_id}/skills/equip", response_model=None)
async def equip_pet_skills(
    pet_id: int,
    payload: PetSkillsEquipRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """装备最多 4 个已学主动技能（PET-D02）。"""
    character = await gate.require_character(current_user)
    data = await service.equip_skills(character, pet_id, equipped=list(payload.equipped))
    return success(data)


@router.post("/{pet_id}/skills/learn", response_model=None)
async def learn_pet_skill_from_pool(
    pet_id: int,
    payload: PetSkillLearnPoolRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """从物种技能池领悟技能（无等级门槛占位）。"""
    character = await gate.require_character(current_user)
    data = await service.learn_skill_from_pool(
        character,
        pet_id,
        skill_id=payload.skill_id,
    )
    return success(data)


@router.post("/{pet_id}/skills/learn_book", response_model=None)
async def learn_pet_skill_from_book(
    pet_id: int,
    payload: PetSkillLearnBookRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """消耗技能书学会技能（校验 scope）。"""
    character = await gate.require_character(current_user)
    data = await service.learn_skill_from_book(
        character,
        pet_id,
        book_id=payload.book_id,
    )
    return success(data)


@router.patch("/{pet_id}", response_model=None)
async def patch_pet(
    pet_id: int,
    payload: PetPatchRequest,
    service: PetService = Depends(get_pet_service),
    gate: PlayGate = Depends(get_play_gate),
    current_user: User = Depends(get_current_user),
) -> dict:
    """更新灵宠昵称或布阵偏好。"""
    character = await gate.require_character(current_user)
    data = await service.patch_pet(
        character,
        pet_id,
        nickname=payload.nickname,
        is_deploy_preferred=payload.is_deploy_preferred,
    )
    return success(data)
