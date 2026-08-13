"""师徒 HTTP DTO（M7 L6）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MentorApplyRequest(BaseModel):
    """拜师 / 收徒申请。"""

    target_character_id: int | None = None
    target_name: str | None = None
    intent: str = Field(description="apprentice=拜师；master=收徒")


class MentorLessonRequest(BaseModel):
    """日课三选一：传道 / 授业 / 解惑。"""

    kind: str = Field(description="dao|craft|technique")
    resource: str | None = Field(
        default=None,
        description="传道时 spirit|body",
    )
    target_id: str | None = Field(
        default=None,
        description="授业/解惑目标功法 id",
    )


class MentorTeachRequest(BaseModel):
    """传授功法或配方图纸。"""

    item_kind: str = Field(description="technique|recipe")
    item_id: str = Field(description="功法或配方 id")


class MentorStudyRequest(BaseModel):
    """徒弟请学师傅功法。"""

    technique_id: str = Field(description="师傅已掌握的功法 id")


class MentorDirectRequest(BaseModel):
    """师傅设置亲传弟子。"""

    apprentice_character_ids: list[int] = Field(
        default_factory=list,
        description="亲传弟子角色 id（最多配置名额，可含已出师）",
    )


class FerryRescueRequest(BaseModel):
    """社交引渡。"""

    mode: str = Field(description="friend|sect|kin（普渡/道友、同门、亲友）")
    target_character_id: int | None = None
    target_name: str | None = None
