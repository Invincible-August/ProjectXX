"""
神通已学列表与装备槽（展示口子；施放链未开）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.avatar import (
    ERR_AVATAR_EXISTS_OR_MISSING,
    LOADOUT_ACTOR_AVATAR,
    LOADOUT_ACTOR_MAIN,
    normalize_loadout_actor,
)
from app.constants.divine_ability import (
    DIVINE_ABILITY_HELP_ZH,
    ERR_DIVINE_ABILITY_LOADOUT,
    ERR_DIVINE_ABILITY_LOADOUT_ZH,
    element_view,
    normalize_technique_source,
    technique_source_label_zh,
)
from app.constants.technique import TECHNIQUE_SOURCE_SYSTEM
from app.db.models.character import Character
from app.db.models.divine_ability import CharacterDivineAbility, CharacterDivineAbilitySlot
from app.db.models.avatar_loadout import AvatarDivineAbilitySlot
from app.schemas.common import AppError
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

_ZH_ORDINAL = "一二三四五六七八九十"


def compute_divine_ability_slot_cap(
    character: Character,
    *,
    major_realm: str | None = None,
    include_grade: bool = True,
) -> int:
    """Return equippable slot count: realm base plus breakthrough-grade bonus.

    Args:
        character: Character with ``major_realm`` and cached ``divine_ability_slots``.
        major_realm: Override (化身自有境界).
        include_grade: 化身无品阶，传 False.

    Returns:
        Non-negative slot cap used by the character page loadout.
    """
    loadout = get_game_config().divine_ability_loadout
    major = str(major_realm or getattr(character, "major_realm", None) or "body_tempering")
    if major in loadout.slots_by_major:
        realm_slots = max(0, int(loadout.slots_by_major[major]))
    else:
        realm_slots = max(0, int(loadout.default_slots))
    grade_slots = 0
    if include_grade:
        grade_slots = max(0, int(getattr(character, "divine_ability_slots", 0) or 0))
    return realm_slots + grade_slots


def _slot_label_zh(index: int) -> str:
    """Player-visible slot name, 神通一 … 神通十 then 神通11."""
    if 0 <= index < len(_ZH_ORDINAL):
        return f"神通{_ZH_ORDINAL[index]}"
    return f"神通{index + 1}"


class DivineAbilityService:
    """Learned divine-ability pool and variable loadout slots."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Request-scoped async SQLAlchemy session.
        """
        self._session = session

    def slot_cap(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
        major_realm: str | None = None,
    ) -> int:
        """Equip slots from major realm plus grade bonus (no main/sub split)."""
        actor = normalize_loadout_actor(actor)
        return compute_divine_ability_slot_cap(
            character,
            major_realm=major_realm,
            include_grade=actor != LOADOUT_ACTOR_AVATAR,
        )

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

    async def equipped_ability_ids(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> set[str]:
        """Ability ids worn by one actor."""
        actor = normalize_loadout_actor(actor)
        try:
            slots = await self.ensure_loadout_slots(character, actor=actor)
        except AppError:
            return set()
        return {str(s.ability_id) for s in slots if str(s.ability_id or "").strip()}

    async def ensure_default_abilities(self, character_id: int) -> None:
        """Grant all catalog sample abilities if missing."""
        cfg = get_game_config()
        for ability_id in cfg.divine_abilities:
            existing = await self._session.execute(
                select(CharacterDivineAbility.id)
                .where(
                    CharacterDivineAbility.character_id == character_id,
                    CharacterDivineAbility.ability_id == ability_id,
                )
                .limit(1),
            )
            if existing.scalar_one_or_none() is not None:
                continue
            self._session.add(
                CharacterDivineAbility(
                    character_id=character_id,
                    ability_id=ability_id,
                    source=TECHNIQUE_SOURCE_SYSTEM,
                ),
            )
        await self._session.flush()

    async def list_my_abilities(self, character: Character) -> list[dict]:
        """Return learned divine abilities with catalog metadata."""
        await self.ensure_default_abilities(character.id)
        result = await self._session.execute(
            select(CharacterDivineAbility).where(
                CharacterDivineAbility.character_id == character.id,
            ),
        )
        rows = result.scalars().all()
        cfg = get_game_config()
        items: list[dict] = []
        for row in rows:
            body = cfg.divine_abilities.get(row.ability_id)
            if body is None:
                continue
            source = normalize_technique_source(getattr(row, "source", None))
            items.append(
                {
                    "id": row.ability_id,
                    "name": body.name,
                    "icon": str(body.icon or row.ability_id),
                    "source": source,
                    "source_label_zh": technique_source_label_zh(source),
                    "help_zh": body.help_zh,
                    "effect_zh": body.effect_zh,
                    "elements": [element_view(eid) for eid in body.elements],
                },
            )
        return items

    async def ensure_loadout_slots(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> list:
        """Ensure slot rows match the current realm+grade cap; clear overflow."""
        actor = normalize_loadout_actor(actor)
        major = None
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character.id)
            major = str(avatar.major_realm or "jindan")
        cap = self.slot_cap(character, actor=actor, major_realm=major)
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character.id)
            result = await self._session.execute(
                select(AvatarDivineAbilitySlot).where(
                    AvatarDivineAbilitySlot.avatar_id == avatar.id,
                ),
            )
            rows = list(result.scalars().all())
            by_index = {int(r.slot_index): r for r in rows}
            changed = False
            for index in range(cap):
                if index in by_index:
                    continue
                row = AvatarDivineAbilitySlot(
                    avatar_id=int(avatar.id),
                    slot_index=index,
                    ability_id=None,
                )
                self._session.add(row)
                by_index[index] = row
                changed = True
            for index, row in list(by_index.items()):
                if index >= cap and row.ability_id:
                    row.ability_id = None
                    changed = True
            if changed:
                await self._session.flush()
            return [by_index[i] for i in range(cap)]

        result = await self._session.execute(
            select(CharacterDivineAbilitySlot).where(
                CharacterDivineAbilitySlot.character_id == character.id,
            ),
        )
        rows = list(result.scalars().all())
        by_index = {int(r.slot_index): r for r in rows}
        changed = False
        for index in range(cap):
            if index in by_index:
                continue
            row = CharacterDivineAbilitySlot(
                character_id=character.id,
                slot_index=index,
                ability_id=None,
            )
            self._session.add(row)
            by_index[index] = row
            changed = True
        for index, row in list(by_index.items()):
            if index >= cap and row.ability_id:
                row.ability_id = None
                changed = True
        if changed:
            await self._session.flush()
        return [by_index[i] for i in range(cap)]

    async def get_loadout_state(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """Build slot board for the character page."""
        actor = normalize_loadout_actor(actor)
        items = await self.list_my_abilities(character)
        by_id = {str(it["id"]): it for it in items}
        slots = await self.ensure_loadout_slots(character, actor=actor)
        help_zh = str(
            get_game_config().divine_ability_loadout.help_zh or DIVINE_ABILITY_HELP_ZH,
        )
        slot_views: list[dict] = []
        for slot in slots:
            ability_id = str(slot.ability_id or "").strip() or None
            item = by_id.get(ability_id) if ability_id else None
            if ability_id and item is None:
                ability_id = None
            view = {
                "slot_index": int(slot.slot_index),
                "label_zh": _slot_label_zh(int(slot.slot_index)),
                "ability_id": ability_id,
            }
            if item:
                view["name"] = item["name"]
                view["icon"] = item.get("icon") or ability_id
                view["source"] = item["source"]
                view["source_label_zh"] = item["source_label_zh"]
                view["help_zh"] = item.get("help_zh") or ""
                view["effect_zh"] = item.get("effect_zh") or ""
                view["elements"] = item.get("elements") or []
            slot_views.append(view)
        major = None
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character.id)
            major = str(avatar.major_realm or "jindan")
        cap = self.slot_cap(character, actor=actor, major_realm=major)
        grade_slots = 0
        if actor != LOADOUT_ACTOR_AVATAR:
            grade_slots = max(0, int(getattr(character, "divine_ability_slots", 0) or 0))
        return {
            "slots": slot_views,
            "slot_cap": cap,
            "realm_slots": cap - grade_slots,
            "grade_slots": grade_slots,
            "help_zh": help_zh,
        }

    async def get_page(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """GET /divine-abilities/me payload."""
        actor = normalize_loadout_actor(actor)
        other = (
            LOADOUT_ACTOR_AVATAR
            if actor == LOADOUT_ACTOR_MAIN
            else LOADOUT_ACTOR_MAIN
        )
        other_ids = await self.equipped_ability_ids(character, actor=other)
        items = [
            it
            for it in await self.list_my_abilities(character)
            if str(it["id"]) not in other_ids
        ]
        loadout = await self.get_loadout_state(character, actor=actor)
        return {"items": items, "loadout": loadout}

    async def equip_ability(
        self,
        character: Character,
        *,
        ability_id: str,
        slot_index: int,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """Equip a learned ability into one realm+grade slot."""
        actor = normalize_loadout_actor(actor)
        major = None
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character.id)
            major = str(avatar.major_realm or "jindan")
        cap = self.slot_cap(character, actor=actor, major_realm=major)
        index = int(slot_index)
        if cap <= 0 or index < 0 or index >= cap:
            raise AppError(
                code=ERR_DIVINE_ABILITY_LOADOUT,
                message="神通槽位不足，需更高修为或品阶",
                http_status=400,
            )
        tid = str(ability_id or "").strip()
        items = await self.list_my_abilities(character)
        if not any(str(it["id"]) == tid for it in items):
            raise AppError(
                code=ERR_DIVINE_ABILITY_LOADOUT,
                message="尚未学会该神通",
                http_status=400,
            )
        other = (
            LOADOUT_ACTOR_AVATAR
            if actor == LOADOUT_ACTOR_MAIN
            else LOADOUT_ACTOR_MAIN
        )
        if tid in await self.equipped_ability_ids(character, actor=other):
            raise AppError(
                code=ERR_DIVINE_ABILITY_LOADOUT,
                message="该神通已被另一主体装备",
                http_status=400,
            )
        slots = await self.ensure_loadout_slots(character, actor=actor)
        target = next((s for s in slots if int(s.slot_index) == index), None)
        if target is None:
            raise AppError(
                code=ERR_DIVINE_ABILITY_LOADOUT,
                message=ERR_DIVINE_ABILITY_LOADOUT_ZH,
                http_status=400,
            )
        for slot in slots:
            if str(slot.ability_id or "") == tid:
                slot.ability_id = None
        target.ability_id = tid
        await self._session.flush()
        return await self.get_page(character, actor=actor)

    async def unequip_ability(
        self,
        character: Character,
        *,
        slot_index: int,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict:
        """Clear one loadout slot."""
        actor = normalize_loadout_actor(actor)
        index = int(slot_index)
        slots = await self.ensure_loadout_slots(character, actor=actor)
        target = next((s for s in slots if int(s.slot_index) == index), None)
        if target is None:
            raise AppError(
                code=ERR_DIVINE_ABILITY_LOADOUT,
                message=ERR_DIVINE_ABILITY_LOADOUT_ZH,
                http_status=400,
            )
        target.ability_id = None
        await self._session.flush()
        return await self.get_page(character, actor=actor)
