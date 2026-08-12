"""宗门 HTTP DTO（M7 L1 + M7-V+）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SectJoinRequest(BaseModel):
    """拜入 NPC 宗门。"""

    template_id: str = Field(description="NPC 宗门模板 id（sects.yaml npc_sects 键）")


class SectCreateRequest(BaseModel):
    """自建宗门。"""

    name: str = Field(min_length=1, max_length=32, description="宗门名（中文）")
    motto: str | None = Field(default=None, max_length=64, description="箴言（可选）")
    specialty: str = Field(description="专精键（specialties）")


class SectQuestAcceptRequest(BaseModel):
    """接取宗门任务。"""

    assignee: str = Field(
        default="body",
        description="接取方：body（本体）或 avatar（化身）",
    )


class SectQuestCompleteRequest(BaseModel):
    """完成宗门任务（占位：接取后即可交）。"""

    assignee: str = Field(default="body", description="接取方：body / avatar")


class SectShopBuyRequest(BaseModel):
    """贡献商店购买。"""

    item_id: str = Field(description="商店条目 id")


class SectPetExchangeRequest(BaseModel):
    """宗门兑宠。"""

    species_id: str = Field(description="白名单物种 id")


class SectRankApplyRequest(BaseModel):
    """职位申请。"""

    target_rank: str = Field(description="目标职位键")


class SectRankAppointRequest(BaseModel):
    """任命职位。"""

    target_character_id: int = Field(description="被任命角色 id")
    target_rank: str = Field(description="目标职位键")


class SectAnnounceRequest(BaseModel):
    """发布公告。"""

    text_zh: str = Field(default="", max_length=256, description="公告正文")


class SectBuffToggleRequest(BaseModel):
    """开启/关闭 buff。"""

    buff_id: str = Field(description="增益键")
    enable: bool = Field(description="True=开启")


class SectWarStartRequest(BaseModel):
    """战事占位。"""

    war_kind: str = Field(
        default="sect_war",
        description="sect_war（宗门战）或 force_war（势力战）",
    )


class SectTreasuryExchangeRequest(BaseModel):
    """藏宝阁贡献兑换。"""

    item_key: str = Field(description="目录键")


class SectTreasuryDepositRequest(BaseModel):
    """藏宝阁放入。"""

    page: int = Field(ge=1, description="页码 1～N")
    item_type: str = Field(description="物品类型键")
    item_id: str = Field(description="物品 id")
    quantity: int = Field(default=1, ge=1)
    label_zh: str | None = Field(default=None, description="中文名")


class SectTreasuryAllocateRequest(BaseModel):
    """藏宝阁分配。"""

    stock_id: int = Field(description="库存行 id")
    to_character_id: int = Field(description="目标弟子")
    quantity: int = Field(default=1, ge=1)


class SectScriptureExchangeRequest(BaseModel):
    """藏经阁兑换。"""

    technique_id: str = Field(description="功法 id")


class SectScriptureDonateRequest(BaseModel):
    """藏经阁上供。"""

    technique_id: str = Field(description="功法 id")
    label_zh: str = Field(description="中文名")
    specialty_tag: str | None = Field(default=None)
    self_research: bool = Field(default=False, description="自研须审核")


class SectDonationReviewRequest(BaseModel):
    """审核上供。"""

    approve: bool = Field(description="是否通过")


class SectWorkshopHireRequest(BaseModel):
    """工坊代工。"""

    craftsman_id: str = Field(description="工匠 id")
    recipe_id: str = Field(description="图纸/配方 id")


class SectWorkshopBlueprintExchangeRequest(BaseModel):
    """兑换工坊图纸。"""

    recipe_id: str = Field(description="图纸/配方 id")


class SectWorkshopBlueprintDonateRequest(BaseModel):
    """上缴工坊图纸。"""

    recipe_id: str = Field(description="图纸/配方 id")
    label_zh: str = Field(description="中文名")
    cost_contribution: int = Field(default=40, ge=1, description="日后兑换贡献价")
    self_research: bool = Field(default=False, description="自创须审核")


class SectFormationSelectRequest(BaseModel):
    """选择阵法。"""

    formation_id: str = Field(description="阵法 id")


class SectFormationActiveRequest(BaseModel):
    """启停阵法。"""

    active: bool = Field(description="是否开启")


class SectFormationDonateRequest(BaseModel):
    """上缴阵法功法。"""

    formation_id: str = Field(description="阵法 id")
    need_review: bool = Field(default=True)


class SectFormationAllocateRequest(BaseModel):
    """阵法加点。"""

    attr_key: str = Field(description="属性键：attack/defense/resistance")


class SectFormationExchangeRequest(BaseModel):
    """兑换阵法。"""

    formation_id: str = Field(description="阵法 id")


class SectHerbPlantRequest(BaseModel):
    """灵药园种植 / 托管种植。"""

    plant_id: str = Field(description="灵植 id")
    herbalist_id: str | None = Field(default=None, description="灵植师 id")
    hosted: bool = Field(default=False, description="是否托管种植（须灵植师）")


class SectHerbExchangeRequest(BaseModel):
    """直接兑换灵植。"""

    plant_id: str = Field(description="灵植 id")
