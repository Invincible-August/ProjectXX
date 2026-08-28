"""
Technique self-research drafts (功法自研 P1).

Create / list / abandon / embed / conditions / affix roll-choose-reroll / finalize /
cultivate (base upgrade, affix upgrade, breakthrough).
Creating a draft does not consume cards. Embed always consumes the formal card.
Finalize writes PrivateTechnique + CharacterTechnique and leaves the draft list.
Cultivate mutates PrivateTechnique.payload_json, not the draft row.
"""

from __future__ import annotations

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
from app.constants.technique import TECHNIQUE_SOURCE_RESEARCH, normalize_technique_source
from app.constants.technique_craft import (
    CARD_FORMAL_EFFICACY_ID,
    CARD_FORMAL_ELEMENT_ID,
    DRAFT_PHASE_ABANDONED,
    DRAFT_PHASE_EMBEDDING,
    DRAFT_PHASE_FINALIZED,
    ERR_CRAFT_CARD,
    ERR_CRAFT_CULTIVATE,
    ERR_CRAFT_EMBED,
    ERR_CRAFT_FINALIZE,
    SPELL_EFFICACIES,
    WEAPON_LIMITS,
)
from app.db.models.character import Character
from app.db.models.inventory_item import InventoryItem
from app.db.models.research import PrivateTechnique
from app.db.models.technique import CharacterTechnique
from app.db.models.technique_craft import TechniqueResearchDraft
from app.domain.research_schema import is_valid_zh_label
from app.domain.technique_craft import (
    can_breakthrough,
    filter_affixes,
    next_rank_id,
    payload_attr_grants,
    roll_affix_upgrade_success,
    roll_breakthrough_success,
    roll_embed_success,
    roll_three,
    upgrade_points_for_affix_level,
    upgrade_points_for_base_level,
)
from app.schemas.common import AppError
from app.schemas.technique_craft import TechniqueDraftPublic
from app.services.inventory_service import InventoryService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class TechniqueCraftService:
    """Multi-draft technique craft: create, list, abandon, embed, conditions, affixes, finalize, cultivate."""

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
            conditions_confirmed=False,
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
    def _rank_affix_slots(major_rank: str) -> int:
        """Column count from ``ranks[major_rank].affix_slots`` (body_tempering default 1)."""
        ranks = get_game_config().research.technique_craft.ranks
        rank = ranks.get(str(major_rank)) or ranks.get("body_tempering")
        if rank is None:
            return 1
        return max(1, int(rank.affix_slots or 1))

    @staticmethod
    def _affix_slot_count(row: TechniqueResearchDraft) -> int:
        """Column count for a draft's current major rank."""
        return TechniqueCraftService._rank_affix_slots(str(row.major_rank or "body_tempering"))

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

        cfg = get_game_config()
        base_raw = json.loads(row.base_json or "{}")
        payload = {
            "elements": elements,
            "efficacy": str(row.efficacy),
            "element_limit": row.element_limit,
            "weapon_limit": row.weapon_limit,
            "base": dict(base_raw) if isinstance(base_raw, dict) else {},
            "affixes": slots,
            "upgrade_points": int(row.upgrade_points or 0),
        }
        stats = payload_attr_grants(payload)
        slug = secrets.token_hex(4)
        technique_id = f"{PRIVATE_ID_PREFIX}:technique:{character.id}:{slug}"
        efficacy = str(row.efficacy)
        private = PrivateTechnique(
            character_id=character.id,
            technique_id=technique_id,
            label_zh=label_zh.strip(),
            revision=1,
            schema_version=cfg.research.schema_version,
            affix_ids_json=json.dumps(chosen_ids, ensure_ascii=False),
            stats_json=json.dumps(stats, ensure_ascii=False),
            payload_json=json.dumps(payload, ensure_ascii=False),
            major_rank=str(row.major_rank or "body_tempering"),
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
        row.label_zh = label_zh.strip()
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
        cost = self._table_cost(craft.affix_upgrade_cost, level)
        efficacy = str(payload.get("efficacy") or "")
        self._deduct_reroll_cost(character, efficacy, cost)
        ok = bool(roll_affix_upgrade_success(float(craft.affix_upgrade_fail_rate)))
        if ok:
            new_level = level + 1
            cell["chosen_level"] = new_level
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

    def _payload_affix_slots(self, payload: dict[str, Any], major_rank: str) -> list[dict[str, Any]]:
        """Parse payload affixes and pad empty columns when the rank gains slots."""
        raw = payload.get("affixes") or []
        slots: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    cell = dict(self._empty_affix_slot())
                    cell.update(item)
                    slots.append(cell)
        n = self._rank_affix_slots(major_rank)
        while len(slots) < n:
            slots.append(self._empty_affix_slot())
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
        """Write payload_json and recompute stats_json grants. Does not touch drafts."""
        private.payload_json = json.dumps(payload, ensure_ascii=False)
        private.stats_json = json.dumps(payload_attr_grants(payload), ensure_ascii=False)

    @staticmethod
    def _cultivate_public(private: PrivateTechnique, payload: dict[str, Any]) -> dict[str, Any]:
        """Public cultivate result for HTTP / tests."""
        base_raw = payload.get("base") or {}
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        affixes = list(payload.get("affixes") or [])
        return {
            "technique_id": private.technique_id,
            "major_rank": str(private.major_rank or ""),
            "upgrade_points": int(payload.get("upgrade_points") or 0),
            "base": base,
            "affixes": affixes,
            "stats": payload_attr_grants(payload),
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
        base_raw = json.loads(row.base_json or "{}")
        base = dict(base_raw) if isinstance(base_raw, dict) else {}
        affix_raw = json.loads(row.affixes_json or "[]")
        affixes = list(affix_raw) if isinstance(affix_raw, list) else []
        chosen = any(
            isinstance(cell, dict) and str(cell.get("chosen_id") or "").strip()
            for cell in affixes
        )
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
            affixes=affixes,
        ).model_dump()
