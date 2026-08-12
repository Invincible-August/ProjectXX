"""师徒 HTTP DTO（M7 L6）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MentorApplyRequest(BaseModel):
    """拜师 / 收徒申请。"""

    target_character_id: int | None = None
    target_name: str | None = None
    intent: str = Field(description="apprentice=拜师；master=收徒")


class FerryRescueRequest(BaseModel):
    """社交引渡。"""

    mode: str = Field(description="friend|sect")
    target_character_id: int | None = None
    target_name: str | None = None
