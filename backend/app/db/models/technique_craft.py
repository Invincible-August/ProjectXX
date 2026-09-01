"""
Technique self-research draft ORM (功法自研 P1).

One character may hold many parallel drafts. Abandoned rows stay in the
table (phase=abandoned) so consumed embed cards are never refunded.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TechniqueResearchDraft(Base):
    """In-progress custom technique draft (multi-draft, not a research session)."""

    __tablename__ = "technique_research_drafts"
    __table_args__ = (
        Index("ix_technique_research_drafts_char_phase", "character_id", "phase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="embedding")
    label_zh: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    efficacy: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    element_limit: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    weapon_limit: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    base_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    affixes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # tier5 / perfection：各 { options[], chosen_id }；定稿前须两档均选定
    milestones_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    upgrade_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    major_rank: Mapped[str] = mapped_column(String(32), nullable=False, default="body_tempering")
    conditions_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
