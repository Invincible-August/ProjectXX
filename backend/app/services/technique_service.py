"""
功法列表与创角默认解锁（M2）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.avatar import (
    ERR_AVATAR_EXISTS_OR_MISSING,
    LOADOUT_ACTOR_AVATAR,
    LOADOUT_ACTOR_MAIN,
    normalize_loadout_actor,
)
from app.constants.combat_attrs import COMBAT_FINAL_KEYS
from app.constants.technique import (
    ERR_TECHNIQUE_LOADOUT,
    ERR_TECHNIQUE_LOADOUT_ZH,
    TECHNIQUE_SLOT_ART,
    TECHNIQUE_SLOT_HELP_ZH,
    TECHNIQUE_SLOT_LABELS_ZH,
    TECHNIQUE_SLOT_MAIN,
    TECHNIQUE_SOURCE_RESEARCH,
    TECHNIQUE_SOURCE_SYSTEM,
    element_view,
    normalize_technique_source,
    technique_source_label_zh,
)
from app.constants.technique_craft import ERR_CRAFT_EQUIP_ROLE, IDLE_EFFICACIES
from app.db.models.character import Character
from app.db.models.technique import CharacterTechnique, CharacterTechniqueSlot
from app.db.models.avatar_loadout import AvatarTechniqueSlot
from app.domain.technique_craft import payload_attr_grants
from app.schemas.common import AppError
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
                    source=TECHNIQUE_SOURCE_SYSTEM,
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
        missing_ids: list[str] = []
        for row in rows:
            tech = cfg.techniques.get(row.technique_id)
            if tech is None:
                missing_ids.append(str(row.technique_id))
                continue
            next_cost = None
            if row.level < tech.max_level:
                idx = row.level
                costs = tech.cost_per_level
                if 0 <= idx < len(costs):
                    next_cost = int(costs[idx])
            source = normalize_technique_source(getattr(row, "source", None))
            items.append(
                {
                    "id": row.technique_id,
                    "name": tech.name,
                    "level": row.level,
                    "max_level": tech.max_level,
                    "track": tech.track,
                    "next_cost": next_cost,
                    "source": source,
                    "source_label_zh": technique_source_label_zh(source),
                    "elements": [element_view(eid) for eid in tech.elements],
                    "help_zh": tech.help_zh,
                    "learn_requires": dict(tech.learn_requires),
                    "skills_main": [
                        {
                            "id": sk.skill_id,
                            "label_zh": sk.label_zh,
                            "effect_zh": sk.effect_zh,
                        }
                        for sk in tech.skills_main
                    ],
                    "skills_art": [
                        {
                            "id": sk.skill_id,
                            "label_zh": sk.label_zh,
                            "effect_zh": sk.effect_zh,
                        }
                        for sk in tech.skills_art
                    ],
                },
            )
        if missing_ids:
            from app.services.research_service import ResearchService

            privates = await ResearchService(self._session).get_private_by_ids(
                character.id,
                missing_ids,
            )
            levels = {str(row.technique_id): int(row.level) for row in rows}
            sources = {
                str(row.technique_id): normalize_technique_source(
                    getattr(row, "source", None)
                )
                for row in rows
            }
            for tech_id, private in privates.items():
                level = levels.get(tech_id, 1)
                source = sources.get(tech_id, TECHNIQUE_SOURCE_RESEARCH)
                next_cost = None
                costs = cfg.research.technique.cost_per_level
                if level < int(private.max_level) and 0 <= level < len(costs):
                    next_cost = int(costs[level])
                stats = {}
                payload = TechniqueService._private_payload(private)
                if payload.get("efficacy"):
                    stats = payload_attr_grants(payload)
                else:
                    try:
                        stats = json.loads(private.stats_json or "{}")
                    except json.JSONDecodeError:
                        stats = {}
                author_id = int(
                    getattr(private, "author_character_id", None)
                    or private.character_id
                )
                items.append(
                    {
                        "id": tech_id,
                        "name": private.label_zh,
                        "level": level,
                        "max_level": int(private.max_level),
                        "track": private.track,
                        "next_cost": next_cost,
                        "source": source,
                        "source_label_zh": technique_source_label_zh(source),
                        "elements": [
                            element_view(eid)
                            for eid in (
                                TechniqueService._private_elements(private)
                            )
                        ],
                        "help_zh": "",
                        "learn_requires": {},
                        "skills_main": [],
                        "skills_art": [],
                        "stats": stats,
                        "efficacy": TechniqueService._private_efficacy_of(private),
                        "author_character_id": author_id,
                        "cultivable": author_id == int(character.id)
                        and source == TECHNIQUE_SOURCE_RESEARCH,
                    },
                )
        return items

    def art_slot_cap(
        self,
        character: Character,
        *,
        major_realm: str | None = None,
    ) -> int:
        """技法槽数随大境界增加。"""
        loadout = get_game_config().technique_loadout
        major = str(major_realm or getattr(character, "major_realm", None) or "body_tempering")
        if major in loadout.art_slots_by_major:
            return max(0, int(loadout.art_slots_by_major[major]))
        return max(0, int(loadout.default_art_slots))

    async def _require_avatar(self, character_id: int):
        """Load condensed avatar or raise."""
        from app.services.avatar_repo import fetch_avatar_row

        avatar = await fetch_avatar_row(self._session, character_id)
        if avatar is None:
            raise AppError(
                code=ERR_AVATAR_EXISTS_OR_MISSING,
                message="尚未凝练化身",
                http_status=400,
            )
        return avatar

    async def _actor_major(self, character: Character, actor: str) -> str:
        """Realm key used for slot cap of this wearer."""
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character.id)
            return str(avatar.major_realm or "jindan")
        return str(getattr(character, "major_realm", None) or "body_tempering")

    async def equipped_technique_ids(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> set[str]:
        """Technique ids currently worn by one actor."""
        actor = normalize_loadout_actor(actor)
        try:
            slots = await self.ensure_loadout_slots(character, actor=actor)
        except AppError:
            return set()
        return {
            str(s.technique_id)
            for s in slots
            if str(s.technique_id or "").strip()
        }

    async def list_equipped_technique_items(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> list[dict]:
        """Learned technique rows currently worn by one actor (combat / idle)."""
        ids = await self.equipped_technique_ids(character, actor=actor)
        if not ids:
            return []
        return [it for it in await self.list_my_techniques(character) if str(it["id"]) in ids]

    async def ensure_loadout_slots(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> list[Any]:
        """Ensure one main slot and art-cap art slots exist."""
        actor = normalize_loadout_actor(actor)
        major = await self._actor_major(character, actor)
        cap = self.art_slot_cap(character, major_realm=major)
        wanted: list[tuple[str, int]] = [(TECHNIQUE_SLOT_MAIN, 0)]
        wanted.extend((TECHNIQUE_SLOT_ART, i) for i in range(cap))
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character.id)
            result = await self._session.execute(
                select(AvatarTechniqueSlot).where(
                    AvatarTechniqueSlot.avatar_id == avatar.id,
                ),
            )
            rows = list(result.scalars().all())
            by_key = {(str(r.slot_type), int(r.slot_index)): r for r in rows}
            changed = False
            for slot_type, slot_index in wanted:
                if (slot_type, slot_index) in by_key:
                    continue
                row = AvatarTechniqueSlot(
                    avatar_id=int(avatar.id),
                    slot_type=slot_type,
                    slot_index=slot_index,
                    technique_id=None,
                )
                self._session.add(row)
                by_key[(slot_type, slot_index)] = row
                changed = True
            if changed:
                await self._session.flush()
            return [by_key[key] for key in wanted]

        result = await self._session.execute(
            select(CharacterTechniqueSlot).where(
                CharacterTechniqueSlot.character_id == character.id,
            ),
        )
        rows = list(result.scalars().all())
        by_key = {(str(r.slot_type), int(r.slot_index)): r for r in rows}
        changed = False
        for slot_type, slot_index in wanted:
            if (slot_type, slot_index) in by_key:
                continue
            row = CharacterTechniqueSlot(
                character_id=character.id,
                slot_type=slot_type,
                slot_index=slot_index,
                technique_id=None,
            )
            self._session.add(row)
            by_key[(slot_type, slot_index)] = row
            changed = True
        if changed:
            await self._session.flush()
        return [by_key[key] for key in wanted]

    async def get_loadout_state(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """Build slot board + granted skill chips for the character page."""
        actor = normalize_loadout_actor(actor)
        items = await self.list_my_techniques(character)
        by_id = {str(it["id"]): it for it in items}
        slots = await self.ensure_loadout_slots(character, actor=actor)
        loadout_cfg = get_game_config().technique_loadout
        major = await self._actor_major(character, actor)
        cap = self.art_slot_cap(character, major_realm=major)
        slot_views: list[dict] = []
        granted: list[dict] = []
        seen_skills: set[str] = set()
        for slot in slots:
            tech_id = str(slot.technique_id or "").strip() or None
            item = by_id.get(tech_id) if tech_id else None
            if tech_id and item is None:
                tech_id = None
            view = {
                "slot_type": slot.slot_type,
                "slot_index": int(slot.slot_index),
                "label_zh": TECHNIQUE_SLOT_LABELS_ZH.get(
                    slot.slot_type,
                    slot.slot_type,
                ),
                "technique_id": tech_id,
            }
            if item:
                view["name"] = item["name"]
                view["level"] = item["level"]
                view["max_level"] = item["max_level"]
                view["source"] = item["source"]
                view["source_label_zh"] = item["source_label_zh"]
                view["elements"] = item.get("elements") or []
                view["help_zh"] = item.get("help_zh") or ""
                skill_key = (
                    "skills_main"
                    if slot.slot_type == TECHNIQUE_SLOT_MAIN
                    else "skills_art"
                )
                for skill in item.get(skill_key) or []:
                    sid = str(skill.get("id") or "")
                    if not sid or sid in seen_skills:
                        continue
                    seen_skills.add(sid)
                    granted.append(dict(skill))
            slot_views.append(view)
        return {
            "slots": slot_views,
            "art_slot_cap": cap,
            "main_slots": int(loadout_cfg.main_slots),
            "help_zh": str(loadout_cfg.help_zh or TECHNIQUE_SLOT_HELP_ZH),
            "granted_skills": granted,
        }

    async def get_techniques_page(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """GET /techniques/me payload: learned list + loadout board."""
        actor = normalize_loadout_actor(actor)
        other = (
            LOADOUT_ACTOR_AVATAR
            if actor == LOADOUT_ACTOR_MAIN
            else LOADOUT_ACTOR_MAIN
        )
        other_ids = await self.equipped_technique_ids(character, actor=other)
        items = [
            it
            for it in await self.list_my_techniques(character)
            if str(it["id"]) not in other_ids
        ]
        loadout = await self.get_loadout_state(character, actor=actor)
        return {"items": items, "loadout": loadout}

    async def equip_technique(
        self,
        character: Character,
        *,
        technique_id: str,
        slot_type: str,
        slot_index: int,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """Equip a learned technique into a main or art slot."""
        actor = normalize_loadout_actor(actor)
        role = str(slot_type or "").strip()
        if role not in {TECHNIQUE_SLOT_MAIN, TECHNIQUE_SLOT_ART}:
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message=ERR_TECHNIQUE_LOADOUT_ZH,
                http_status=400,
            )
        index = int(slot_index)
        if index < 0:
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message=ERR_TECHNIQUE_LOADOUT_ZH,
                http_status=400,
            )
        if role == TECHNIQUE_SLOT_MAIN and index != 0:
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message="主功法只能装备在第一格",
                http_status=400,
            )
        if role == TECHNIQUE_SLOT_ART:
            major = await self._actor_major(character, actor)
            if index >= self.art_slot_cap(character, major_realm=major):
                raise AppError(
                    code=ERR_TECHNIQUE_LOADOUT,
                    message="技法槽位不足，需更高修为",
                    http_status=400,
                )
        tid = str(technique_id or "").strip()
        items = await self.list_my_techniques(character)
        item = next((it for it in items if str(it["id"]) == tid), None)
        if item is None:
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message="尚未学会该功法",
                http_status=400,
            )
        if role == TECHNIQUE_SLOT_MAIN:
            efficacy = str(item.get("efficacy") or "").strip()
            if efficacy and efficacy not in IDLE_EFFICACIES:
                raise AppError(
                    code=ERR_CRAFT_EQUIP_ROLE,
                    message="该功法不能装备为主功法",
                    http_status=400,
                )
        other = (
            LOADOUT_ACTOR_AVATAR
            if actor == LOADOUT_ACTOR_MAIN
            else LOADOUT_ACTOR_MAIN
        )
        if tid in await self.equipped_technique_ids(character, actor=other):
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message="该功法已被另一主体装备",
                http_status=400,
            )
        slots = await self.ensure_loadout_slots(character, actor=actor)
        target = next(
            (
                s
                for s in slots
                if s.slot_type == role and int(s.slot_index) == index
            ),
            None,
        )
        if target is None:
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message=ERR_TECHNIQUE_LOADOUT_ZH,
                http_status=400,
            )
        for slot in slots:
            if str(slot.technique_id or "") == tid:
                slot.technique_id = None
        target.technique_id = tid
        await self._session.flush()
        return await self.get_techniques_page(character, actor=actor)

    async def unequip_technique(
        self,
        character: Character,
        *,
        slot_type: str,
        slot_index: int,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """Clear one loadout slot."""
        actor = normalize_loadout_actor(actor)
        role = str(slot_type or "").strip()
        index = int(slot_index)
        slots = await self.ensure_loadout_slots(character, actor=actor)
        target = next(
            (
                s
                for s in slots
                if s.slot_type == role and int(s.slot_index) == index
            ),
            None,
        )
        if target is None:
            raise AppError(
                code=ERR_TECHNIQUE_LOADOUT,
                message=ERR_TECHNIQUE_LOADOUT_ZH,
                http_status=400,
            )
        target.technique_id = None
        await self._session.flush()
        return await self.get_techniques_page(character, actor=actor)

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
                "source": item.get("source") or TECHNIQUE_SOURCE_SYSTEM,
                "source_label_zh": item.get("source_label_zh")
                or technique_source_label_zh(item.get("source")),
            }
            for item in session_techniques
        ]

    @staticmethod
    def compute_technique_combat_amounts(
        techniques: list[dict],
    ) -> dict[str, float]:
        """
        Sum combat-key bonuses from official placeholders and custom research stats.

        Args:
            techniques: Technique list with id, level, and optional stats.

        Returns:
            dict[str, float]: ATTR combat keys with non-zero sums.
        """
        cfg = get_game_config()
        allowed = set(COMBAT_FINAL_KEYS)
        totals: dict[str, float] = {}
        for item in techniques:
            tech = cfg.techniques.get(item["id"])
            level = int(item["level"])
            if tech is not None:
                effects = tech.effects_placeholder
                atk = float(effects.get("atk_bonus_per_level", 0) or 0) * level
                hp = float(effects.get("hp_bonus_per_level", 0) or 0) * level
                if abs(atk) > 1e-9:
                    totals["phys_atk"] = totals.get("phys_atk", 0.0) + atk
                if abs(hp) > 1e-9:
                    totals["hp"] = totals.get("hp", 0.0) + hp
                continue
            stats = item.get("stats") or {}
            scale = max(level, 1)
            for key, raw in stats.items():
                if str(key) not in allowed:
                    continue
                value = float(raw or 0) * scale
                if abs(value) > 1e-9:
                    totals[str(key)] = totals.get(str(key), 0.0) + value
        return totals

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
        amounts = TechniqueService.compute_technique_combat_amounts(techniques)
        return int(amounts.get("phys_atk", 0)), int(amounts.get("hp", 0))

    @staticmethod
    def _private_payload(private: Any) -> dict:
        """Parse ``PrivateTechnique.payload_json``; invalid values become {}."""
        try:
            raw = json.loads(getattr(private, "payload_json", None) or "{}")
        except json.JSONDecodeError:
            return {}
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    def _private_efficacy_of(private: Any) -> str | None:
        """Efficacy id stored on a custom technique, or None."""
        text = str(TechniqueService._private_payload(private).get("efficacy") or "").strip()
        return text or None

    @staticmethod
    def _private_elements(private: Any) -> list[str]:
        """Embedded element ids from custom-technique payload."""
        raw = TechniqueService._private_payload(private).get("elements") or []
        if not isinstance(raw, list):
            return []
        return [str(x) for x in raw if str(x)]


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
