"""
Technique self-research drafts (功法自研 P1).

Create / list / abandon / embed. Conditions and finalize are later tasks.
Creating a draft does not consume cards. Embed always consumes the formal card.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.research import ERR_RESEARCH_OWNER, ERR_RESEARCH_SESSION
from app.constants.technique_craft import (
    CARD_FORMAL_EFFICACY_ID,
    CARD_FORMAL_ELEMENT_ID,
    DRAFT_PHASE_ABANDONED,
    DRAFT_PHASE_EMBEDDING,
    ERR_CRAFT_CARD,
    ERR_CRAFT_EMBED,
)
from app.db.models.character import Character
from app.db.models.inventory_item import InventoryItem
from app.db.models.technique_craft import TechniqueResearchDraft
from app.domain.technique_craft import roll_embed_success
from app.schemas.common import AppError
from app.schemas.technique_craft import TechniqueDraftPublic
from app.services.inventory_service import InventoryService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class TechniqueCraftService:
    """Multi-draft technique craft: create, list, abandon, embed."""

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

    async def embed_card(
        self,
        character: Character,
        draft_id: int,
        item_uid: str,
    ) -> dict[str, Any]:
        """
        Embed one formal element or efficacy card into a draft.

        The card is always deducted after validation, whether the embed
        roll succeeds or fails. Failed rolls leave other draft fields
        unchanged. A filled slot rejects a second card of that kind
        without consuming it.

        Args:
            character: Acting character (must own the draft and the card).
            draft_id: Draft primary key.
            item_uid: Inventory uid of a formal technique card.

        Returns:
            dict[str, Any]: Public draft payload after the attempt.

        Raises:
            AppError: 40207 not owner; 40220 wrong card type / invalid
                meta; 40221 slot already locked; 40000/40055 missing card.
        """
        row = await self._require_draft(character, draft_id)
        card = await self._load_embed_card(character.id, item_uid)
        item_id = str(card.item_id)
        meta = InventoryService._parse_row_meta(card) or {}

        if item_id == CARD_FORMAL_ELEMENT_ID:
            elements = self._formal_elements(meta)
            if self._draft_elements(row):
                raise AppError(ERR_CRAFT_EMBED, "属性槽已锁定", http_status=400)
            payload: dict[str, Any] = {"kind": "elements", "elements": elements}
        elif item_id == CARD_FORMAL_EFFICACY_ID:
            efficacy = self._formal_efficacy(meta)
            if row.efficacy:
                raise AppError(ERR_CRAFT_EMBED, "效能槽已锁定", http_status=400)
            payload = {"kind": "efficacy", "efficacy": efficacy}
        else:
            raise AppError(ERR_CRAFT_CARD, "该物品不是可镶嵌的正式卡", http_status=400)

        inv = InventoryService(self._session)
        await inv.remove_one_by_uid(character.id, item_uid)

        fail_rate = float(get_game_config().research.technique_craft.embed_fail_rate)
        ok = bool(roll_embed_success(fail_rate))
        if ok:
            if payload["kind"] == "elements":
                row.elements_json = json.dumps(payload["elements"], ensure_ascii=False)
            else:
                row.efficacy = str(payload["efficacy"])
            await self._session.flush()

        logger.info(
            "technique craft embed character_id=%s draft_id=%s item_id=%s success=%s",
            character.id,
            row.id,
            item_id,
            ok,
        )
        return self._draft_public(row)

    async def _load_embed_card(
        self,
        character_id: int,
        item_uid: str,
    ) -> InventoryItem:
        """Load the bag row that will be embedded; does not deduct yet."""
        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_uid == item_uid,
            )
            .limit(1)
        )
        card = result.scalar_one_or_none()
        if card is None or int(card.quantity) < 1:
            raise AppError(40000, "背包物品不存在", http_status=404)
        return card

    @staticmethod
    def _formal_elements(meta: dict[str, Any]) -> list[str]:
        """Read non-empty ``elements`` from a formal element card."""
        raw = meta.get("elements")
        if not isinstance(raw, list):
            raise AppError(ERR_CRAFT_CARD, "该物品不是可镶嵌的正式卡", http_status=400)
        elements = [str(x) for x in raw if str(x)]
        if not elements:
            raise AppError(ERR_CRAFT_CARD, "该物品不是可镶嵌的正式卡", http_status=400)
        return elements

    @staticmethod
    def _formal_efficacy(meta: dict[str, Any]) -> str:
        """Read non-empty ``efficacy`` from a formal efficacy card."""
        raw = meta.get("efficacy")
        if not isinstance(raw, str) or not raw.strip():
            raise AppError(ERR_CRAFT_CARD, "该物品不是可镶嵌的正式卡", http_status=400)
        return raw.strip()

    @staticmethod
    def _draft_elements(row: TechniqueResearchDraft) -> list[str]:
        """Parse ``elements_json``; non-list values become empty."""
        raw = json.loads(row.elements_json or "[]")
        return list(raw) if isinstance(raw, list) else []

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
        elements = TechniqueCraftService._draft_elements(row)
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
