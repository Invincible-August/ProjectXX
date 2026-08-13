"""邮件领域纯规则（M7 L3 · 无 IO）。

含：附件规范化、堆叠上限校验、赠送估价、可删判定。
"""

from __future__ import annotations

from typing import Any

from app.domain.inventory_rules import max_stack_for


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


def mail_can_delete(
    *,
    is_read: bool,
    is_claimed: bool,
    has_attachments: bool,
) -> bool:
    """
    是否允许删除：须已读；有附件须已领。

    Args:
        is_read: 已读。
        is_claimed: 已领（或无附件视同可删侧）。
        has_attachments: 当前仍展示未领附件。

    Returns:
        bool: 可删。
    """
    if not is_read:
        return False
    if has_attachments and not is_claimed:
        return False
    return True


def clamp_item_qty_to_max_stack(
    *,
    item_id: str,
    quantity: int,
    item_type: str,
    inventory_cfg: Any,
) -> int:
    """
    将数量钳到该物品最大堆叠。

    Args:
        item_id: 物品 id。
        quantity: 请求数量。
        item_type: 物品类型。
        inventory_cfg: InventoryConfig。

    Returns:
        int: 合法数量（至少 1 时由调用方保证）。
    """
    cap = max_stack_for(item_id, item_type, inventory_cfg)
    return max(0, min(int(quantity), int(cap)))


def validate_attachment_item_stacks(
    items: list[dict[str, Any]],
    inventory_cfg: Any,
) -> tuple[bool, str | None, list[dict[str, Any]]]:
    """
    校验并钳制附件物品数量不超过最大堆叠。

    Args:
        items: 物品行。
        inventory_cfg: InventoryConfig。

    Returns:
        tuple: (ok, 错误中文, 钳制后的行)。
    """
    out: list[dict[str, Any]] = []
    for row in items:
        item_id = str(row.get("item_id") or "").strip()
        qty = int(row.get("quantity") or 0)
        if not item_id or qty <= 0:
            continue
        defn = inventory_cfg.items.get(item_id)
        if defn is None:
            return False, f"未知物品：{item_id}", []
        item_type = str(defn.item_type or "material")
        max_stack = max_stack_for(item_id, item_type, inventory_cfg)
        if qty > max_stack:
            return (
                False,
                f"「{defn.name}」单次最多 {max_stack}（最大堆叠）",
                [],
            )
        out.append({"item_id": item_id, "quantity": qty})
    return True, None, out


def estimate_gift_spirit_value(
    *,
    spirit_stones: int,
    items: list[dict[str, Any]],
    item_values: dict[str, int],
    default_value: int,
) -> int:
    """
    附带道具/灵石发信的日限额估价。

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


def sect_rank_allows_broadcast(
    rank: str,
    disciple_ranks: dict[str, Any],
    *,
    min_order: int,
) -> bool:
    """
    宗门职位是否允许群发（掌门及以上：order >= min_order）。

    Args:
        rank: 职位键。
        disciple_ranks: sects.yaml disciple_ranks。
        min_order: 最低 order（默认 9=掌门）。

    Returns:
        bool: 允许。
    """
    body = disciple_ranks.get(str(rank)) or {}
    order = int(body.get("order") or 0)
    return order >= int(min_order)
