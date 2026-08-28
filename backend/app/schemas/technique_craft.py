"""Technique-craft HTTP schemas (功法自研 P1 drafts)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TechniqueEmbedRequest(BaseModel):
    """POST /cave/lab/technique/drafts/{id}/embed body."""

    item_uid: str = Field(..., min_length=1, max_length=64)


class TechniqueConditionsRequest(BaseModel):
    """POST /cave/lab/technique/drafts/{id}/conditions body."""

    element_limit: str | None = None
    weapon_limit: str | None = None


class TechniqueAffixSlotRequest(BaseModel):
    """POST .../affix/roll and .../affix/reroll body."""

    slot: int = Field(..., ge=0)


class TechniqueAffixChooseRequest(BaseModel):
    """POST /cave/lab/technique/drafts/{id}/affix/choose body."""

    slot: int = Field(..., ge=0)
    affix_id: str = Field(..., min_length=1, max_length=64)


class TechniqueFinalizeRequest(BaseModel):
    """POST /cave/lab/technique/drafts/{id}/finalize body."""

    label_zh: str = Field(..., min_length=2, max_length=16)


class TechniqueBaseUpgradeRequest(BaseModel):
    """POST /cave/lab/technique/techniques/{id}/base-upgrade body."""

    stat: str = Field(..., min_length=1, max_length=16)


class TechniqueAffixUpgradeRequest(BaseModel):
    """POST /cave/lab/technique/techniques/{id}/affix-upgrade body."""

    slot: int = Field(..., ge=0)


class TechniqueDraftPublic(BaseModel):
    """Public draft payload returned by create/list/embed."""

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
