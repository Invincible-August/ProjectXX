"""
Equipment loadout service (M8 R0 · 17-zone pointer slots).

Wear/unequip gear + pet pointer slots; aggregates stats for combat / idle / dice.
Puppet uses a multi-item loadout board (not a single slot).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.divine_sense import (
    DIVINE_SENSE_ZONE_LABELS_ZH,
    PUPPET_LOADOUT_MAX,
    PUPPET_LOADOUT_MAX_ZH,
    PUPPET_SENSE_HELP_ZH,
)
from app.constants.avatar import (
    ERR_AVATAR_EXISTS_OR_MISSING,
    LOADOUT_ACTOR_AVATAR,
    LOADOUT_ACTOR_MAIN,
    normalize_loadout_actor,
)
from app.constants.equipment import (
    AVATAR_EQUIPMENT_SLOTS,
    AVATAR_FORBIDDEN_EQUIP_SLOTS,
    EQUIPMENT_SLOT_ALIASES,
    EQUIPMENT_SLOT_LABELS_ZH,
    EQUIPMENT_SLOT_PET,
    EQUIPMENT_SLOT_WEAPON_1,
    EQUIPMENT_SLOT_WEAPON_2,
    EQUIPMENT_SLOTS,
    EQUIP_KIND_WEAPON_2H,
    ERR_EQUIP_INVALID,
    WEAPON_POINTER_SLOTS,
    canonical_equipment_slot,
    compatible_pointer_slots,
)
from app.constants.craft import CRAFT_QUALITY_LABEL_ZH
from app.domain.craft_quality import normalize_craft_quality
from app.domain.item_icon import resolve_item_icon
from app.constants.inventory import ITEM_TYPE_EQUIPMENT, ItemType, Occupancy
from app.constants.puppet import PUPPET_DEF_TRIAL_WOOD
from app.db.models.character import Character
from app.db.models.character_equipment import CharacterEquipmentSlot
from app.db.models.avatar_loadout import AvatarEquipmentSlot
from app.db.models.inventory_item import InventoryItem
from app.domain.avatar_rules import major_realm_order
from app.domain.divine_sense import (
    OverloadBand,
    puppet_sense_reading,
    serialize_overload_bands,
)
from app.schemas.common import AppError
from app.services.divine_sense_service import DivineSenseService
from app.services.realm_config import EquipmentItemDef, get_game_config

logger = logging.getLogger(__name__)

_STARTER_EQUIPMENT = (
    "iron_sword_t1",
    "cloth_robe_t1",
    "jade_pendant_t1",
)


def _slot_accepts_def(slot: str, def_slot: str) -> bool:
    """Return True when catalog slot/kind matches the wear pointer."""
    want = canonical_equipment_slot(slot)
    return want in compatible_pointer_slots(def_slot)


def _is_weapon_2h(def_slot: str) -> bool:
    """Return True when catalog kind is a two-handed weapon."""
    return str(def_slot) == EQUIP_KIND_WEAPON_2H


def _pointer_targets(def_slot: str, chosen: str) -> tuple[str, ...]:
    """
    Resolve which pointer rows an equip writes.

    Two-handed weapons always occupy both weapon slots; others write ``chosen``.
    """
    if _is_weapon_2h(def_slot):
        return WEAPON_POINTER_SLOTS
    return (chosen,)


def _realm_meets(required: str | None, character_major: str, realms: dict[str, Any]) -> bool:
    if not required:
        return True
    order = major_realm_order(realms)
    try:
        return order.index(character_major) >= order.index(required)
    except ValueError:
        return True


class EquipmentService:
    """17-zone equipment wear/unequip and aggregation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_avatar(self, character_id: int):
        """Load condensed avatar row or raise."""
        from app.services.avatar_repo import fetch_avatar_row

        avatar = await fetch_avatar_row(self._session, character_id)
        if avatar is None:
            raise AppError(
                code=ERR_AVATAR_EXISTS_OR_MISSING,
                message="尚未凝练化身",
                http_status=400,
            )
        return avatar

    def _slots_for_actor(self, actor: str) -> tuple[str, ...]:
        """Pointer ids this wearer may occupy."""
        if actor == LOADOUT_ACTOR_AVATAR:
            return AVATAR_EQUIPMENT_SLOTS
        return EQUIPMENT_SLOTS

    async def ensure_default_slots(
        self,
        character_id: int,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> None:
        """Create pointer slots; migrate legacy five-slot ids in place."""
        actor = normalize_loadout_actor(actor)
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character_id)
            result = await self._session.execute(
                select(AvatarEquipmentSlot).where(
                    AvatarEquipmentSlot.avatar_id == avatar.id,
                ),
            )
            rows = list(result.scalars().all())
            by_slot = {str(r.slot): r for r in rows}
            for slot in AVATAR_EQUIPMENT_SLOTS:
                if slot not in by_slot:
                    self._session.add(
                        AvatarEquipmentSlot(avatar_id=int(avatar.id), slot=slot),
                    )
            await self._session.flush()
            return

        result = await self._session.execute(
            select(CharacterEquipmentSlot).where(
                CharacterEquipmentSlot.character_id == character_id,
            ),
        )
        rows = list(result.scalars().all())
        by_slot = {str(r.slot): r for r in rows}

        # Rename legacy weapon/armor/fabao → canonical ids
        for legacy, canonical in EQUIPMENT_SLOT_ALIASES.items():
            legacy_row = by_slot.get(legacy)
            if legacy_row is None:
                continue
            target = by_slot.get(canonical)
            if target is None:
                legacy_row.slot = canonical
                by_slot[canonical] = legacy_row
                del by_slot[legacy]
            else:
                if target.inventory_item_id is None and legacy_row.inventory_item_id is not None:
                    target.inventory_item_id = legacy_row.inventory_item_id
                await self._session.delete(legacy_row)
                del by_slot[legacy]

        for slot in EQUIPMENT_SLOTS:
            if slot not in by_slot:
                row = CharacterEquipmentSlot(character_id=character_id, slot=slot)
                self._session.add(row)
                by_slot[slot] = row

        await self._session.flush()

    async def grant_starter_kit(self, character_id: int) -> None:
        """Grant sample equipment for acceptance / GM (not auto-equipped)."""
        from app.services.inventory_service import InventoryService

        inv = InventoryService(self._session)
        for item_id in _STARTER_EQUIPMENT:
            await inv.add_item(
                character_id,
                item_type=ITEM_TYPE_EQUIPMENT,
                item_id=item_id,
                quantity=1,
            )
        logger.info("equipment starter kit granted character_id=%s", character_id)

    async def _equipped_rows(
        self,
        character_id: int,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> list[CharacterEquipmentSlot] | list[AvatarEquipmentSlot]:
        actor = normalize_loadout_actor(actor)
        await self.ensure_default_slots(character_id, actor=actor)
        wanted = self._slots_for_actor(actor)
        if actor == LOADOUT_ACTOR_AVATAR:
            avatar = await self._require_avatar(character_id)
            result = await self._session.execute(
                select(AvatarEquipmentSlot).where(
                    AvatarEquipmentSlot.avatar_id == avatar.id,
                ),
            )
            by_slot = {str(r.slot): r for r in result.scalars().all()}
            ordered: list[AvatarEquipmentSlot] = []
            for slot in wanted:
                row = by_slot.get(slot)
                if row is not None:
                    ordered.append(row)
            return ordered

        result = await self._session.execute(
            select(CharacterEquipmentSlot).where(
                CharacterEquipmentSlot.character_id == character_id,
            ),
        )
        by_slot = {str(r.slot): r for r in result.scalars().all()}
        ordered_main: list[CharacterEquipmentSlot] = []
        for slot in wanted:
            row = by_slot.get(slot)
            if row is not None:
                ordered_main.append(row)
        return ordered_main

    async def _inventory_by_id(self, character_id: int, inv_id: int) -> InventoryItem | None:
        result = await self._session.execute(
            select(InventoryItem).where(
                InventoryItem.id == inv_id,
                InventoryItem.character_id == character_id,
            ).limit(1),
        )
        return result.scalar_one_or_none()

    async def _inventory_by_uid(self, character_id: int, item_uid: str) -> InventoryItem | None:
        result = await self._session.execute(
            select(InventoryItem).where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_uid == item_uid,
            ).limit(1),
        )
        return result.scalar_one_or_none()

    def _equip_def(self, item_id: str) -> EquipmentItemDef | None:
        return get_game_config().equipment.items.get(item_id)

    def _parse_meta(self, inv: InventoryItem | None) -> dict[str, Any]:
        """Parse inventory ``meta_json``; empty dict on missing/invalid JSON."""
        if inv is None:
            return {}
        try:
            raw = json.loads(inv.meta_json or "{}")
        except json.JSONDecodeError:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _equip_rarity_fields(self, inv: InventoryItem | None) -> dict[str, str]:
        """
        Item craft quality → rarity display fields (§0.0.3).

        Workshop writes ``quality`` (gray…red / 粗糙～太古) into meta;
        legacy common/fine/rare/superb are normalized. Missing → 普通.
        """
        meta = self._parse_meta(inv)
        qid = normalize_craft_quality(str(meta.get("quality") or ""))
        return {
            "rarity": qid,
            "rarity_label_zh": CRAFT_QUALITY_LABEL_ZH.get(qid, qid),
        }

    def _item_icon(self, item_id: str) -> str:
        """§0.0.4 icon key: equipment.yaml overrides inventory.yaml; else def id."""
        cfg = get_game_config()
        eq = cfg.equipment.items.get(item_id)
        inv = cfg.inventory.items.get(item_id)
        if eq is not None and str(eq.icon or "").strip():
            return str(eq.icon)
        if inv is not None and str(inv.icon or "").strip():
            return str(inv.icon)
        return resolve_item_icon(None, item_id)

    def _stats_preview(self, eq: EquipmentItemDef | None) -> dict[str, Any]:
        """Build player-facing stat lines; never expose raw attr ids."""
        if eq is None:
            return {}
        cfg = get_game_config()
        preview: dict[str, Any] = {}
        for key, val in eq.stats.items():
            attr = cfg.combat_attrs.attrs.get(key)
            label = attr.label_zh if attr else "未知"
            preview[key] = {"label_zh": label, "value": val}
        return preview

    async def _equipped_inventory_ids(
        self,
        character_id: int,
        *,
        actor: str | None = None,
    ) -> set[int]:
        """Worn inventory ids; omit actor to union 本体+化身."""
        if actor is None:
            main_ids = await self._equipped_inventory_ids(
                character_id,
                actor=LOADOUT_ACTOR_MAIN,
            )
            try:
                avatar_ids = await self._equipped_inventory_ids(
                    character_id,
                    actor=LOADOUT_ACTOR_AVATAR,
                )
            except AppError:
                avatar_ids = set()
            return main_ids | avatar_ids
        rows = await self._equipped_rows(character_id, actor=actor)
        return {int(r.inventory_item_id) for r in rows if r.inventory_item_id is not None}

    def _rows_by_slot(
        self,
        rows: list[Any],
    ) -> dict[str, Any]:
        """Index wear rows by slot id."""
        return {str(r.slot): r for r in rows}

    def _clear_weapon_pair(self, by_slot: dict[str, Any]) -> None:
        """Clear both weapon pointer slots."""
        for slot_id in WEAPON_POINTER_SLOTS:
            row = by_slot.get(slot_id)
            if row is not None:
                row.inventory_item_id = None

    def _weapon_pair_shares_id(
        self,
        by_slot: dict[str, Any],
        inv_id: int | None = None,
    ) -> bool:
        """True when both hands point at the same inventory row (2h wear)."""
        w1 = by_slot.get(EQUIPMENT_SLOT_WEAPON_1)
        w2 = by_slot.get(EQUIPMENT_SLOT_WEAPON_2)
        if w1 is None or w2 is None:
            return False
        if w1.inventory_item_id is None or w2.inventory_item_id is None:
            return False
        if int(w1.inventory_item_id) != int(w2.inventory_item_id):
            return False
        if inv_id is not None and int(w1.inventory_item_id) != int(inv_id):
            return False
        return True

    async def list_bag_equipment(self, character_id: int) -> list[dict[str, Any]]:
        """Unequipped equipment (and idle pets) for UI backpack."""
        equipped_ids = await self._equipped_inventory_ids(character_id)
        result = await self._session.execute(
            select(InventoryItem).where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_type.in_((ITEM_TYPE_EQUIPMENT, ItemType.PET)),
            ).order_by(InventoryItem.item_type, InventoryItem.item_id),
        )
        items: list[dict[str, Any]] = []
        inv_cfg = get_game_config().inventory
        eq_cfg = get_game_config().equipment
        for row in result.scalars().all():
            if int(row.id) in equipped_ids:
                continue
            defn = inv_cfg.items.get(row.item_id)
            eq = eq_cfg.items.get(row.item_id)
            if row.item_type == ItemType.PET:
                hint = EQUIPMENT_SLOT_PET
                meta: dict[str, Any] = {}
                try:
                    meta = json.loads(row.meta_json or "{}")
                except json.JSONDecodeError:
                    meta = {}
                name = str(meta.get("nickname") or "") or (defn.name if defn else row.item_id)
                preview: dict[str, Any] = {}
            else:
                hint = eq.slot if eq else None
                name = eq.label_zh if eq else (defn.name if defn else row.item_id)
                preview = self._stats_preview(eq)
            row_body: dict[str, Any] = {
                "item_uid": row.item_uid,
                "item_id": row.item_id,
                "name": name,
                "slot_hint": hint,
                "compatible_slots": list(compatible_pointer_slots(hint or "")),
                "stats_preview": preview,
                "quantity": int(row.quantity),
                "item_type": row.item_type,
                "icon": self._item_icon(str(row.item_id)),
            }
            if row.item_type != ItemType.PET:
                row_body.update(self._equip_rarity_fields(row))
            items.append(row_body)
        return items

    async def list_puppet_rows(self, character_id: int) -> list[InventoryItem]:
        """All puppet inventory rows for the character."""
        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_type == ItemType.PUPPET,
            )
            .order_by(InventoryItem.item_id, InventoryItem.id),
        )
        return list(result.scalars().all())

    def _puppet_cost(self, row: InventoryItem) -> tuple[int, bool]:
        """
        Per-puppet divine-sense cost and whether it feeds load_puppet.

        Trial wood templates do not count (M4 §6.4). Missing YAML cost defaults
        to DivineSenseConfig.cost_puppet.
        """
        cfg = get_game_config()
        defn = cfg.inventory.items.get(str(row.item_id))
        actor_id = defn.actor_def_id if defn and defn.actor_def_id else str(row.item_id)
        if actor_id == PUPPET_DEF_TRIAL_WOOD:
            return 0, False
        return int(cfg.divine_sense.cost_puppet), True

    def _puppet_loadout_max(self) -> int:
        """Deployed puppet hard cap (YAML, default PUPPET_LOADOUT_MAX)."""
        cfg = get_game_config().divine_sense
        raw = int(getattr(cfg, "puppet_loadout_max", PUPPET_LOADOUT_MAX) or PUPPET_LOADOUT_MAX)
        return max(1, raw)

    def _puppet_public(self, row: InventoryItem, occupancy: str) -> dict[str, Any]:
        """Serialize a puppet inventory row for loadout / bag lists."""
        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(str(row.item_id))
        cost, counts = self._puppet_cost(row)
        return {
            "inventory_item_id": int(row.id),
            "item_uid": row.item_uid,
            "item_id": row.item_id,
            "label_zh": defn.name if defn else row.item_id,
            "occupancy": occupancy,
            "divine_sense_cost": cost,
            "counts_toward_load": counts,
        }

    def _puppet_sense_payload(
        self,
        character: Character,
        loadout: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Saved-loadout puppet sense reading + bands for live client preview."""
        cfg = get_game_config().divine_sense
        pool = DivineSenseService.snapshot_for_character(
            character,
            avatar_deploy_count=0,
            pet_deploy_count=0,
        )
        load = sum(
            int(p.get("divine_sense_cost") or 0)
            for p in loadout
            if p.get("counts_toward_load", True)
        )
        bands = [
            OverloadBand(
                max_load_ratio=b.max_load_ratio,
                combat_stat_mult=b.combat_stat_mult,
                zone=b.zone,
            )
            for b in cfg.overload_bands
        ]
        capacity = int(pool["capacity"])
        reading = puppet_sense_reading(
            load=load,
            capacity=capacity,
            soft_cap=capacity,
            hard_cap=int(pool["hard_cap"]),
            bands=bands,
            fallback_stat_mult=cfg.overload_stat_mult,
            zone_labels=DIVINE_SENSE_ZONE_LABELS_ZH,
        )
        reading["default_cost"] = int(cfg.cost_puppet)
        reading["max_count"] = self._puppet_loadout_max()
        reading["help_zh"] = PUPPET_SENSE_HELP_ZH
        reading["bands"] = serialize_overload_bands(
            bands,
            zone_labels=DIVINE_SENSE_ZONE_LABELS_ZH,
        )
        return reading

    async def list_puppet_loadout(
        self,
        character_id: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Split puppets into deployed loadout vs idle bag.

        Returns:
            tuple: (puppet_loadout, bag_puppets)
        """
        from app.services.inventory_service import InventoryService

        inv_svc = InventoryService(self._session)
        loadout: list[dict[str, Any]] = []
        bag: list[dict[str, Any]] = []
        for row in await self.list_puppet_rows(character_id):
            occupancy = inv_svc.read_meta_occupancy(row)
            entry = self._puppet_public(row, occupancy)
            if occupancy == Occupancy.DEPLOYED:
                loadout.append(entry)
            else:
                bag.append(entry)
        return loadout, bag

    async def add_puppet_to_loadout(self, character: Character, *, item_uid: str) -> dict[str, Any]:
        """Mark a puppet inventory row as deployed (count hard-cap from YAML)."""
        from app.services.inventory_service import InventoryService

        inv = await self._inventory_by_uid(character.id, item_uid)
        if inv is None or inv.item_type != ItemType.PUPPET:
            raise AppError(ERR_EQUIP_INVALID, "只能将傀儡加入编成板", http_status=400)
        if int(inv.quantity) < 1:
            raise AppError(ERR_EQUIP_INVALID, "只能将傀儡加入编成板", http_status=400)
        inv_svc = InventoryService(self._session)
        occupancy = inv_svc.read_meta_occupancy(inv)
        if occupancy != Occupancy.DEPLOYED:
            loadout, _bag = await self.list_puppet_loadout(character.id)
            if len(loadout) >= self._puppet_loadout_max():
                raise AppError(ERR_EQUIP_INVALID, PUPPET_LOADOUT_MAX_ZH, http_status=400)
        await inv_svc.set_occupancy(inv, Occupancy.DEPLOYED)
        logger.info(
            "puppet loadout add character_id=%s item_uid=%s",
            character.id,
            item_uid,
        )
        return await self.get_slots_state(character)

    async def remove_puppet_from_loadout(
        self,
        character: Character,
        *,
        item_uid: str,
    ) -> dict[str, Any]:
        """Clear puppet deployed occupancy back to idle."""
        from app.services.inventory_service import InventoryService

        inv = await self._inventory_by_uid(character.id, item_uid)
        if inv is None or inv.item_type != ItemType.PUPPET:
            raise AppError(ERR_EQUIP_INVALID, "编成板上无此傀儡", http_status=400)
        inv_svc = InventoryService(self._session)
        await inv_svc.set_occupancy(inv, Occupancy.NONE)
        logger.info(
            "puppet loadout remove character_id=%s item_uid=%s",
            character.id,
            item_uid,
        )
        return await self.get_slots_state(character)

    async def replace_puppet_loadout(
        self,
        character: Character,
        *,
        item_uids: list[str],
    ) -> dict[str, Any]:
        """
        Replace the deployed puppet set in one write.

        Does not reject for divine-sense overload (M4 §6.4). Duplicate uids
        collapse; empty list clears the board.
        """
        from app.services.inventory_service import InventoryService

        wanted: list[str] = []
        seen: set[str] = set()
        for raw in item_uids:
            uid = str(raw or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            wanted.append(uid)

        if len(wanted) > self._puppet_loadout_max():
            raise AppError(ERR_EQUIP_INVALID, PUPPET_LOADOUT_MAX_ZH, http_status=400)

        inv_svc = InventoryService(self._session)
        rows = await self.list_puppet_rows(character.id)
        by_uid = {str(row.item_uid): row for row in rows}
        for uid in wanted:
            inv = by_uid.get(uid)
            if inv is None or int(inv.quantity) < 1:
                raise AppError(ERR_EQUIP_INVALID, "编成板上无此傀儡", http_status=400)
        wanted_set = set(wanted)
        for row in rows:
            occupancy = Occupancy.DEPLOYED if str(row.item_uid) in wanted_set else Occupancy.NONE
            await inv_svc.set_occupancy(row, occupancy)
        logger.info(
            "puppet loadout replace character_id=%s count=%s",
            character.id,
            len(wanted),
        )
        return await self.get_slots_state(character)

    async def _avatar_deploy_payload(self, character: Character) -> dict[str, Any]:
        """装备栏化身上阵开关（不占17区槽，只耗神识）。"""
        from app.db.models.avatar import Avatar

        cfg = get_game_config().divine_sense
        result = await self._session.execute(
            select(Avatar).where(Avatar.character_id == character.id).limit(1),
        )
        avatar = result.scalar_one_or_none()
        if avatar is None:
            return {
                "has_avatar": False,
                "deployed": False,
                "name": None,
                "cost": int(cfg.cost_avatar),
                "help_zh": "凝练化身后可在此选择是否上阵；上阵即占神识，并进入阵法可上场列表。",
            }
        return {
            "has_avatar": True,
            "deployed": int(getattr(avatar, "is_deployed", 0) or 0) == 1,
            "name": avatar.name,
            "cost": int(cfg.cost_avatar),
            "status": avatar.status,
            "help_zh": "打开则化身占用神识并出现在阵法配置列表；关闭则不占神识、不可上场。",
        }

    async def set_avatar_deployed(self, character: Character, *, deployed: bool) -> dict[str, Any]:
        """Toggle whether the condensed avatar counts toward sense and formation bench."""
        from app.db.models.avatar import Avatar

        result = await self._session.execute(
            select(Avatar).where(Avatar.character_id == character.id).limit(1),
        )
        avatar = result.scalar_one_or_none()
        if avatar is None:
            raise AppError(40051, "尚未凝练化身", http_status=400)
        avatar.is_deployed = 1 if deployed else 0
        await self._session.flush()
        logger.info(
            "avatar deploy toggle character_id=%s deployed=%s",
            character.id,
            deployed,
        )
        return await self.get_slots_state(character)

    async def _talisman_payload(self, character: Character) -> dict[str, Any]:
        """Reuse CharacterTalismanLoadout; unlimited count when preload_slots<=0."""
        from app.constants.inventory import Occupancy
        from app.services.craft_service import CraftService
        from app.services.inventory_service import InventoryService

        craft = CraftService(self._session)
        inv_svc = InventoryService(self._session)
        listed = await craft.list_talisman_preload(character)
        loadout = listed.get("slots") or []
        deployed_ids = {int(s["inventory_item_id"]) for s in loadout}
        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character.id,
                InventoryItem.item_type == ItemType.TALISMAN,
            )
            .order_by(InventoryItem.id),
        )
        bag: list[dict[str, Any]] = []
        for row in result.scalars().all():
            if int(row.quantity) < 1:
                continue
            if int(row.id) in deployed_ids:
                continue
            occupancy = inv_svc.read_meta_occupancy(row)
            meta: dict[str, Any] = {}
            try:
                meta = json.loads(row.meta_json or "{}")
            except json.JSONDecodeError:
                meta = {}
            bag.append(
                {
                    "inventory_item_id": int(row.id),
                    "item_uid": row.item_uid,
                    "item_id": row.item_id,
                    "label_zh": meta.get("label_zh") or row.item_id,
                    "effect_id": meta.get("effect_id"),
                    "quantity": int(row.quantity),
                    "occupancy": occupancy,
                },
            )
        for slot in loadout:
            inv = await self._session.get(InventoryItem, int(slot["inventory_item_id"]))
            slot["item_uid"] = inv.item_uid if inv is not None else None
        return {
            "talisman_loadout": loadout,
            "bag_talismans": bag,
            "talisman_loadout_note_zh": "加入战斗的符箓无件数上限；同种类战斗中不叠加，取最高效果，低效果符仍会消耗。",
            "max_slots": int(listed.get("max_slots") or 0),
        }

    async def replace_talisman_loadout(
        self,
        character: Character,
        *,
        inventory_item_ids: list[int] | None = None,
        item_uids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Save equipped talismans (same table as workshop preload)."""
        from app.services.craft_service import CraftService

        ids: list[int] = list(inventory_item_ids or [])
        if item_uids:
            result = await self._session.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.item_type == ItemType.TALISMAN,
                ),
            )
            by_uid = {str(row.item_uid): int(row.id) for row in result.scalars().all()}
            for uid in item_uids:
                inv_id = by_uid.get(str(uid))
                if inv_id is None:
                    raise AppError(ERR_EQUIP_INVALID, "编成板上无此符箓", http_status=400)
                ids.append(inv_id)
        await CraftService(self._session).set_talisman_preload(character, ids)
        return await self.get_slots_state(character)

    def _slot_public(
        self,
        slot: str,
        inv: InventoryItem | None,
        *,
        channels: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = get_game_config()
        combat_channel = cfg.combat_attrs.channels.get("equipment") or {}
        enabled = bool(combat_channel.get("enabled", False))
        occupancy = (
            Occupancy.DEPLOYED if slot == EQUIPMENT_SLOT_PET else Occupancy.EQUIPPED
        )
        body: dict[str, Any] = {
            "slot": slot,
            "slot_label_zh": EQUIPMENT_SLOT_LABELS_ZH.get(slot, slot),
            "item_uid": None,
            "item_id": None,
            "item_label_zh": None,
            "stats_preview": {},
            "channel_enabled": enabled,
            "channel_label_zh": str(combat_channel.get("label_zh") or "装备"),
            "occupancy": occupancy,
        }
        if inv is None:
            return body
        if slot == EQUIPMENT_SLOT_PET:
            inv_cfg = get_game_config().inventory
            defn = inv_cfg.items.get(str(inv.item_id))
            meta = self._parse_meta(inv)
            label = (
                str(meta.get("nickname") or "")
                or (defn.name if defn else "")
                or str(meta.get("species_id") or inv.item_id)
            )
            body.update(
                {
                    "item_uid": inv.item_uid,
                    "item_id": inv.item_id,
                    "item_label_zh": label,
                    "pet_id": meta.get("pet_id"),
                    "icon": self._item_icon(str(inv.item_id)),
                },
            )
            return body
        eq = self._equip_def(str(inv.item_id))
        if eq is None:
            return body
        body.update(
            {
                "item_uid": inv.item_uid,
                "item_id": inv.item_id,
                "item_label_zh": eq.label_zh,
                "stats_preview": self._stats_preview(eq),
                "icon": self._item_icon(str(inv.item_id)),
                **self._equip_rarity_fields(inv),
            },
        )
        return body

    async def get_slots_state(
        self,
        character: Character,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """Full slots payload for GET /equipment/slots."""
        actor = normalize_loadout_actor(actor)
        cfg = get_game_config()
        rows = await self._equipped_rows(character.id, actor=actor)
        slots: list[dict[str, Any]] = []
        for row in rows:
            inv = None
            if row.inventory_item_id is not None:
                inv = await self._inventory_by_id(character.id, int(row.inventory_item_id))
            slots.append(
                self._slot_public(str(row.slot), inv, channels=cfg.combat_attrs.channels),
            )
        combat_ch = cfg.combat_attrs.channels.get("equipment") or {}
        idle_ch = cfg.idle.bonus_channels.get("equipment_idle")
        dice_ch = cfg.dice.bonus_channels.get("equipment")
        puppet_loadout, bag_puppets = await self.list_puppet_loadout(character.id)
        from app.services.pet_service import PetService

        await PetService(self._session).ensure_all_inventory_faces(character.id)
        talisman = await self._talisman_payload(character)
        return {
            "slots": slots,
            "bag_equipment": await self.list_bag_equipment(character.id),
            "puppet_loadout": puppet_loadout,
            "bag_puppets": bag_puppets,
            "puppet_loadout_note_zh": "傀儡走编成板（多只），不占单槽；双手武器占主副手两格",
            "puppet_sense": self._puppet_sense_payload(character, puppet_loadout),
            "avatar_deploy": await self._avatar_deploy_payload(character),
            **talisman,
            "channels": {
                "combat_equipment": {
                    "enabled": bool(combat_ch.get("enabled", False)),
                    "label_zh": str(combat_ch.get("label_zh") or "装备"),
                },
                "idle_equipment": {
                    "enabled": bool(idle_ch.enabled) if idle_ch else False,
                    "label_zh": "装备",
                },
                "dice_equipment": {
                    "enabled": bool(dice_ch.enabled) if dice_ch else False,
                    "label_zh": "装备",
                },
            },
        }

    async def aggregate_equipped_modifiers(
        self,
        character_id: int,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> tuple[dict[str, float], float, int, int]:
        """
        Sum combat stats, idle mult product, dice min/max from worn equipment.

        Deduplicates by inventory_item_id so two-handed dual pointers count once.

        Returns:
            tuple: (stats, idle_mult_product, dice_min_bonus, dice_max_bonus)
        """
        rows = await self._equipped_rows(character_id, actor=actor)
        stats: dict[str, float] = {}
        idle_product = 1.0
        idle_any = False
        dice_min = 0
        dice_max = 0
        seen_inv: set[int] = set()
        for row in rows:
            if row.inventory_item_id is None:
                continue
            if str(row.slot) == EQUIPMENT_SLOT_PET:
                continue
            inv_id = int(row.inventory_item_id)
            if inv_id in seen_inv:
                continue
            seen_inv.add(inv_id)
            inv = await self._inventory_by_id(character_id, inv_id)
            if inv is None:
                continue
            eq = self._equip_def(str(inv.item_id))
            if eq is None:
                continue
            for key, val in eq.stats.items():
                stats[key] = stats.get(key, 0.0) + float(val)
            im = eq.idle_mods.get("idle_mult")
            if im is not None and float(im) != 1.0:
                idle_any = True
                idle_product *= float(im)
            dice_min += int(eq.dice_mods.get("min_bonus", 0) or 0)
            dice_max += int(eq.dice_mods.get("max_bonus", 0) or 0)
        if not idle_any:
            idle_product = 1.0
        return stats, idle_product, dice_min, dice_max

    async def equip_item(
        self,
        character: Character,
        *,
        slot: str,
        item_uid: str,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """Wear inventory equipment or pet into a pointer slot."""
        actor = normalize_loadout_actor(actor)
        slot = canonical_equipment_slot(slot)
        allowed_slots = self._slots_for_actor(actor)
        if slot not in allowed_slots:
            raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
        if actor == LOADOUT_ACTOR_AVATAR and slot in AVATAR_FORBIDDEN_EQUIP_SLOTS:
            raise AppError(ERR_EQUIP_INVALID, "化身不能装备该部位", http_status=400)
        inv = await self._inventory_by_uid(character.id, item_uid)
        if inv is None:
            raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
        if int(inv.quantity) < 1:
            raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)

        eq: EquipmentItemDef | None = None
        if slot == EQUIPMENT_SLOT_PET:
            if actor == LOADOUT_ACTOR_AVATAR:
                raise AppError(ERR_EQUIP_INVALID, "化身不能装备灵宠", http_status=400)
            if inv.item_type != ItemType.PET:
                raise AppError(ERR_EQUIP_INVALID, "灵宠槽只能装入灵宠", http_status=400)
        else:
            if inv.item_type != ITEM_TYPE_EQUIPMENT:
                raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
            eq = self._equip_def(str(inv.item_id))
            if eq is None:
                raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
            if not _slot_accepts_def(slot, eq.slot):
                raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
            bundle = get_game_config()
            realm_major = str(character.major_realm)
            if actor == LOADOUT_ACTOR_AVATAR:
                avatar = await self._require_avatar(character.id)
                realm_major = str(avatar.major_realm)
            if not _realm_meets(
                eq.required_major_realm,
                realm_major,
                bundle.realms,
            ):
                raise AppError(ERR_EQUIP_INVALID, "境界不足", http_status=400)

        equipped_ids = await self._equipped_inventory_ids(character.id)
        if int(inv.id) in equipped_ids:
            raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
        rows = await self._equipped_rows(character.id, actor=actor)
        by_slot = self._rows_by_slot(rows)

        if eq is not None and _is_weapon_2h(eq.slot):
            self._clear_weapon_pair(by_slot)
            for target_slot in _pointer_targets(eq.slot, slot):
                target = by_slot.get(target_slot)
                if target is None:
                    raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
                target.inventory_item_id = int(inv.id)
        else:
            # 1h into a hand that shares a 2h id: clear both first
            if slot in WEAPON_POINTER_SLOTS and self._weapon_pair_shares_id(by_slot):
                self._clear_weapon_pair(by_slot)
            target = by_slot.get(slot)
            if target is None:
                raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
            target.inventory_item_id = int(inv.id)

        await self._session.flush()
        logger.info(
            "equipment equip character_id=%s actor=%s slot=%s item_uid=%s",
            character.id,
            actor,
            slot,
            item_uid,
        )
        return await self.get_slots_state(character, actor=actor)

    async def unequip_slot(
        self,
        character: Character,
        *,
        slot: str,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """Remove equipment from slot back to bag (2h clears both hands)."""
        actor = normalize_loadout_actor(actor)
        slot = canonical_equipment_slot(slot)
        if slot not in self._slots_for_actor(actor):
            raise AppError(ERR_EQUIP_INVALID, "该灵物无法装入此槽", http_status=400)
        rows = await self._equipped_rows(character.id, actor=actor)
        by_slot = self._rows_by_slot(rows)
        target = by_slot.get(slot)
        if target is None or target.inventory_item_id is None:
            return await self.get_slots_state(character, actor=actor)

        inv_id = int(target.inventory_item_id)
        if slot in WEAPON_POINTER_SLOTS and self._weapon_pair_shares_id(by_slot, inv_id):
            self._clear_weapon_pair(by_slot)
        else:
            target.inventory_item_id = None

        await self._session.flush()
        logger.info(
            "equipment unequip character_id=%s actor=%s slot=%s",
            character.id,
            actor,
            slot,
        )
        return await self.get_slots_state(character, actor=actor)

    async def unequip_all_avatar(self, character_id: int) -> int:
        """Clear all avatar wear pointers so items return to the shared bag."""
        from app.services.avatar_repo import fetch_avatar_row

        avatar = await fetch_avatar_row(self._session, character_id)
        if avatar is None:
            return 0
        result = await self._session.execute(
            select(AvatarEquipmentSlot).where(
                AvatarEquipmentSlot.avatar_id == avatar.id,
            ),
        )
        cleared = 0
        for row in result.scalars().all():
            if row.inventory_item_id is not None:
                row.inventory_item_id = None
                cleared += 1
        await self._session.flush()
        return cleared

    async def get_catalog(self) -> list[dict[str, Any]]:
        """Read-only official equipment catalog."""
        cfg = get_game_config()
        out: list[dict[str, Any]] = []
        for item_id, eq in cfg.equipment.items.items():
            out.append(
                {
                    "item_id": item_id,
                    "label_zh": eq.label_zh,
                    "help_zh": eq.help_zh,
                    "slot": eq.slot,
                    "stats": eq.stats,
                    "required_major_realm": eq.required_major_realm,
                },
            )
        return out


def parse_puppet_combat_stats(meta_json: str | None) -> dict[str, float]:
    """Read puppet cultivation stats from Actor.meta_json."""
    if not meta_json:
        return {}
    try:
        meta = json.loads(meta_json)
    except json.JSONDecodeError:
        return {}
    raw = meta.get("combat_stats") or meta.get("stats") or {}
    if not isinstance(raw, dict):
        return {}
    cfg = get_game_config().combat_attrs
    stats: dict[str, float] = {}
    for key, val in raw.items():
        sk = str(key)
        if sk in cfg.attrs:
            stats[sk] = float(val)
    return stats
