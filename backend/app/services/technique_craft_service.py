"""
Technique self-research drafts (功法自研 P1).

Create / list / abandon only. Embed, conditions, and finalize are later tasks.
Creating a draft does not consume cards.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.research import ERR_RESEARCH_OWNER, ERR_RESEARCH_SESSION
from app.constants.technique_craft import DRAFT_PHASE_ABANDONED, DRAFT_PHASE_EMBEDDING
from app.db.models.character import Character
from app.db.models.technique_craft import TechniqueResearchDraft
from app.schemas.common import AppError
from app.schemas.technique_craft import TechniqueDraftPublic

logger = logging.getLogger(__name__)


class TechniqueCraftService:
    """Multi-draft technique craft: create, list, abandon."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(self, character: Character) -> dict[str, Any]:
        """
        Open a new empty draft. Does not deduct inventory cards.

        Args:
            character: Acting character.

        Returns:
            dict[str, Any]: Public draft payload (``can_finalize`` is false).
        """
        row = TechniqueResearchDraft(
            character_id=character.id,
            phase=DRAFT_PHASE_EMBEDDING,
            label_zh="",
            elements_json="[]",
            efficacy=None,
            element_limit=None,
            weapon_limit=None,
            base_json="{}",
            affixes_json="[]",
            upgrade_points=0,
            major_rank=str(character.major_realm or "body_tempering"),
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "technique craft draft created character_id=%s draft_id=%s",
            character.id,
            row.id,
        )
        return self._draft_public(row)

    async def list_drafts(self, character: Character) -> list[dict[str, Any]]:
        """
        Active drafts for the character. Abandoned rows are omitted.

        Args:
            character: Acting character.

        Returns:
            list[dict[str, Any]]: Public payloads, oldest first.
        """
        result = await self._session.execute(
            select(TechniqueResearchDraft)
            .where(
                TechniqueResearchDraft.character_id == character.id,
                TechniqueResearchDraft.phase != DRAFT_PHASE_ABANDONED,
            )
            .order_by(TechniqueResearchDraft.id.asc())
        )
        return [self._draft_public(row) for row in result.scalars().all()]

    async def abandon_draft(self, character: Character, draft_id: int) -> None:
        """
        Mark a draft abandoned. Embedded cards are not refunded.

        Args:
            character: Acting character.
            draft_id: Draft primary key.

        Raises:
            AppError: 40201 if missing/abandoned; 40207 if not owned.
        """
        row = await self._require_draft(character, draft_id)
        row.phase = DRAFT_PHASE_ABANDONED
        await self._session.flush()
        logger.info(
            "technique craft draft abandoned character_id=%s draft_id=%s",
            character.id,
            row.id,
        )

    async def _require_draft(
        self,
        character: Character,
        draft_id: int,
    ) -> TechniqueResearchDraft:
        result = await self._session.execute(
            select(TechniqueResearchDraft)
            .where(TechniqueResearchDraft.id == draft_id)
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(ERR_RESEARCH_SESSION, "自研草稿不存在", http_status=404)
        if int(row.character_id) != int(character.id):
            raise AppError(ERR_RESEARCH_OWNER, "私有内容不属于当前角色", http_status=403)
        if row.phase == DRAFT_PHASE_ABANDONED:
            raise AppError(ERR_RESEARCH_SESSION, "自研草稿不存在", http_status=404)
        return row

    @staticmethod
    def _draft_public(row: TechniqueResearchDraft) -> dict[str, Any]:
        elements_raw = json.loads(row.elements_json or "[]")
        elements = list(elements_raw) if isinstance(elements_raw, list) else []
        base_raw = json.loads(row.base_json or "{}")
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        affix_raw = json.loads(row.affixes_json or "[]")
        affixes = list(affix_raw) if isinstance(affix_raw, list) else []
        return TechniqueDraftPublic(
            id=row.id,
            phase=row.phase,
            elements=elements,
            efficacy=row.efficacy or None,
            can_finalize=False,
            label_zh=row.label_zh or "",
            major_rank=row.major_rank,
            element_limit=row.element_limit or None,
            weapon_limit=row.weapon_limit or None,
            upgrade_points=int(row.upgrade_points or 0),
            base=base,
            affixes=affixes,
        ).model_dump()
