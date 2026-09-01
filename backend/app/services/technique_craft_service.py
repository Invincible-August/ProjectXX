"""
Technique self-research drafts (功法自研 P1).

Create / list / abandon / embed / conditions / affix roll-choose-reroll / finalize /
cultivate (base upgrade, affix upgrade, breakthrough) / print manual / abolish.
Creating a draft does not consume cards. Embed consumes formal cards unless they are
infinite test cards. Finalize writes PrivateTechnique + CharacterTechnique at the
lowest rank (body_tempering) and leaves the draft list.
Cultivate mutates PrivateTechnique.payload_json, not the draft row.
Print copies the current payload into an unstacked inventory manual.
Learn copies a frozen snapshot onto the reader (source=chance) then consumes the book.
Abolish deletes only the author's CharacterTechnique + PrivateTechnique after unequip;
manual / scripture / disciple copies remain.
"""

from __future__ import annotations

import copy
import json
import logging
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.research import (
    ERR_RESEARCH_AFFIX_SLOTS,
    ERR_RESEARCH_FROZEN,
    ERR_RESEARCH_MATERIALS,
    ERR_RESEARCH_OWNER,
    ERR_RESEARCH_SESSION,
    PRIVATE_ID_PREFIX,
    RESEARCH_SOURCE_CUSTOM,
)
from app.constants.technique import (
    TECHNIQUE_SOURCE_CHANCE,
    TECHNIQUE_SOURCE_RESEARCH,
    normalize_technique_source,
)
from app.constants.technique_craft import (
    CARD_FORMAL_EFFICACY_ID,
    CARD_FORMAL_ELEMENT_ID,
    CARD_MANUAL_ID,
    CRAFT_INITIAL_RANK,
    CREATE_AFFIX_SLOTS_KEY,
    DRAFT_PHASE_ABANDONED,
    DRAFT_PHASE_EMBEDDING,
    DRAFT_PHASE_FINALIZED,
    ERR_CRAFT_ABOLISH,
    ERR_CRAFT_CARD,
    ERR_CRAFT_CULTIVATE,
    ERR_CRAFT_EMBED,
    ERR_CRAFT_FINALIZE,
    ERR_CRAFT_LEARN,
    ERR_CRAFT_MANUAL,
    FORMAL_EFFICACY_CARD_IDS,
    FORMAL_ELEMENT_CARD_IDS,
    INFINITE_FORMAL_CARD_IDS,
    SPELL_EFFICACIES,
    WEAPON_LIMITS,
)
from app.db.models.character import Character
from app.db.models.inventory_item import InventoryItem
from app.db.models.research import PrivateTechnique
from app.db.models.sect import Sect
from app.db.models.technique import CharacterTechnique
from app.db.models.technique_craft import TechniqueResearchDraft
from app.domain.research_schema import is_valid_zh_label
from app.domain.technique_craft import (
    affix_upgrade_cost_multiplier,
    can_breakthrough,
    enrich_affix_slots_public,
    filter_affixes,
    learner_meets_manual_rank,
    major_rank_label_zh,
    next_rank_id,
    payload_attr_grants,
    resolve_affix_rarity,
    roll_affix_upgrade_success,
    roll_breakthrough_success,
    roll_embed_success,
    roll_three_weighted,
    upgrade_points_for_affix_level,
    upgrade_points_for_base_level,
)
from app.schemas.common import AppError
from app.schemas.technique_craft import TechniqueDraftPublic
from app.services.inventory_service import InventoryService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class TechniqueCraftService:
    """Multi-draft technique craft: create, list, abandon, embed, conditions, affixes, finalize, cultivate, print, learn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(self, character: Character) -> dict[str, Any]:
        """
        Open a new empty draft. Does not deduct inventory cards.

        Affix column count is frozen from the character's major realm
        (``ranks[realm].affix_slots``), not the technique's starting rank.

        Args:
            character: Acting character.

        Returns:
            dict[str, Any]: Public draft payload (``can_finalize`` is false).
        """
        create_slots = self._rank_affix_slots(str(character.major_realm or CRAFT_INITIAL_RANK))
        slots = [self._empty_affix_slot() for _ in range(create_slots)]
        row = TechniqueResearchDraft(
            character_id=character.id,
            phase=DRAFT_PHASE_EMBEDDING,
            label_zh="",
            elements_json="[]",
            efficacy=None,
            element_limit=None,
            weapon_limit=None,
            base_json=json.dumps({CREATE_AFFIX_SLOTS_KEY: create_slots}, ensure_ascii=False),
            affixes_json=json.dumps(slots, ensure_ascii=False),
            upgrade_points=0,
            major_rank=CRAFT_INITIAL_RANK,
            conditions_confirmed=False,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "technique craft draft created character_id=%s draft_id=%s create_affix_slots=%s",
            character.id,
            row.id,
            create_slots,
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
                TechniqueResearchDraft.phase.notin_(
                    (DRAFT_PHASE_ABANDONED, DRAFT_PHASE_FINALIZED),
                ),
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

        if item_id in FORMAL_ELEMENT_CARD_IDS:
            elements = self._formal_elements(meta)
            if self._draft_elements(row):
                raise AppError(ERR_CRAFT_EMBED, "属性槽已锁定", http_status=400)
            payload: dict[str, Any] = {"kind": "elements", "elements": elements}
        elif item_id in FORMAL_EFFICACY_CARD_IDS:
            efficacy = self._formal_efficacy(meta)
            if row.efficacy:
                raise AppError(ERR_CRAFT_EMBED, "效能槽已锁定", http_status=400)
            payload = {"kind": "efficacy", "efficacy": efficacy}
        else:
            raise AppError(ERR_CRAFT_CARD, "该物品不是可镶嵌的正式卡", http_status=400)

        inv = InventoryService(self._session)
        infinite = item_id in INFINITE_FORMAL_CARD_IDS or bool(meta.get("infinite_use"))
        if not infinite:
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
            "technique craft embed character_id=%s draft_id=%s item_id=%s success=%s infinite=%s",
            character.id,
            row.id,
            item_id,
            ok,
            infinite,
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
        row.conditions_confirmed = True
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
        cell["options"] = self._weighted_affix_roll(pool)
        cell["chosen_id"] = None
        cell["chosen_rarity"] = None
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
        cell["chosen_rarity"] = resolve_affix_rarity(pick)
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
        cell["options"] = self._weighted_affix_roll(pool)
        cell["chosen_id"] = None
        cell["chosen_rarity"] = None
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
            "chosen_rarity": None,
            "chosen_level": 0,
            "upgrade_count": 0,
            "reroll_count": 0,
            "rank_boost": 0,
        }

    @staticmethod
    def _rank_affix_slots(major_rank: str) -> int:
        """Column count from ``ranks[major_rank].affix_slots`` (body_tempering default 1)."""
        ranks = get_game_config().research.technique_craft.ranks
        rank = ranks.get(str(major_rank)) or ranks.get("body_tempering")
        if rank is None:
            return 1
        return max(1, int(rank.affix_slots or 1))

    @staticmethod
    def _create_affix_slots_from_draft(row: TechniqueResearchDraft) -> int:
        """Frozen create-time column count stored in draft ``base_json``."""
        try:
            base = json.loads(row.base_json or "{}")
        except json.JSONDecodeError:
            base = {}
        if isinstance(base, dict) and base.get(CREATE_AFFIX_SLOTS_KEY) is not None:
            return max(1, int(base[CREATE_AFFIX_SLOTS_KEY]))
        return TechniqueCraftService._rank_affix_slots(str(row.major_rank or CRAFT_INITIAL_RANK))

    @staticmethod
    def _create_affix_slots_from_payload(payload: dict[str, Any]) -> int:
        """Frozen create-time column count on a cultivated technique payload."""
        raw = payload.get("create_affix_slots")
        if raw is not None:
            return max(1, int(raw))
        return 0

    @classmethod
    def _affix_slot_count(cls, row: TechniqueResearchDraft) -> int:
        """
        Draft column count = max(create-time realm slots, current technique-rank slots).

        Create freezes character-realm slots; breakthrough may raise the floor via
        the technique's own rank ``affix_slots``.
        """
        create_n = cls._create_affix_slots_from_draft(row)
        rank_n = cls._rank_affix_slots(str(row.major_rank or CRAFT_INITIAL_RANK))
        return max(create_n, rank_n)

    @classmethod
    def _load_affix_slots(cls, row: TechniqueResearchDraft) -> list[dict[str, Any]]:
        """Parse ``affixes_json`` and pad to the target column count (never shrink)."""
        try:
            raw = json.loads(row.affixes_json or "[]")
        except json.JSONDecodeError:
            raw = []
        slots: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    cell = dict(cls._empty_affix_slot())
                    cell.update(item)
                    slots.append(cell)
        n = max(cls._affix_slot_count(row), len(slots))
        while len(slots) < n:
            slots.append(cls._empty_affix_slot())
        return slots

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

    def _payload_affix_pool_ids(self, payload: dict[str, Any]) -> list[str]:
        """Filtered catalog ids for a cultivated technique payload."""
        craft = get_game_config().research.technique_craft
        elements_raw = payload.get("elements") or []
        elements = [str(x) for x in elements_raw] if isinstance(elements_raw, list) else []
        filtered = filter_affixes(
            craft.affixes,
            efficacy=str(payload.get("efficacy") or ""),
            elements=elements,
            element_limit=(
                str(payload.get("element_limit") or "").strip() or None
            ),
            weapon_limit=(
                str(payload.get("weapon_limit") or "").strip() or None
            ),
        )
        ids: list[str] = []
        for item in filtered:
            aid = str(getattr(item, "affix_id", "") or "")
            if aid:
                ids.append(aid)
        return ids

    def _weighted_affix_roll(self, pool: list[str]) -> list[str]:
        """Draw three weighted options from a pool."""
        craft = get_game_config().research.technique_craft
        weights = {
            aid: float(
                getattr(
                    craft.affix_rarities.get(resolve_affix_rarity(aid)),
                    "weight",
                    1.0,
                )
                or 1.0
            )
            for aid in pool
        }
        return roll_three_weighted(pool, weights)

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

    async def finalize_draft(
        self,
        character: Character,
        draft_id: int,
        label_zh: str,
    ) -> dict[str, Any]:
        """
        Freeze a ready draft into a private technique on the learned list.

        Gates: non-empty elements and efficacy, ``conditions_confirmed``, at
        least one chosen affix that still matches the current pool. Then
        ``phase=finalized``, insert ``PrivateTechnique`` + ``CharacterTechnique``.

        Args:
            character: Acting character (becomes ``author_character_id``).
            draft_id: Draft primary key.
            label_zh: Player-chosen Chinese name (2–16 chars).

        Returns:
            dict[str, Any]: Public draft plus ``private`` / ``technique_id``.

        Raises:
            AppError: 40222 if a gate fails; 40206 if already finalized.
        """
        row = await self._require_draft(character, draft_id)
        elements = self._draft_elements(row)
        if not elements or not str(row.efficacy or "").strip():
            raise AppError(ERR_CRAFT_FINALIZE, "须先镶嵌属性与效能", http_status=400)
        if not bool(getattr(row, "conditions_confirmed", False)):
            raise AppError(ERR_CRAFT_FINALIZE, "须先确认发动条件", http_status=400)
        slots = self._load_affix_slots(row)
        chosen_ids = [
            str(cell.get("chosen_id") or "").strip()
            for cell in slots
            if str(cell.get("chosen_id") or "").strip()
        ]
        if not chosen_ids:
            raise AppError(ERR_CRAFT_FINALIZE, "须至少确认一个词条", http_status=400)
        pool = set(self._affix_pool_ids(row))
        if any(cid not in pool for cid in chosen_ids):
            raise AppError(ERR_CRAFT_FINALIZE, "词条与当前效能或发动条件不符", http_status=400)
        if not is_valid_zh_label(label_zh):
            raise AppError(ERR_CRAFT_FINALIZE, "请使用二至十六字中文名称", http_status=400)
        name = label_zh.strip()
        await self._assert_unique_technique_label(name)

        for cell in slots:
            cid = str(cell.get("chosen_id") or "").strip()
            if cid and not str(cell.get("chosen_rarity") or "").strip():
                cell["chosen_rarity"] = resolve_affix_rarity(cid)

        cfg = get_game_config()
        base_raw = json.loads(row.base_json or "{}")
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        create_slots = self._create_affix_slots_from_draft(row)
        base.pop(CREATE_AFFIX_SLOTS_KEY, None)
        payload = {
            "elements": elements,
            "efficacy": str(row.efficacy),
            "element_limit": row.element_limit,
            "weapon_limit": row.weapon_limit,
            "base": base,
            "affixes": slots,
            "upgrade_points": int(row.upgrade_points or 0),
            "create_affix_slots": create_slots,
        }
        stats = payload_attr_grants(payload)
        slug = secrets.token_hex(4)
        technique_id = f"{PRIVATE_ID_PREFIX}:technique:{character.id}:{slug}"
        efficacy = str(row.efficacy)
        # 定稿一律从最低阶起，须逐步突破；草稿里若曾写入人物境界也强制覆盖
        row.major_rank = CRAFT_INITIAL_RANK
        private = PrivateTechnique(
            character_id=character.id,
            technique_id=technique_id,
            label_zh=name,
            revision=1,
            schema_version=cfg.research.schema_version,
            affix_ids_json=json.dumps(chosen_ids, ensure_ascii=False),
            stats_json=json.dumps(stats, ensure_ascii=False),
            payload_json=json.dumps(payload, ensure_ascii=False),
            major_rank=CRAFT_INITIAL_RANK,
            author_character_id=int(character.id),
            track="spirit" if efficacy in SPELL_EFFICACIES else "body",
            max_level=int(cfg.research.technique.max_level),
            source=RESEARCH_SOURCE_CUSTOM,
        )
        self._session.add(private)
        existing = await self._session.execute(
            select(CharacterTechnique.id)
            .where(
                CharacterTechnique.character_id == character.id,
                CharacterTechnique.technique_id == technique_id,
            )
            .limit(1)
        )
        if existing.scalar_one_or_none() is None:
            self._session.add(
                CharacterTechnique(
                    character_id=character.id,
                    technique_id=technique_id,
                    level=1,
                    source=TECHNIQUE_SOURCE_RESEARCH,
                )
            )
        row.phase = DRAFT_PHASE_FINALIZED
        row.label_zh = name
        await self._session.flush()
        logger.info(
            "technique craft finalized character_id=%s draft_id=%s technique_id=%s",
            character.id,
            row.id,
            technique_id,
        )
        from app.services.research_service import ResearchService

        out = self._draft_public(row)
        out["private"] = ResearchService._private_public(private)
        out["technique_id"] = technique_id
        return out

    async def _assert_unique_technique_label(self, label_zh: str) -> None:
        """
        Reject if the Chinese name is already used by a private or official technique.

        Args:
            label_zh: Trimmed player-chosen name.

        Raises:
            AppError: 40222 when the name is taken.
        """
        taken = await self._session.execute(
            select(PrivateTechnique.id)
            .where(PrivateTechnique.label_zh == label_zh)
            .limit(1)
        )
        if taken.scalar_one_or_none() is not None:
            raise AppError(ERR_CRAFT_FINALIZE, "功法名称已被占用，请重新输入", http_status=400)
        for tech in get_game_config().techniques.values():
            official = str(getattr(tech, "name", "") or "").strip()
            if official and official == label_zh:
                raise AppError(ERR_CRAFT_FINALIZE, "功法名称已被占用，请重新输入", http_status=400)

    async def upgrade_base(
        self,
        character: Character,
        technique_id: str,
        stat: str,
    ) -> dict[str, Any]:
        """
        Spend one base-upgrade click on attack, defense, or speed.

        Cost index is ``min(total_upgrades, len(cost)-1)`` for the whole
        technique, independent of which stat is chosen. Writes payload_json.

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.
            stat: ``attack``, ``defense``, or ``speed``.

        Returns:
            dict[str, Any]: Cultivated public payload.

        Raises:
            AppError: 40223 not cultivable / illegal stat / cap; 40200 poor.
        """
        private, payload = await self._require_cultivable(character, technique_id)
        key = str(stat or "").strip()
        if key not in ("attack", "defense", "speed"):
            raise AppError(ERR_CRAFT_CULTIVATE, "基础加成立项非法", http_status=400)
        craft = get_game_config().research.technique_craft
        base_raw = payload.get("base") or {}
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        total = (
            int(base.get("attack") or 0)
            + int(base.get("defense") or 0)
            + int(base.get("speed") or 0)
        )
        rank = craft.ranks.get(str(private.major_rank)) or craft.ranks.get("body_tempering")
        cap = int(rank.base_upgrade_cap) if rank is not None else 0
        if total + 1 > cap:
            raise AppError(ERR_CRAFT_CULTIVATE, "基础加成次数已达当前阶上限", http_status=400)
        efficacy = str(payload.get("efficacy") or "")
        costs = craft.spirit_upgrade_cost if efficacy in SPELL_EFFICACIES else craft.body_upgrade_cost
        cost = self._table_cost(costs, total)
        self._deduct_reroll_cost(character, efficacy, cost)
        base[key] = int(base.get(key) or 0) + 1
        payload["base"] = base
        new_level = total + 1
        payload["upgrade_points"] = int(payload.get("upgrade_points") or 0) + (
            upgrade_points_for_base_level(new_level)
        )
        self._persist_payload(private, payload)
        await self._session.flush()
        logger.info(
            "technique craft base-upgrade character_id=%s technique_id=%s stat=%s cost=%s",
            character.id,
            technique_id,
            key,
            cost,
        )
        return self._cultivate_public(private, payload)

    async def upgrade_affix(
        self,
        character: Character,
        technique_id: str,
        slot: int,
    ) -> dict[str, Any]:
        """
        Pay affix-upgrade cost, then roll ``affix_upgrade_fail_rate``.

        Failure still charges; ``chosen_level`` stays. Success increments
        level and adds ``affix_upgrade_points``.

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.
            slot: 0-based affix column.

        Returns:
            dict[str, Any]: Cultivated public payload.
        """
        private, payload = await self._require_cultivable(character, technique_id)
        slots = self._payload_affix_slots(payload, str(private.major_rank or "body_tempering"))
        cell = self._require_slot(slots, slot)
        if not str(cell.get("chosen_id") or "").strip():
            raise AppError(ERR_CRAFT_CULTIVATE, "该栏尚未确认词条", http_status=400)
        craft = get_game_config().research.technique_craft
        level = int(cell.get("chosen_level") or 0)
        rarity = str(cell.get("chosen_rarity") or "").strip() or resolve_affix_rarity(
            str(cell.get("chosen_id") or "")
        )
        cost = int(
            round(
                self._table_cost(craft.affix_upgrade_cost, level)
                * affix_upgrade_cost_multiplier(rarity)
            )
        )
        efficacy = str(payload.get("efficacy") or "")
        self._deduct_reroll_cost(character, efficacy, cost)
        ok = bool(roll_affix_upgrade_success(float(craft.affix_upgrade_fail_rate)))
        if ok:
            new_level = level + 1
            cell["chosen_level"] = new_level
            cell["chosen_rarity"] = rarity
            cell["upgrade_count"] = int(cell.get("upgrade_count") or 0) + 1
            payload["upgrade_points"] = int(payload.get("upgrade_points") or 0) + (
                upgrade_points_for_affix_level(new_level)
            )
        payload["affixes"] = slots
        self._persist_payload(private, payload)
        await self._session.flush()
        logger.info(
            "technique craft affix-upgrade character_id=%s technique_id=%s slot=%s success=%s cost=%s",
            character.id,
            technique_id,
            slot,
            ok,
            cost,
        )
        return self._cultivate_public(private, payload)

    async def breakthrough(
        self,
        character: Character,
        technique_id: str,
    ) -> dict[str, Any]:
        """
        Spend breakthrough resources and roll ``breakthrough_fail_rate``.

        Illegal next rank (missing from ranks, or height above the character)
        raises 40223 before charging. Failure deducts only the resource cost.
        Success raises ``major_rank`` and keeps ``upgrade_points``.

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.

        Returns:
            dict[str, Any]: Cultivated public payload.

        Raises:
            AppError: 40223 illegal breakthrough; 40200 poor.
        """
        private, payload = await self._require_cultivable(character, technique_id)
        craft = get_game_config().research.technique_craft
        current = str(private.major_rank or "body_tempering")
        points = int(payload.get("upgrade_points") or 0)
        if not can_breakthrough(current, points, str(character.major_realm or ""), craft.ranks):
            raise AppError(ERR_CRAFT_CULTIVATE, "无法突破当前功法阶", http_status=400)
        nxt = next_rank_id(current)
        if not nxt:
            raise AppError(ERR_CRAFT_CULTIVATE, "无法突破当前功法阶", http_status=400)
        efficacy = str(payload.get("efficacy") or "")
        cost = int(
            craft.breakthrough_cost_cultivation
            if efficacy in SPELL_EFFICACIES
            else craft.breakthrough_cost_body
        )
        self._deduct_reroll_cost(character, efficacy, cost)
        ok = bool(roll_breakthrough_success(float(craft.breakthrough_fail_rate)))
        if ok:
            private.major_rank = nxt
            slots = self._payload_affix_slots(payload, current)
            for cell in slots:
                if str(cell.get("chosen_id") or "").strip():
                    cell["rank_boost"] = int(cell.get("rank_boost") or 0) + 1
            payload["affixes"] = slots
            payload["affixes"] = self._payload_affix_slots(payload, nxt)
        self._persist_payload(private, payload)
        await self._session.flush()
        logger.info(
            "technique craft breakthrough character_id=%s technique_id=%s success=%s next=%s",
            character.id,
            technique_id,
            ok,
            nxt,
        )
        return self._cultivate_public(private, payload)

    async def roll_cultivate_affix(
        self,
        character: Character,
        technique_id: str,
        slot: int,
    ) -> dict[str, Any]:
        """
        Roll three options for an empty cultivate slot (breakthrough pad / unfilled).

        Only empty columns (no ``chosen_id``) may be filled here.

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.
            slot: 0-based affix column.

        Returns:
            dict[str, Any]: Cultivated public payload.
        """
        private, payload = await self._require_cultivable(character, technique_id)
        slots = self._payload_affix_slots(payload, str(private.major_rank or CRAFT_INITIAL_RANK))
        cell = self._require_slot(slots, slot)
        if str(cell.get("chosen_id") or "").strip():
            raise AppError(ERR_CRAFT_CULTIVATE, "该栏已有词条，请使用升级", http_status=400)
        if cell.get("options"):
            raise AppError(ERR_CRAFT_CULTIVATE, "该栏已生成词条", http_status=400)
        pool = self._payload_affix_pool_ids(payload)
        if not pool:
            raise AppError(ERR_CRAFT_CULTIVATE, "无可用词条", http_status=400)
        cell["options"] = self._weighted_affix_roll(pool)
        cell["chosen_id"] = None
        cell["chosen_rarity"] = None
        cell["chosen_level"] = 0
        cell["upgrade_count"] = 0
        cell["rank_boost"] = 0
        payload["affixes"] = slots
        self._persist_payload(private, payload)
        await self._session.flush()
        logger.info(
            "technique craft cultivate affix roll character_id=%s technique_id=%s slot=%s",
            character.id,
            technique_id,
            slot,
        )
        return self._cultivate_public(private, payload)

    async def choose_cultivate_affix(
        self,
        character: Character,
        technique_id: str,
        slot: int,
        affix_id: str,
    ) -> dict[str, Any]:
        """
        Lock one rolled option onto an empty cultivate slot.

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.
            slot: 0-based affix column.
            affix_id: Must be in that slot's ``options``.

        Returns:
            dict[str, Any]: Cultivated public payload.
        """
        private, payload = await self._require_cultivable(character, technique_id)
        slots = self._payload_affix_slots(payload, str(private.major_rank or CRAFT_INITIAL_RANK))
        cell = self._require_slot(slots, slot)
        if str(cell.get("chosen_id") or "").strip():
            raise AppError(ERR_CRAFT_CULTIVATE, "该栏已有词条，请使用升级", http_status=400)
        options = [str(x) for x in (cell.get("options") or [])]
        pick = str(affix_id or "").strip()
        if not options:
            raise AppError(ERR_CRAFT_CULTIVATE, "该栏尚未生成词条", http_status=400)
        if pick not in options:
            raise AppError(ERR_RESEARCH_AFFIX_SLOTS, "词条不在候选中", http_status=400)
        cell["chosen_id"] = pick
        cell["chosen_rarity"] = resolve_affix_rarity(pick)
        cell["rank_boost"] = 0
        payload["affixes"] = slots
        self._persist_payload(private, payload)
        await self._session.flush()
        logger.info(
            "technique craft cultivate affix choose character_id=%s technique_id=%s slot=%s affix_id=%s",
            character.id,
            technique_id,
            slot,
            pick,
        )
        return self._cultivate_public(private, payload)

    async def reroll_cultivate_affix(
        self,
        character: Character,
        technique_id: str,
        slot: int,
    ) -> dict[str, Any]:
        """
        Pay reroll cost and redraw options on an empty cultivate slot.

        Refuses slots that already locked a chosen affix (use upgrade instead).

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.
            slot: 0-based affix column.

        Returns:
            dict[str, Any]: Cultivated public payload.
        """
        private, payload = await self._require_cultivable(character, technique_id)
        slots = self._payload_affix_slots(payload, str(private.major_rank or CRAFT_INITIAL_RANK))
        cell = self._require_slot(slots, slot)
        if str(cell.get("chosen_id") or "").strip():
            raise AppError(ERR_CRAFT_CULTIVATE, "该栏已有词条，请使用升级", http_status=400)
        pool = self._payload_affix_pool_ids(payload)
        if not pool:
            raise AppError(ERR_CRAFT_CULTIVATE, "无可用词条", http_status=400)
        costs = tuple(int(x) for x in get_game_config().research.technique_craft.affix_reroll_cost)
        n = int(cell.get("reroll_count") or 0)
        cost = int(costs[min(n, len(costs) - 1)]) if costs else 0
        efficacy = str(payload.get("efficacy") or "")
        self._deduct_reroll_cost(character, efficacy, cost)
        cell["options"] = self._weighted_affix_roll(pool)
        cell["chosen_id"] = None
        cell["chosen_rarity"] = None
        cell["chosen_level"] = 0
        cell["upgrade_count"] = 0
        cell["rank_boost"] = 0
        cell["reroll_count"] = n + 1
        payload["affixes"] = slots
        self._persist_payload(private, payload)
        await self._session.flush()
        logger.info(
            "technique craft cultivate affix reroll character_id=%s technique_id=%s slot=%s cost=%s",
            character.id,
            technique_id,
            slot,
            cost,
        )
        return self._cultivate_public(private, payload)

    async def print_manual(
        self,
        character: Character,
        technique_id: str,
    ) -> dict[str, Any]:
        """
        Spend print cost and grant one unstacked technique manual of the current snapshot.

        Only the original research author may print. The private technique row is
        not mutated. Non-empty ``meta`` forces a new inventory row (no stacking).
        If the author is in a sect with a non-empty specialty, that value is
        stamped onto the snapshot as ``specialty_tag`` (intrinsic at print time).

        Args:
            character: Acting original author.
            technique_id: Learned custom technique id.

        Returns:
            dict[str, Any]: ``item_id`` plus the snapshot written into inventory meta.

        Raises:
            AppError: 40225 if not the original author / not research; 40200 if poor.
        """
        try:
            private, payload = await self._require_cultivable(character, technique_id)
        except AppError as exc:
            if exc.code == ERR_CRAFT_CULTIVATE:
                raise AppError(ERR_CRAFT_MANUAL, "仅原创者可制成秘籍", http_status=400) from exc
            raise
        efficacy = str(payload.get("efficacy") or "")
        craft = get_game_config().research.technique_craft
        cost = (
            craft.print_manual_cost_cultivation
            if efficacy in SPELL_EFFICACIES
            else craft.print_manual_cost_body
        )
        self._deduct_reroll_cost(character, efficacy, int(cost))
        snapshot = self._manual_snapshot(private, payload)
        # Intrinsic specialty at print time (author's current sect), not at donate.
        sect_id = getattr(character, "sect_id", None)
        if sect_id is not None:
            sect = await self._session.get(Sect, int(sect_id))
            specialty = str(getattr(sect, "specialty", None) or "").strip() if sect else ""
            if specialty:
                snapshot["specialty_tag"] = specialty
        inv = InventoryService(self._session)
        await inv.add_item(
            character.id,
            item_type="manual",
            item_id=CARD_MANUAL_ID,
            quantity=1,
            meta=snapshot,
        )
        await self._session.flush()
        logger.info(
            "technique craft print-manual character_id=%s technique_id=%s cost=%s",
            character.id,
            technique_id,
            cost,
        )
        return {"item_id": CARD_MANUAL_ID, "snapshot": snapshot}

    async def abolish_technique(
        self,
        character: Character,
        technique_id: str,
    ) -> dict[str, Any]:
        """
        Permanently remove the author's original technique from their learned list.

        Requires the technique to be unequipped on both main and avatar loadouts.
        Manual / scripture / disciple copies keep their own PrivateTechnique rows
        and ``origin_technique_id`` snapshots; they are not deleted.

        Args:
            character: Original author.
            technique_id: Author's private technique id.

        Returns:
            dict[str, Any]: ``{technique_id, abolished: true}``.

        Raises:
            AppError: 40228 if not owner, equipped, or not an original research technique.
        """
        from sqlalchemy import delete

        from app.db.models.avatar import Avatar
        from app.db.models.avatar_loadout import AvatarTechniqueSlot
        from app.db.models.technique import CharacterTechniqueSlot

        tid = str(technique_id or "").strip()
        if not tid:
            raise AppError(ERR_CRAFT_ABOLISH, "功法不存在", http_status=404)

        try:
            private, _payload = await self._require_cultivable(character, tid)
        except AppError as exc:
            if exc.code in (ERR_CRAFT_CULTIVATE, ERR_RESEARCH_SESSION):
                raise AppError(ERR_CRAFT_ABOLISH, "仅可废除自己的原创功法", http_status=400) from exc
            raise

        equipped = await self._session.execute(
            select(CharacterTechniqueSlot.id)
            .where(
                CharacterTechniqueSlot.character_id == character.id,
                CharacterTechniqueSlot.technique_id == tid,
            )
            .limit(1)
        )
        if equipped.scalar_one_or_none() is not None:
            raise AppError(ERR_CRAFT_ABOLISH, "请先卸下装备中的该功法", http_status=400)

        avatar_ids = list(
            (
                await self._session.execute(
                    select(Avatar.id).where(Avatar.character_id == character.id)
                )
            ).scalars().all()
        )
        if avatar_ids:
            avatar_eq = await self._session.execute(
                select(AvatarTechniqueSlot.id)
                .where(
                    AvatarTechniqueSlot.avatar_id.in_(avatar_ids),
                    AvatarTechniqueSlot.technique_id == tid,
                )
                .limit(1)
            )
            if avatar_eq.scalar_one_or_none() is not None:
                raise AppError(ERR_CRAFT_ABOLISH, "请先卸下化身装备中的该功法", http_status=400)

        await self._session.execute(
            delete(CharacterTechnique).where(
                CharacterTechnique.character_id == character.id,
                CharacterTechnique.technique_id == tid,
            )
        )
        await self._session.delete(private)
        await self._session.flush()
        logger.info(
            "technique craft abolished character_id=%s technique_id=%s",
            character.id,
            tid,
        )
        return {"technique_id": tid, "abolished": True}

    async def learn_from_manual_meta(
        self,
        character: Character,
        meta: dict[str, Any] | None,
        *,
        source: str = TECHNIQUE_SOURCE_CHANCE,
    ) -> dict[str, Any]:
        """
        Grant a frozen copy of a printed technique snapshot. Does not consume the book.

        ``author_character_id`` stays the original researcher. Numeric stats are
        copied verbatim. ``origin_technique_id`` is written onto the copy payload
        so a second learn of the same origin fail-closes.

        Args:
            character: Learner (must not be the snapshot author).
            meta: Inventory row snapshot, or None if the row has no/invalid JSON.
            source: CharacterTechnique.source stamp. Bag manuals keep the default
                ``chance``; scripture exchange passes ``sect``.

        Returns:
            dict[str, Any]: ``technique_id`` of the new private copy.

        Raises:
            AppError: 40225 if the learner is the author; 40226 if the snapshot
                is unusable, already learned, or below rank.
        """
        snapshot = self._require_manual_snapshot(meta)
        origin = str(snapshot["origin_technique_id"])
        author_id = int(snapshot["author_character_id"])
        if int(character.id) == author_id:
            raise AppError(ERR_CRAFT_MANUAL, "不可学习自己的秘籍", http_status=400)
        if await self._already_learned_origin(character, origin):
            raise AppError(ERR_CRAFT_LEARN, "已习得该功法", http_status=400)
        if not learner_meets_manual_rank(
            str(character.major_realm or ""),
            str(snapshot["major_rank"]),
        ):
            raise AppError(ERR_CRAFT_LEARN, "境界不足", http_status=400)

        frozen = copy.deepcopy(snapshot["payload"])
        frozen["origin_technique_id"] = origin
        stats = copy.deepcopy(snapshot["stats"])
        affix_ids = list(snapshot["affix_ids"])
        efficacy = str(frozen.get("efficacy") or "")
        cfg = get_game_config()
        technique_id = f"{PRIVATE_ID_PREFIX}:technique:{character.id}:{secrets.token_hex(4)}"
        private = PrivateTechnique(
            character_id=int(character.id),
            technique_id=technique_id,
            label_zh=str(snapshot["label_zh"] or ""),
            revision=1,
            schema_version=cfg.research.schema_version,
            affix_ids_json=json.dumps(affix_ids, ensure_ascii=False),
            stats_json=json.dumps(stats, ensure_ascii=False),
            payload_json=json.dumps(frozen, ensure_ascii=False),
            major_rank=str(snapshot["major_rank"]),
            author_character_id=author_id,
            track="spirit" if efficacy in SPELL_EFFICACIES else "body",
            max_level=int(cfg.research.technique.max_level),
            source=RESEARCH_SOURCE_CUSTOM,
        )
        self._session.add(private)
        self._session.add(
            CharacterTechnique(
                character_id=int(character.id),
                technique_id=technique_id,
                level=1,
                source=normalize_technique_source(source),
            )
        )
        await self._session.flush()
        logger.info(
            "technique craft learn-manual character_id=%s origin=%s copy=%s",
            character.id,
            origin,
            technique_id,
        )
        return {"technique_id": technique_id}

    @staticmethod
    def _require_manual_snapshot(meta: dict[str, Any] | None) -> dict[str, Any]:
        """Parse a printed-manual meta dict or raise 40226."""
        if not isinstance(meta, dict):
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        if str(meta.get("manual_kind") or "") != "technique":
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        origin = str(meta.get("origin_technique_id") or "").strip()
        if not origin:
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        try:
            author_id = int(meta["author_character_id"])
        except (KeyError, TypeError, ValueError):
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400) from None
        major_rank = str(meta.get("major_rank") or "").strip()
        if not major_rank:
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        payload = meta.get("payload")
        if not isinstance(payload, dict):
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        stats = meta.get("stats")
        if not isinstance(stats, dict):
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        affix_ids = meta.get("affix_ids")
        if not isinstance(affix_ids, list):
            raise AppError(ERR_CRAFT_LEARN, "秘籍无效", http_status=400)
        return {
            "origin_technique_id": origin,
            "author_character_id": author_id,
            "label_zh": str(meta.get("label_zh") or ""),
            "major_rank": major_rank,
            "payload": payload,
            "stats": stats,
            "affix_ids": affix_ids,
        }

    async def _already_learned_origin(self, character: Character, origin: str) -> bool:
        """True if the learner already has this origin as id or payload origin."""
        learned = await self._session.execute(
            select(CharacterTechnique.id)
            .where(
                CharacterTechnique.character_id == character.id,
                CharacterTechnique.technique_id == origin,
            )
            .limit(1)
        )
        if learned.scalar_one_or_none() is not None:
            return True
        privates = (
            await self._session.execute(
                select(PrivateTechnique).where(
                    PrivateTechnique.character_id == character.id,
                )
            )
        ).scalars().all()
        for row in privates:
            try:
                body = json.loads(row.payload_json or "{}")
            except json.JSONDecodeError:
                continue
            copied = str(body.get("origin_technique_id") or "") if isinstance(body, dict) else ""
            if copied == origin:
                return True
        return False

    @staticmethod
    def _manual_snapshot(
        private: PrivateTechnique,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Current technique snapshot for inventory meta. Does not mutate ``payload``."""
        frozen = copy.deepcopy(payload)
        author = getattr(private, "author_character_id", None)
        if author is None:
            author = private.character_id
        try:
            affix_ids = json.loads(private.affix_ids_json or "[]")
        except json.JSONDecodeError:
            affix_ids = []
        if not isinstance(affix_ids, list):
            affix_ids = []
        if frozen.get("efficacy"):
            stats = payload_attr_grants(frozen)
        else:
            try:
                stats = json.loads(private.stats_json or "{}")
            except json.JSONDecodeError:
                stats = {}
            if not isinstance(stats, dict):
                stats = {}
        return {
            "manual_kind": "technique",
            "origin_technique_id": str(private.technique_id),
            "author_character_id": int(author),
            "label_zh": str(private.label_zh or ""),
            "major_rank": str(private.major_rank or ""),
            "payload": frozen,
            "stats": stats,
            "affix_ids": affix_ids,
        }

    async def _require_cultivable(
        self,
        character: Character,
        technique_id: str,
    ) -> tuple[PrivateTechnique, dict[str, Any]]:
        """Load the author's research technique or raise 40223."""
        learned = await self._session.execute(
            select(CharacterTechnique)
            .where(
                CharacterTechnique.character_id == character.id,
                CharacterTechnique.technique_id == technique_id,
            )
            .limit(1)
        )
        row = learned.scalar_one_or_none()
        if row is None or normalize_technique_source(getattr(row, "source", None)) != (
            TECHNIQUE_SOURCE_RESEARCH
        ):
            raise AppError(ERR_CRAFT_CULTIVATE, "仅原创功法可培养", http_status=400)
        private_row = await self._session.execute(
            select(PrivateTechnique)
            .where(PrivateTechnique.technique_id == technique_id)
            .limit(1)
        )
        private = private_row.scalar_one_or_none()
        if private is None:
            raise AppError(ERR_CRAFT_CULTIVATE, "仅原创功法可培养", http_status=400)
        author = getattr(private, "author_character_id", None)
        if author is None:
            author = private.character_id
        if int(author) != int(character.id):
            raise AppError(ERR_CRAFT_CULTIVATE, "仅原创者可培养", http_status=400)
        try:
            raw = json.loads(private.payload_json or "{}")
        except json.JSONDecodeError:
            raw = {}
        payload = dict(raw) if isinstance(raw, dict) else {}
        return private, payload

    @classmethod
    def _payload_affix_slots(cls, payload: dict[str, Any], major_rank: str) -> list[dict[str, Any]]:
        """
        Parse payload affixes and pad empty columns.

        Target count = max(create_affix_slots, technique-rank affix_slots, existing).
        Never shrinks columns that already exist.
        """
        raw = payload.get("affixes") or []
        slots: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    cell = dict(cls._empty_affix_slot())
                    cell.update(item)
                    slots.append(cell)
        create_n = cls._create_affix_slots_from_payload(payload)
        rank_n = cls._rank_affix_slots(major_rank)
        n = max(create_n, rank_n, len(slots))
        while len(slots) < n:
            slots.append(cls._empty_affix_slot())
        return slots

    @staticmethod
    def _table_cost(table: tuple[int, ...] | list[int], index: int) -> int:
        """Cost at ``min(index, len-1)``; empty table is free."""
        seq = tuple(int(x) for x in table)
        if not seq:
            return 0
        return int(seq[min(max(index, 0), len(seq) - 1)])

    @staticmethod
    def _persist_payload(private: PrivateTechnique, payload: dict[str, Any]) -> None:
        """Write payload_json and recompute stats_json / affix_ids. Does not touch drafts."""
        private.payload_json = json.dumps(payload, ensure_ascii=False)
        private.stats_json = json.dumps(payload_attr_grants(payload), ensure_ascii=False)
        chosen_ids = [
            str(cell.get("chosen_id") or "").strip()
            for cell in (payload.get("affixes") or [])
            if isinstance(cell, dict) and str(cell.get("chosen_id") or "").strip()
        ]
        private.affix_ids_json = json.dumps(chosen_ids, ensure_ascii=False)

    @staticmethod
    def _cultivate_public(private: PrivateTechnique, payload: dict[str, Any]) -> dict[str, Any]:
        """Public cultivate result for HTTP / tests."""
        base_raw = payload.get("base") or {}
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        major_rank = str(private.major_rank or "")
        affixes = enrich_affix_slots_public(
            TechniqueCraftService._payload_affix_slots(payload, major_rank)
        )
        nxt = next_rank_id(major_rank)
        craft = get_game_config().research.technique_craft
        breakthrough_points_required: int | None = None
        if nxt and nxt in craft.ranks:
            breakthrough_points_required = int(
                getattr(craft.ranks[nxt], "upgrade_points_required", 0) or 0
            )
        create_slots = payload.get("create_affix_slots")
        return {
            "technique_id": private.technique_id,
            "major_rank": major_rank,
            "major_rank_label_zh": major_rank_label_zh(major_rank),
            "upgrade_points": int(payload.get("upgrade_points") or 0),
            "base": base,
            "affixes": affixes,
            "stats": payload_attr_grants(payload),
            "next_rank": nxt,
            "next_rank_label_zh": major_rank_label_zh(nxt) if nxt else None,
            "breakthrough_points_required": breakthrough_points_required,
            "create_affix_slots": int(create_slots) if create_slots is not None else None,
        }

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
        if row.phase == DRAFT_PHASE_FINALIZED:
            raise AppError(ERR_RESEARCH_FROZEN, "已定稿不可改，只能另开新研", http_status=400)
        return row

    @staticmethod
    def _draft_public(row: TechniqueResearchDraft) -> dict[str, Any]:
        elements = TechniqueCraftService._draft_elements(row)
        try:
            base_raw = json.loads(row.base_json or "{}")
        except json.JSONDecodeError:
            base_raw = {}
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        base.pop(CREATE_AFFIX_SLOTS_KEY, None)
        # Pad columns for UI without requiring a service instance.
        affixes = TechniqueCraftService._load_affix_slots(row)
        chosen = any(str(cell.get("chosen_id") or "").strip() for cell in affixes)
        can_finalize = bool(
            elements
            and str(row.efficacy or "").strip()
            and bool(getattr(row, "conditions_confirmed", False))
            and chosen
            and row.phase == DRAFT_PHASE_EMBEDDING
        )
        return TechniqueDraftPublic(
            id=row.id,
            phase=row.phase,
            elements=elements,
            efficacy=row.efficacy or None,
            can_finalize=can_finalize,
            label_zh=row.label_zh or "",
            major_rank=row.major_rank,
            element_limit=row.element_limit or None,
            weapon_limit=row.weapon_limit or None,
            upgrade_points=int(row.upgrade_points or 0),
            base=base,
            affixes=enrich_affix_slots_public(affixes),
        ).model_dump()
