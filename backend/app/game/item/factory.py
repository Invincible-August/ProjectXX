"""Dispatch inventory rows onto Item subclasses (M8 R0)."""

from __future__ import annotations

from typing import Any

from app.constants.inventory import ItemType, Occupancy
from app.game.item.types import (
    ConsumableItem,
    EquipmentItem,
    GenericItem,
    ManualItem,
    MaterialItem,
    PetEggItem,
    PetItem,
    PuppetItem,
    TalismanItem,
)

_TYPE_MAP: dict[str, type[GenericItem]] = {
    ItemType.MATERIAL: MaterialItem,
    ItemType.CONSUMABLE: ConsumableItem,
    ItemType.EQUIPMENT: EquipmentItem,
    ItemType.TALISMAN: TalismanItem,
    ItemType.MANUAL: ManualItem,
    ItemType.SKILL_BOOK: ManualItem,
    ItemType.PUPPET: PuppetItem,
    ItemType.PET_EGG: PetEggItem,
    ItemType.PET: PetItem,
}


def _raw_from_def(defn: Any, fallback_type: str) -> dict[str, Any]:
    if defn is None:
        return {"item_type": fallback_type}
    if isinstance(defn, dict):
        raw = dict(defn)
        raw.setdefault("item_type", fallback_type)
        return raw
    return {
        "item_type": str(getattr(defn, "item_type", None) or fallback_type),
        "name": getattr(defn, "name", None),
        "label_zh": getattr(defn, "label_zh", None),
        "max_stack": getattr(defn, "max_stack", None),
        "tradable": getattr(defn, "tradable", True),
        "bound": getattr(defn, "bound", False),
        "unique": getattr(defn, "unique", False),
        "use_effect": getattr(defn, "use_effect", None),
        "actor_def_id": getattr(defn, "actor_def_id", None),
        "slot": getattr(defn, "slot", None),
        "stats": getattr(defn, "stats", None),
        "grants": getattr(defn, "grants", None),
        "manual_kind": getattr(defn, "manual_kind", None),
        "unlock_recipe_id": getattr(defn, "unlock_recipe_id", None),
        "talisman_effect_id": getattr(defn, "talisman_effect_id", None),
    }


def item_from_mapping(
    def_id: str,
    raw: dict[str, Any] | None = None,
    *,
    instance_uid: str | None = None,
    occupancy: str = Occupancy.NONE,
    quantity: int = 1,
) -> GenericItem:
    """Build an Item from a definition mapping (tests / factory)."""
    body = dict(raw or {})
    item_kind = str(body.get("item_type") or "material")
    cls = _TYPE_MAP.get(item_kind, GenericItem)
    kwargs: dict[str, Any] = {
        "def_id": def_id,
        "raw": body,
        "instance_uid": instance_uid,
        "occupancy": occupancy,
        "quantity": quantity,
        "label_zh": body.get("name") or body.get("label_zh"),
    }
    if cls in (EquipmentItem, PuppetItem):
        return cls(**kwargs)
    kwargs["item_kind"] = item_kind
    return cls(**kwargs)


def item_from_inventory_row(
    row: Any,
    defn: Any = None,
    *,
    occupancy: str = Occupancy.NONE,
) -> GenericItem:
    """Build an Item from an InventoryItem ORM row plus catalog def."""
    item_type = str(getattr(row, "item_type", None) or "material")
    item_id = str(getattr(row, "item_id", None) or "")
    raw = _raw_from_def(defn, item_type)
    raw.setdefault("item_type", item_type)
    return item_from_mapping(
        item_id,
        raw,
        instance_uid=str(getattr(row, "item_uid", None) or item_id),
        occupancy=occupancy,
        quantity=int(getattr(row, "quantity", 1) or 1),
    )
