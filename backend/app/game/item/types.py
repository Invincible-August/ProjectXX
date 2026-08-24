"""Generic item fallback and typed subclasses (M8 R0)."""

from __future__ import annotations

from typing import Any

from app.constants.inventory import (
    ERR_ITEM_OCCUPIED,
    ERR_ITEM_USE_EFFECT,
    Occupancy,
)
from app.game.ability import SimpleGrantSource
from app.game.ability.grant import GrantSource
from app.game.item.base import Item
from app.game.item.use_effect import UseEffectError, validate_use_effect
from app.schemas.common import AppError


class GenericItem(Item):
    """通用道具门面（未知类型回退）。"""

    def get_item_kind(self) -> str:
        return self._item_kind

    def as_grant_source(self) -> GrantSource | None:
        grants = self._raw.get("grants") or []
        if not grants:
            return None
        return SimpleGrantSource(
            source_type=self._item_kind,
            source_id=self._def_id,
            ability_ids=[str(x) for x in grants],
        )


class MaterialItem(GenericItem):
    """材料。"""

    kind = "material"


class ConsumableItem(GenericItem):
    """丹药及其它消耗品。"""

    kind = "consumable"

    def on_use(self, ctx: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Validate whitelist; refuse occupied / illegal / unsettled timed pills."""
        del ctx
        if self.get_occupancy() != Occupancy.NONE:
            raise AppError(code=ERR_ITEM_OCCUPIED, message="占用中的物品不可使用", http_status=400)
        raw = self._raw.get("use_effect")
        try:
            effects = validate_use_effect(raw)
        except UseEffectError as exc:
            raise AppError(code=ERR_ITEM_USE_EFFECT, message=str(exc), http_status=400) from exc
        if not effects:
            raise AppError(code=ERR_ITEM_USE_EFFECT, message="该物品不可使用", http_status=400)
        if any(not bool(row.get("instant")) for row in effects):
            raise AppError(
                code=ERR_ITEM_USE_EFFECT,
                message="时效丹结算尚未开放",
                http_status=400,
            )
        return {"effects": effects, "consume": True}


class EquipmentItem(GenericItem):
    """装备（ATTR-D02 / R0 工厂）。"""

    kind = "equipment"

    def __init__(self, *, def_id: str, raw: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(def_id=def_id, item_kind="equipment", raw=raw, **kwargs)

    @property
    def slot(self) -> str | None:
        return self._raw.get("slot") or self._raw.get("equip_kind")

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._raw.get("stats") or {})

    @property
    def set_id(self) -> str | None:
        return self._raw.get("set_id")

    def equip_slot(self) -> str | None:
        return self.slot


class TalismanItem(GenericItem):
    """符箓成品。"""

    kind = "talisman"


class ManualItem(GenericItem):
    """秘籍（包内物；配方正文归 Content）。"""

    kind = "manual"

    @property
    def manual_kind(self) -> str:
        """图纸细类：forge_blueprint / alchemy_formula / …"""
        return str(self._raw.get("manual_kind") or "")

    @property
    def unlock_recipe_id(self) -> str:
        """关联工坊配方 id（学习完式延后 M8-D06）。"""
        return str(self._raw.get("unlock_recipe_id") or "")


class PuppetItem(GenericItem):
    """傀儡背包面；``actor_def_id`` 指向战斗模板。"""

    kind = "puppet"

    def __init__(self, *, def_id: str, raw: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(def_id=def_id, item_kind="puppet", raw=raw, **kwargs)

    @property
    def actor_def_id(self) -> str:
        return str(self._raw.get("actor_def_id") or self._def_id)

    def as_actor_ref(self) -> str:
        return self.actor_def_id


class PetEggItem(GenericItem):
    """灵宠蛋。"""

    kind = "pet_egg"


class PetItem(GenericItem):
    """孵化后的灵宠背包面。"""

    kind = "pet"
