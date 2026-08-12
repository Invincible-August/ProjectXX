"""
功法列表与创角默认解锁（M2）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.db.models.technique import CharacterTechnique
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

_STARTER_TECHNIQUE_IDS = ("basic_qi_art", "iron_body_art", "beginner_alchemy")


class TechniqueService:
    """
    Application service for character technique unlocks and listings (M2).

    Ensures default techniques on character creation and exposes level/cost
    metadata for allocation and combat bonus calculation.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize technique service with a database session.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session

    async def ensure_default_techniques(
        self,
        character_id: int,
    ) -> None:
        """
        Grant all configured starter techniques at level 0 if missing.

        Args:
            character_id: Character primary key.
        """
        cfg = get_game_config()
        for tech_id in cfg.techniques:
            existing = await self._session.execute(
                select(CharacterTechnique.id)
                .where(
                    CharacterTechnique.character_id == character_id,
                    CharacterTechnique.technique_id == tech_id,
                )
                .limit(1),
            )
            if existing.scalar_one_or_none() is not None:
                continue
            self._session.add(
                CharacterTechnique(
                    character_id=character_id,
                    technique_id=tech_id,
                    level=0,
                ),
            )
        await self._session.flush()
        logger.info("default techniques granted character_id=%s", character_id)

    async def list_my_techniques(
        self,
        character: Character,
    ) -> list[dict]:
        """
        Return the character's technique levels with next-level cost hints.

        Args:
            character: Character entity.

        Returns:
            list[dict]: Entries with id, name, level, max_level, track, next_cost.
        """
        await self.ensure_default_techniques(character.id)
        result = await self._session.execute(
            select(CharacterTechnique).where(CharacterTechnique.character_id == character.id),
        )
        rows = result.scalars().all()
        cfg = get_game_config()
        items: list[dict] = []
        for row in rows:
            tech = cfg.techniques.get(row.technique_id)
            if tech is None:
                continue
            next_cost = None
            if row.level < tech.max_level:
                idx = row.level  # cost_per_level[0] = 升到 1 级
                costs = tech.cost_per_level
                if 0 <= idx < len(costs):
                    next_cost = int(costs[idx])
            items.append(
                {
                    "id": row.technique_id,
                    "name": tech.name,
                    "level": row.level,
                    "max_level": tech.max_level,
                    "track": tech.track,
                    "next_cost": next_cost,
                },
            )
        return items

    @staticmethod
    def technique_summary_for_character(
        session_techniques: list[dict],
    ) -> list[dict]:
        """
        Build a compact technique summary for CharacterPublic.

        Args:
            session_techniques: Output of ``list_my_techniques``.

        Returns:
            list[dict]: id, name, level, max_level only.
        """
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "level": item["level"],
                "max_level": item["max_level"],
            }
            for item in session_techniques
        ]

    @staticmethod
    def compute_technique_combat_bonuses(
        techniques: list[dict],
    ) -> tuple[int, int]:
        """
        Compute atk/hp bonuses from technique levels and placeholder effects.

        Args:
            techniques: Technique list with id and level fields.

        Returns:
            tuple[int, int]: (atk_bonus, hp_bonus).
        """
        cfg = get_game_config()
        atk_bonus = 0
        hp_bonus = 0
        for item in techniques:
            tech = cfg.techniques.get(item["id"])
            if tech is None:
                continue
            level = int(item["level"])
            effects = tech.effects_placeholder
            atk_bonus += int(effects.get("atk_bonus_per_level", 0)) * level
            hp_bonus += int(effects.get("hp_bonus_per_level", 0)) * level
        return atk_bonus, hp_bonus


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


async def ensure_default_techniques(
    session: AsyncSession,
    character_id: int,
) -> None:
    """Module wrapper delegating to ``TechniqueService.ensure_default_techniques``."""
    await TechniqueService(session).ensure_default_techniques(character_id)


async def list_my_techniques(
    session: AsyncSession,
    character: Character,
) -> list[dict]:
    """Module wrapper delegating to ``TechniqueService.list_my_techniques``."""
    return await TechniqueService(session).list_my_techniques(character)


def technique_summary_for_character(
    session_techniques: list[dict],
) -> list[dict]:
    """Module wrapper delegating to ``TechniqueService.technique_summary_for_character``."""
    return TechniqueService.technique_summary_for_character(session_techniques)


def compute_technique_combat_bonuses(
    techniques: list[dict],
) -> tuple[int, int]:
    """Module wrapper delegating to ``TechniqueService.compute_technique_combat_bonuses``."""
    return TechniqueService.compute_technique_combat_bonuses(techniques)
