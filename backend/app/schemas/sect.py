"""宗门 HTTP DTO（M7 L1）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SectJoinRequest(BaseModel):
    """拜入 NPC 宗门。"""

    template_id: str = Field(description="NPC 宗门模板 id（sects.yaml npc_sects 键）")


class SectCreateRequest(BaseModel):
    """自建宗门。"""

    name: str = Field(min_length=1, max_length=32, description="宗门名（中文）")
    motto: str | None = Field(default=None, max_length=64, description="箴言（可选）")


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
