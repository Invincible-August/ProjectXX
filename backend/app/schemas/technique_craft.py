"""Technique-craft HTTP schemas (功法自研 P1 drafts)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TechniqueDraftPublic(BaseModel):
    """Public draft payload returned by create/list."""

    id: int
    phase: str
    elements: list[str] = Field(default_factory=list)
    efficacy: str | None = None
    can_finalize: bool = False
    label_zh: str = ""
    major_rank: str = "body_tempering"
    element_limit: str | None = None
    weapon_limit: str | None = None
    upgrade_points: int = 0
    base: dict[str, Any] = Field(default_factory=dict)
    affixes: list[Any] = Field(default_factory=list)
