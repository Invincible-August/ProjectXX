"""Research HTTP schemas (M8 R2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchCreateRequest(BaseModel):
    """Create a research session."""

    kind: str = Field(description="technique|formation|talisman")
    materials: list[dict[str, Any]] = Field(default_factory=list)
    spends: dict[str, int] = Field(default_factory=dict)
    effect_id: str | None = Field(default=None, description="talisman whitelist effect")


class ResearchFinalizeRequest(BaseModel):
    """Finalize a previewed session."""

    label_zh: str = Field(min_length=2, max_length=16)


class ResearchFormationDraftRequest(BaseModel):
    """Save a formation or talisman designer draft onto the session."""

    blueprint: dict[str, Any] = Field(default_factory=dict)
    effect_id: str | None = Field(default=None, description="talisman effect id")
