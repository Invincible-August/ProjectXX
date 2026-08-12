"""邮件 / 赠送领域纯规则（M7 L3 · 无 IO）。"""

from __future__ import annotations

from typing import Any


def normalize_attachments(
    *,
    spirit_stones: int = 0,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    规范化附件结构。

    Args:
        spirit_stones: 灵石。
        items: 物品行。

    Returns:
        dict: ``{spirit_stones, items}``。
    """
    lines: list[dict[str, Any]] = []
    for row in items or []:
        item_id = str(row.get("item_id") or "").strip()
        qty = int(row.get("quantity") or 0)
        if not item_id or qty <= 0:
            continue
        lines.append({"item_id": item_id, "quantity": qty})
    return {
        "spirit_stones": max(0, int(spirit_stones)),
        "items": lines,
    }


def attachments_empty(att: dict[str, Any]) -> bool:
    """附件是否为空（无石无物）。"""
    return int(att.get("spirit_stones") or 0) <= 0 and not (att.get("items") or [])


def estimate_gift_spirit_value(
    *,
    spirit_stones: int,
    items: list[dict[str, Any]],
    item_values: dict[str, int],
    default_value: int,
) -> int:
    """
    赠送日限额估价。

    Args:
        spirit_stones: 现金灵石。
        items: 物品行。
        item_values: item_id → 估价。
        default_value: 缺省单价。

    Returns:
        int: 总估价。
    """
    total = max(0, int(spirit_stones))
    for row in items:
        item_id = str(row.get("item_id") or "")
        qty = int(row.get("quantity") or 0)
        unit = int(item_values.get(item_id, default_value))
        total += unit * qty
    return total
