"""M4/N4/PET-D01/D02 灵宠 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PetCaptureTestRequest(BaseModel):
    """POST /pets/capture_test 请求体。"""

    # None / 空 = 按稀有度权重从 capture_test 池抽取
    species_id: str | None = Field(default=None)


class PetPatchRequest(BaseModel):
    """PATCH /pets/{id} 请求体。"""

    nickname: str | None = None
    is_deploy_preferred: bool | None = None


class PetAffixRerollValueRequest(BaseModel):
    """POST /pets/{id}/affix/reroll-value 请求体。"""

    slot_index: int = Field(..., ge=0, le=8, description="词条槽下标 0..cap-1")


class PetSectRerollTypeRequest(BaseModel):
    """POST /pets/sect/affix/reroll-type 请求体（PET-D06）。"""

    pet_id: int = Field(..., ge=1)
    slot_index: int = Field(..., ge=0, le=8, description="词条槽下标；须 < type_reroll_slots")
    # 可选幂等键占位（本期不做服务端去重存储）
    idempotency_key: str | None = Field(default=None, max_length=64)


class PetFeedRequest(BaseModel):
    """POST /pets/{id}/feed 请求体（PET-D04）。"""

    item_id: str = Field(..., min_length=1, description="兽丹道具 id")
    quantity: int = Field(default=1, ge=1, le=99)


class PetExploreEncounterRequest(BaseModel):
    """POST /pets/explore/encounter 请求体（M4-D04c）。"""

    region_id: str = Field(default="default", min_length=1, max_length=64)
    seed: int | None = Field(default=None, ge=0)


class PetExploreCaptureRequest(BaseModel):
    """POST /pets/explore/capture 请求体（M4-D04c）。"""

    encounter_id: str = Field(..., min_length=1, max_length=64)
    seed: int | None = Field(default=None, ge=0)


class PetExploreAutoRequest(BaseModel):
    """POST /pets/explore/auto 请求体（M4-D04c 自动捕）。"""

    region_id: str = Field(default="default", min_length=1, max_length=64)
    seed: int | None = Field(default=None, ge=0)


class PetSkillsEquipRequest(BaseModel):
    """POST /pets/{id}/skills/equip 请求体。"""

    equipped: list[str | None] = Field(default_factory=list)


class PetSkillLearnPoolRequest(BaseModel):
    """POST /pets/{id}/skills/learn 请求体（物种池）。"""

    skill_id: str = Field(..., min_length=1)


class PetSkillLearnBookRequest(BaseModel):
    """POST /pets/{id}/skills/learn_book 请求体。"""

    book_id: str = Field(..., min_length=1)


class PetDuelNpcStartRequest(BaseModel):
    """POST /pets/duel/npc/start 请求体。"""

    pet_id: int = Field(..., ge=1)
    npc_id: str | None = Field(default=None, description="缺省取第一个 NPC 模板")
    seed: int | None = Field(default=None, description="可选；用于复现")


class PetDuelTurnRequest(BaseModel):
    """POST /pets/duel/{duel_id}/turn 请求体。"""

    skill_id: str | None = Field(default=None, description="空则挣扎")


class PetDuelAutoRequest(BaseModel):
    """POST /pets/duel/npc/auto 请求体。"""

    pet_id: int = Field(..., ge=1)
    npc_id: str | None = None
    seed: int | None = None


class PetHatchStartRequest(BaseModel):
    """POST /pets/hatch/start 请求体（N5）。"""

    egg_item_id: str = Field(..., min_length=1, description="蛋道具 id，对齐 pet_eggs")
