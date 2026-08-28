"""
Technique self-research drafts (功法自研 P1).

Create / list / abandon / embed / conditions / affix roll-choose-reroll.
Finalize and equip are later tasks. Creating a draft does not consume cards.
Embed always consumes the formal card.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.research import (
    ERR_RESEARCH_AFFIX_SLOTS,
    ERR_RESEARCH_MATERIALS,
    ERR_RESEARCH_OWNER,
    ERR_RESEARCH_SESSION,
)
from app.constants.technique_craft import (
    CARD_FORMAL_EFFICACY_ID,
    CARD_FORMAL_ELEMENT_ID,
    DRAFT_PHASE_ABANDONED,
    DRAFT_PHASE_EMBEDDING,
    ERR_CRAFT_CARD,
    ERR_CRAFT_EMBED,
    SPELL_EFFICACIES,
    WEAPON_LIMITS,
)
from app.db.models.character import Character
from app.db.models.inventory_item import InventoryItem
from app.db.models.technique_craft import TechniqueResearchDraft
from app.domain.technique_craft import filter_affixes, roll_embed_success, roll_three
from app.schemas.common import AppError
from app.schemas.technique_craft import TechniqueDraftPublic
from app.services.inventory_service import InventoryService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class TechniqueCraftService:
    """Multi-draft technique craft: create, list, abandon, embed, conditions, affixes."""

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

    async def set_conditions(
        self,
        character: Character,
        draft_id: int,
        element_limit: str | None = None,
        weapon_limit: str | None = None,
    ) -> dict[str, Any]:
        """
        Confirm launch conditions. Both boxes may be empty.

        Requires embedded elements and efficacy. Empty limits mean no check.

        Args:
            character: Acting character.
            draft_id: Draft primary key.
            element_limit: Must be empty or one of the draft elements.
            weapon_limit: Must be empty or one of ``WEAPON_LIMITS``.

        Returns:
            dict[str, Any]: Public draft payload.

        Raises:
            AppError: 40221 if embed is incomplete; 40220 if a limit is illegal.
        """
        row = await self._require_draft(character, draft_id)
        elements = self._draft_elements(row)
        if not elements or not row.efficacy:
            raise AppError(ERR_CRAFT_EMBED, "须先镶嵌属性与效能", http_status=400)
        el = str(element_limit or "").strip() or None
        wp = str(weapon_limit or "").strip() or None
        if el is not None and el not in {str(x) for x in elements}:
            raise AppError(ERR_CRAFT_CARD, "属性限制须为本门已嵌属性", http_status=400)
        if wp is not None and wp not in WEAPON_LIMITS:
            raise AppError(ERR_CRAFT_CARD, "装备限制非法", http_status=400)
        row.element_limit = el
        row.weapon_limit = wp
        await self._session.flush()
        logger.info(
            "technique craft conditions character_id=%s draft_id=%s element_limit=%s weapon_limit=%s",
            character.id,
            row.id,
            el,
            wp,
        )
        return self._draft_public(row)

    async def roll_affix(
        self,
        character: Character,
        draft_id: int,
        slot: int,
    ) -> dict[str, Any]:
        """
        Generate three affix options for one slot. Free; conditions need not be set.

        Args:
            character: Acting character.
            draft_id: Draft primary key.
            slot: 0-based affix column.

        Returns:
            dict[str, Any]: Public draft payload with ``options`` of length 3.

        Raises:
            AppError: 40221 missing efficacy / empty pool / already rolled;
                40208 illegal slot.
        """
        row = await self._require_draft(character, draft_id)
        if not row.efficacy:
            raise AppError(ERR_CRAFT_EMBED, "须先镶嵌效能", http_status=400)
        slots = self._load_affix_slots(row)
        cell = self._require_slot(slots, slot)
        if cell.get("options"):
            raise AppError(ERR_CRAFT_EMBED, "该栏已生成词条", http_status=400)
        pool = self._affix_pool_ids(row)
        if not pool:
            raise AppError(ERR_CRAFT_EMBED, "无可用词条", http_status=400)
        cell["options"] = roll_three(pool)
        cell["chosen_id"] = None
        cell["chosen_level"] = 0
        cell["upgrade_count"] = 0
        row.affixes_json = json.dumps(slots, ensure_ascii=False)
        await self._session.flush()
        logger.info(
            "technique craft affix roll character_id=%s draft_id=%s slot=%s",
            character.id,
            row.id,
            slot,
        )
        return self._draft_public(row)

    async def choose_affix(
        self,
        character: Character,
        draft_id: int,
        slot: int,
        affix_id: str,
    ) -> dict[str, Any]:
        """
        Lock one of the three rolled options onto the slot.

        Args:
            character: Acting character.
            draft_id: Draft primary key.
            slot: 0-based affix column.
            affix_id: Must be present in that slot's ``options``.

        Returns:
            dict[str, Any]: Public draft payload.

        Raises:
            AppError: 40221 no options yet; 40208 id not in options / bad slot.
        """
        row = await self._require_draft(character, draft_id)
        slots = self._load_affix_slots(row)
        cell = self._require_slot(slots, slot)
        options = [str(x) for x in (cell.get("options") or [])]
        pick = str(affix_id or "").strip()
        if not options:
            raise AppError(ERR_CRAFT_EMBED, "该栏尚未生成词条", http_status=400)
        if pick not in options:
            raise AppError(ERR_RESEARCH_AFFIX_SLOTS, "词条不在候选中", http_status=400)
        cell["chosen_id"] = pick
        row.affixes_json = json.dumps(slots, ensure_ascii=False)
        await self._session.flush()
        logger.info(
            "technique craft affix choose character_id=%s draft_id=%s slot=%s affix_id=%s",
            character.id,
            row.id,
            slot,
            pick,
        )
        return self._draft_public(row)

    async def reroll_affix(
        self,
        character: Character,
        draft_id: int,
        slot: int,
    ) -> dict[str, Any]:
        """
        Pay reroll cost, clear levels, and draw three new options.

        Cost index is ``min(reroll_count, len(affix_reroll_cost)-1)``. Spell /
        idle_spirit spend ``cultivation_points``; martial / idle_body spend
        ``body_tempering_points``.

        Args:
            character: Acting character (points deducted on this row).
            draft_id: Draft primary key.
            slot: 0-based affix column.

        Returns:
            dict[str, Any]: Public draft payload.

        Raises:
            AppError: 40200 not enough points; 40221 missing efficacy / empty
                pool; 40208 illegal slot.
        """
        row = await self._require_draft(character, draft_id)
        if not row.efficacy:
            raise AppError(ERR_CRAFT_EMBED, "须先镶嵌效能", http_status=400)
        slots = self._load_affix_slots(row)
        cell = self._require_slot(slots, slot)
        pool = self._affix_pool_ids(row)
        if not pool:
            raise AppError(ERR_CRAFT_EMBED, "无可用词条", http_status=400)
        costs = tuple(int(x) for x in get_game_config().research.technique_craft.affix_reroll_cost)
        n = int(cell.get("reroll_count") or 0)
        cost = int(costs[min(n, len(costs) - 1)]) if costs else 0
        self._deduct_reroll_cost(character, str(row.efficacy), cost)
        cell["options"] = roll_three(pool)
        cell["chosen_id"] = None
        cell["chosen_level"] = 0
        cell["upgrade_count"] = 0
        cell["reroll_count"] = n + 1
        row.affixes_json = json.dumps(slots, ensure_ascii=False)
        await self._session.flush()
        logger.info(
            "technique craft affix reroll character_id=%s draft_id=%s slot=%s cost=%s",
            character.id,
            row.id,
            slot,
            cost,
        )
        return self._draft_public(row)

    @staticmethod
    def _empty_affix_slot() -> dict[str, Any]:
        """One affix column before the first roll."""
        return {
            "options": [],
            "chosen_id": None,
            "chosen_level": 0,
            "upgrade_count": 0,
            "reroll_count": 0,
        }

    @staticmethod
    def _affix_slot_count(row: TechniqueResearchDraft) -> int:
        """Column count from ``ranks[major_rank].affix_slots`` (body_tempering default 1)."""
        ranks = get_game_config().research.technique_craft.ranks
        rank = ranks.get(str(row.major_rank)) or ranks.get("body_tempering")
        if rank is None:
            return 1
        return max(1, int(rank.affix_slots or 1))

    def _load_affix_slots(self, row: TechniqueResearchDraft) -> list[dict[str, Any]]:
        """Parse ``affixes_json`` and pad to the rank's column count."""
        raw = json.loads(row.affixes_json or "[]")
        slots: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    cell = dict(self._empty_affix_slot())
                    cell.update(item)
                    slots.append(cell)
        n = self._affix_slot_count(row)
        while len(slots) < n:
            slots.append(self._empty_affix_slot())
        return slots[:n]

    @staticmethod
    def _require_slot(slots: list[dict[str, Any]], slot: int) -> dict[str, Any]:
        """Return the column dict or raise 40208."""
        idx = int(slot)
        if idx < 0 or idx >= len(slots):
            raise AppError(ERR_RESEARCH_AFFIX_SLOTS, "词条栏位非法", http_status=400)
        return slots[idx]

    def _affix_pool_ids(self, row: TechniqueResearchDraft) -> list[str]:
        """Filtered catalog ids for this draft's efficacy / elements / conditions."""
        craft = get_game_config().research.technique_craft
        filtered = filter_affixes(
            craft.affixes,
            efficacy=str(row.efficacy or ""),
            elements=self._draft_elements(row),
            element_limit=row.element_limit or None,
            weapon_limit=row.weapon_limit or None,
        )
        ids: list[str] = []
        for item in filtered:
            aid = str(getattr(item, "affix_id", "") or "")
            if aid:
                ids.append(aid)
        return ids

    @staticmethod
    def _deduct_reroll_cost(character: Character, efficacy: str, cost: int) -> None:
        """Spend cultivation or body points on the character row. No extra ledger."""
        need = int(cost)
        if need <= 0:
            return
        if efficacy in SPELL_EFFICACIES:
            pool = int(character.cultivation_points or 0)
            if pool < need:
                raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)
            character.cultivation_points = pool - need
            return
        pool = int(character.body_tempering_points or 0)
        if pool < need:
            raise AppError(ERR_RESEARCH_MATERIALS, "投入修为或炼体不足", http_status=400)
        character.body_tempering_points = pool - need

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
