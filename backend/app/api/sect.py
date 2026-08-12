"""宗门 HTTP 路由（M7 L1 + M7-V+ 组织/设施）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import (
    get_current_user,
    get_sect_facility_service,
    get_sect_org_service,
    get_sect_service,
)
from app.db.models import User
from app.schemas.common import success
from app.schemas.sect import (
    SectAnnounceRequest,
    SectBuffToggleRequest,
    SectCreateRequest,
    SectDonationReviewRequest,
    SectFormationActiveRequest,
    SectFormationAllocateRequest,
    SectFormationDonateRequest,
    SectFormationExchangeRequest,
    SectFormationSelectRequest,
    SectHerbExchangeRequest,
    SectHerbPlantRequest,
    SectJoinRequest,
    SectPetExchangeRequest,
    SectQuestAcceptRequest,
    SectQuestCompleteRequest,
    SectRankAppointRequest,
    SectRankApplyRequest,
    SectScriptureDonateRequest,
    SectScriptureExchangeRequest,
    SectShopBuyRequest,
    SectTreasuryAllocateRequest,
    SectTreasuryDepositRequest,
    SectTreasuryExchangeRequest,
    SectWarStartRequest,
    SectWorkshopBlueprintDonateRequest,
    SectWorkshopBlueprintExchangeRequest,
    SectWorkshopHireRequest,
)
from app.services.sect_facility_service import SectFacilityService
from app.services.sect_org_service import SectOrgService
from app.services.sect_service import SectService

router = APIRouter(prefix="/sect", tags=["sect"])


@router.get("/me", response_model=None)
async def sect_me(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """我的宗门摘要。"""
    return success(await svc.get_me(current_user))


@router.get("/npc", response_model=None)
async def sect_npc_list(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """NPC 宗门列表。"""
    return success(await svc.list_npc(current_user))


@router.post("/join", response_model=None)
async def sect_join(
    body: SectJoinRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拜入 NPC 宗门。"""
    return success(await svc.join(current_user, template_id=body.template_id))


@router.post("/create", response_model=None)
async def sect_create(
    body: SectCreateRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """自建宗门（须选专精）。"""
    return success(
        await svc.create(
            current_user,
            name=body.name,
            motto=body.motto,
            specialty=body.specialty,
        ),
    )


@router.get("/overview", response_model=None)
async def sect_overview(
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """宗门组织总览（等级/设施/buff/权限）。"""
    return success(await svc.overview(current_user))


@router.get("/members", response_model=None)
async def sect_members(
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """门众列表。"""
    return success(await svc.list_members(current_user))


@router.get("/ranks/applications", response_model=None)
async def sect_rank_applications(
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """职位申请列表。"""
    return success(await svc.list_applications(current_user))


@router.post("/ranks/apply", response_model=None)
async def sect_rank_apply(
    body: SectRankApplyRequest,
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """申请晋升 / 毛遂自荐。"""
    return success(await svc.apply_rank(current_user, target_rank=body.target_rank))


@router.post("/ranks/appoint", response_model=None)
async def sect_rank_appoint(
    body: SectRankAppointRequest,
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """任命职位。"""
    return success(
        await svc.appoint_rank(
            current_user,
            target_character_id=body.target_character_id,
            target_rank=body.target_rank,
        ),
    )


@router.post("/council/salary", response_model=None)
async def sect_claim_salary(
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """领取议事厅日俸。"""
    return success(await svc.claim_salary(current_user))


@router.post("/council/announce", response_model=None)
async def sect_announce(
    body: SectAnnounceRequest,
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发布宗门公告。"""
    return success(await svc.set_announcement(current_user, text_zh=body.text_zh))


@router.post("/council/war/start", response_model=None)
async def sect_war_start(
    body: SectWarStartRequest,
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发起战事（M11 占位）。"""
    return success(await svc.start_war_stub(current_user, war_kind=body.war_kind))


@router.post("/grade/upgrade", response_model=None)
async def sect_grade_upgrade(
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """升级宗门等级。"""
    return success(await svc.upgrade_grade(current_user))


@router.post("/facilities/{facility_id}/upgrade", response_model=None)
async def sect_facility_upgrade(
    facility_id: str,
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """升级设施。"""
    return success(await svc.upgrade_facility(current_user, facility_id=facility_id))


@router.post("/buffs/toggle", response_model=None)
async def sect_buff_toggle(
    body: SectBuffToggleRequest,
    svc: SectOrgService = Depends(get_sect_org_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开启/关闭宗门增益。"""
    return success(
        await svc.toggle_buff(current_user, buff_id=body.buff_id, enable=body.enable),
    )


@router.get("/quests", response_model=None)
async def sect_quests(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """宗门任务列表。"""
    return success(await svc.list_quests(current_user))


@router.post("/quests/{quest_id}/accept", response_model=None)
async def sect_quest_accept(
    quest_id: str,
    body: SectQuestAcceptRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """接取宗门任务。"""
    return success(
        await svc.accept_quest(
            current_user,
            quest_id=quest_id,
            assignee=body.assignee,
        ),
    )


@router.post("/quests/{quest_id}/complete", response_model=None)
async def sect_quest_complete(
    quest_id: str,
    body: SectQuestCompleteRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """完成宗门任务。"""
    return success(
        await svc.complete_quest(
            current_user,
            quest_id=quest_id,
            assignee=body.assignee,
        ),
    )


@router.get("/shop", response_model=None)
async def sect_shop(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """贡献商店列表。"""
    return success(await svc.list_shop(current_user))


@router.post("/shop/buy", response_model=None)
async def sect_shop_buy(
    body: SectShopBuyRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """贡献商店购买。"""
    return success(await svc.buy_shop(current_user, item_id=body.item_id))


@router.get("/soul-lamps", response_model=None)
async def sect_soul_lamps(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """魂灯列表。"""
    return success(await svc.list_soul_lamps(current_user))


@router.get("/exchange/catalog", response_model=None)
async def sect_exchange_catalog(
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兑宠目录。"""
    return success(await svc.exchange_catalog(current_user))


@router.post("/exchange/pet", response_model=None)
async def sect_exchange_pet(
    body: SectPetExchangeRequest,
    svc: SectService = Depends(get_sect_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """宗门兑宠。"""
    return success(await svc.exchange_pet(current_user, species_id=body.species_id))


# ----- 设施 -----


@router.get("/treasury", response_model=None)
async def treasury_list(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏宝阁。"""
    return success(await svc.treasury_list(current_user))


@router.post("/treasury/exchange", response_model=None)
async def treasury_exchange(
    body: SectTreasuryExchangeRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏宝阁兑换。"""
    return success(await svc.treasury_exchange(current_user, item_key=body.item_key))


@router.post("/treasury/deposit", response_model=None)
async def treasury_deposit(
    body: SectTreasuryDepositRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏宝阁放入。"""
    return success(
        await svc.treasury_deposit(
            current_user,
            page=body.page,
            item_type=body.item_type,
            item_id=body.item_id,
            quantity=body.quantity,
            label_zh=body.label_zh,
        ),
    )


@router.post("/treasury/allocate", response_model=None)
async def treasury_allocate(
    body: SectTreasuryAllocateRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏宝阁分配。"""
    return success(
        await svc.treasury_allocate(
            current_user,
            stock_id=body.stock_id,
            to_character_id=body.to_character_id,
            quantity=body.quantity,
        ),
    )


@router.get("/scripture", response_model=None)
async def scripture_list(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏经阁。"""
    return success(await svc.scripture_list(current_user))


@router.post("/scripture/exchange", response_model=None)
async def scripture_exchange(
    body: SectScriptureExchangeRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏经阁兑换。"""
    return success(
        await svc.scripture_exchange(current_user, technique_id=body.technique_id),
    )


@router.post("/scripture/donate", response_model=None)
async def scripture_donate(
    body: SectScriptureDonateRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """藏经阁上供。"""
    return success(
        await svc.scripture_donate(
            current_user,
            technique_id=body.technique_id,
            label_zh=body.label_zh,
            specialty_tag=body.specialty_tag,
            self_research=body.self_research,
        ),
    )


@router.post("/donations/{review_id}/review", response_model=None)
async def donation_review(
    review_id: int,
    body: SectDonationReviewRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """审核上供。"""
    return success(
        await svc.review_donation(
            current_user,
            review_id=review_id,
            approve=body.approve,
        ),
    )


@router.get("/workshops/{branch}", response_model=None)
async def workshop_catalog(
    branch: str,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """工坊目录。"""
    return success(await svc.workshop_catalog(current_user, branch=branch))


@router.post("/workshops/{branch}/blueprints/exchange", response_model=None)
async def workshop_blueprint_exchange(
    branch: str,
    body: SectWorkshopBlueprintExchangeRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兑换图纸。"""
    return success(
        await svc.workshop_exchange_blueprint(
            current_user,
            branch=branch,
            recipe_id=body.recipe_id,
        ),
    )


@router.post("/workshops/{branch}/blueprints/donate", response_model=None)
async def workshop_blueprint_donate(
    branch: str,
    body: SectWorkshopBlueprintDonateRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """上缴图纸。"""
    return success(
        await svc.workshop_donate_blueprint(
            current_user,
            branch=branch,
            recipe_id=body.recipe_id,
            label_zh=body.label_zh,
            cost_contribution=body.cost_contribution,
            self_research=body.self_research,
        ),
    )


@router.post("/workshops/{branch}/hire", response_model=None)
async def workshop_hire(
    branch: str,
    body: SectWorkshopHireRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """聘工匠代工。"""
    return success(
        await svc.workshop_hire(
            current_user,
            branch=branch,
            craftsman_id=body.craftsman_id,
            recipe_id=body.recipe_id,
        ),
    )


@router.post("/workshops/jobs/{job_id}/claim", response_model=None)
async def workshop_claim(
    job_id: int,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """领取代工。"""
    return success(await svc.workshop_claim(current_user, job_id=job_id))


@router.get("/formation", response_model=None)
async def formation_status(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """宗门大阵。"""
    return success(await svc.formation_status(current_user))


@router.post("/formation/select", response_model=None)
async def formation_select(
    body: SectFormationSelectRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """选择阵法。"""
    return success(
        await svc.formation_select(current_user, formation_id=body.formation_id),
    )


@router.post("/formation/active", response_model=None)
async def formation_active(
    body: SectFormationActiveRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """启停阵法。"""
    return success(await svc.formation_set_active(current_user, active=body.active))


@router.post("/formation/upgrade", response_model=None)
async def formation_upgrade(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兼容：默认给防御加点。"""
    return success(await svc.formation_upgrade(current_user))


@router.post("/formation/allocate", response_model=None)
async def formation_allocate(
    body: SectFormationAllocateRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """阵法加点（攻击/防御/抗性）。"""
    return success(
        await svc.formation_allocate_attr(current_user, attr_key=body.attr_key),
    )


@router.post("/formation/exchange", response_model=None)
async def formation_exchange(
    body: SectFormationExchangeRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """兑换阵法。"""
    return success(
        await svc.formation_exchange(current_user, formation_id=body.formation_id),
    )


@router.post("/formation/donate", response_model=None)
async def formation_donate(
    body: SectFormationDonateRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """上缴阵法功法。"""
    return success(
        await svc.formation_donate(
            current_user,
            formation_id=body.formation_id,
            need_review=body.need_review,
        ),
    )


@router.get("/mine", response_model=None)
async def mine_status(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """矿脉。"""
    return success(await svc.mine_status(current_user))


@router.post("/mine/start", response_model=None)
async def mine_start(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """开始采矿挂机。"""
    return success(await svc.mine_start(current_user))


@router.post("/mine/stop", response_model=None)
async def mine_stop(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """停止采矿挂机。"""
    return success(await svc.mine_stop(current_user))


@router.get("/herbs", response_model=None)
async def herb_status(
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """灵药园。"""
    return success(await svc.herb_status(current_user))


@router.post("/herbs/exchange", response_model=None)
async def herb_exchange(
    body: SectHerbExchangeRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """直接兑换灵植。"""
    return success(await svc.herb_exchange(current_user, plant_id=body.plant_id))


@router.post("/herbs/plant", response_model=None)
async def herb_plant(
    body: SectHerbPlantRequest,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """种植 / 托管种植。"""
    return success(
        await svc.herb_plant(
            current_user,
            plant_id=body.plant_id,
            herbalist_id=body.herbalist_id,
            hosted=bool(body.hosted),
        ),
    )

@router.post("/herbs/{plot_id}/harvest", response_model=None)
async def herb_harvest(
    plot_id: int,
    svc: SectFacilityService = Depends(get_sect_facility_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """收获。"""
    return success(await svc.herb_harvest(current_user, plot_id=plot_id))
