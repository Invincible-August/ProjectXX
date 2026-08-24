"""Four stack/trade laws shared by Item subclasses (M8 R0)."""

from __future__ import annotations

from typing import Any

from app.constants.inventory import Occupancy


def _rules(item: Any) -> dict[str, Any]:
    return dict(item.get_stack_rules() or {})


def _occupancy(item: Any) -> str:
    getter = getattr(item, "get_occupancy", None)
    if callable(getter):
        return str(getter() or Occupancy.NONE)
    return str(getattr(item, "_occupancy", Occupancy.NONE) or Occupancy.NONE)


def can_trade(item: Any) -> bool:
    """Tradable and unbound and not occupied."""
    rules = _rules(item)
    tradable = bool(rules.get("tradable", True))
    bound = bool(rules.get("bound", False))
    return tradable and not bound and _occupancy(item) == Occupancy.NONE


def can_stack_with(left: Any, right: Any) -> bool:
    """Same def, idle, not unique, both below max_stack."""
    if left.get_def_id() != right.get_def_id():
        return False
    if left.get_item_kind() != right.get_item_kind():
        return False
    left_rules = _rules(left)
    right_rules = _rules(right)
    if left_rules.get("unique") or right_rules.get("unique"):
        return False
    if bool(left_rules.get("bound")) != bool(right_rules.get("bound")):
        return False
    if _occupancy(left) != Occupancy.NONE or _occupancy(right) != Occupancy.NONE:
        return False
    max_stack = int(left_rules.get("max_stack") or 1)
    qty_left = int(getattr(left, "quantity", 1) or 1)
    qty_right = int(getattr(right, "quantity", 1) or 1)
    return qty_left < max_stack and qty_right < max_stack
