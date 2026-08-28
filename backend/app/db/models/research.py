"""
Research session and private technique ORM (M8 R2).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchSession(Base):
    """Player research session (technique / formation / talisman)."""

    __tablename__ = "research_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="drafting")
    materials_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    spends_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dice_roll: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    affix_preview_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    reroll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    private_content_id: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
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


class PrivateFormation(Base):
    """Finalized custom formation blueprint (immutable revision)."""

    __tablename__ = "private_formations"
    __table_args__ = (
        UniqueConstraint("formation_id", name="uq_private_formation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    formation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    label_zh: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    blueprint_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PrivateTalisman(Base):
    """Finalized custom talisman template (effect whitelist freeze)."""

    __tablename__ = "private_talismans"
    __table_args__ = (
        UniqueConstraint("template_id", name="uq_private_talisman_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[str] = mapped_column(String(128), nullable=False)
    label_zh: Mapped[str] = mapped_column(String(32), nullable=False)
    effect_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CharacterTalismanLoadout(Base):
    """Preloaded talisman inventory pointers for the next battle."""

    __tablename__ = "character_talisman_loadouts"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    slots_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PrivateTechnique(Base):
    """Finalized custom technique fragment (frozen)."""

    __tablename__ = "private_techniques"
    __table_args__ = (
        UniqueConstraint("technique_id", name="uq_private_technique_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    technique_id: Mapped[str] = mapped_column(String(128), nullable=False)
    label_zh: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    affix_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    major_rank: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    author_character_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    track: Mapped[str] = mapped_column(String(32), nullable=False, default="spirit")
    max_level: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
