"""道具抽象基类（M8 R0）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.constants.inventory import Occupancy, bag_tab_for
from app.domain.item_icon import resolve_item_icon
from app.game.ability.grant import GrantSource
from app.game.item.laws import can_stack_with as laws_can_stack_with
from app.game.item.laws import can_trade as laws_can_trade


class Item(ABC):
    """背包/装配物契约。"""

    kind: str = "item"

    def __init__(
        self,
        *,
        def_id: str,
        item_kind: str,
        raw: dict[str, Any] | None = None,
        instance_uid: str | None = None,
        occupancy: str = Occupancy.NONE,
        quantity: int = 1,
        label_zh: str | None = None,
    ) -> None:
        self._def_id = def_id
        self._item_kind = item_kind
        self._raw = dict(raw or {})
        self.instance_uid = instance_uid or def_id
        self._occupancy = str(occupancy or Occupancy.NONE)
        self.quantity = int(quantity)
        self.label_zh = label_zh or str(self._raw.get("name") or self._raw.get("label_zh") or def_id)

    @abstractmethod
    def get_item_kind(self) -> str:
        """inventory item_type：material/equipment/puppet/…"""

    def get_def_id(self) -> str:
        """配置定义 id。"""
        return self._def_id

    def get_icon(self) -> str:
        """UI icon key (§0.0.4); defaults to def_id when catalog omits icon."""
        return resolve_item_icon(
            str(self._raw.get("icon") or self._raw.get("ui_key") or "") or None,
            self._def_id,
        )

    def get_stack_rules(self) -> dict[str, Any]:
        """绑定 / 唯一 / 可出售 / 堆叠摘要。"""
        return {
            "bound": bool(self._raw.get("bound", False)),
            "unique": bool(self._raw.get("unique", False)),
            "tradable": bool(self._raw.get("tradable", True)),
            "max_stack": int(self._raw.get("max_stack") or 1),
            "quantity": self.quantity,
        }

    def get_occupancy(self) -> str:
        """none / equipped / deployed."""
        return self._occupancy

    def get_bag_tab(self) -> str:
        """Four-tab bag page from item_type."""
        return bag_tab_for(self.get_item_kind())

    def as_grant_source(self) -> GrantSource | None:
        """可授予 Ability 时返回源；默认无。"""
        return None

    def on_use(self, ctx: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """消耗品使用钩子；默认不支持。"""
        return None

    def as_actor_ref(self) -> int | str | None:
        """傀儡 / 灵宠 Actor 主键；默认无。"""
        return None

    def equip_slot(self) -> str | tuple[str, ...] | None:
        """穿戴栏槽；非装备为空。"""
        return None

    def can_trade(self) -> bool:
        """四法则：可交易。"""
        return laws_can_trade(self)

    def can_stack_with(self, other: Item) -> bool:
        """四法则：可与另一行堆叠。"""
        return laws_can_stack_with(self, other)
