"""
M4 背包领域：堆叠增减纯函数。

InventoryService 负责 ORM 持久化。
"""

from __future__ import annotations

from typing import Any


def max_stack_for(item_id: str, item_type: str, inventory_cfg: Any) -> int:
    """
    查物品最大堆叠数。

    参数:
        item_id: 物品 id。
        item_type: 物品类型。
        inventory_cfg: InventoryConfig。

    返回:
        最大堆叠数。
    """
    items = inventory_cfg.items
    if item_id in items:
        return int(items[item_id].max_stack)
    by_type = inventory_cfg.stack_rules.by_item_type
    if item_type in by_type:
        return int(by_type[item_type])
    return int(inventory_cfg.stack_rules.default_max_stack)


def can_add_to_stack(current_qty: int, add_qty: int, max_stack: int) -> int:
    """
    计算可添加数量（受堆叠上限约束）。

    返回:
        实际可添加数量。
    """
    if add_qty <= 0:
        return 0
    room = max(0, max_stack - current_qty)
    return min(add_qty, room)


def apply_remove(current_qty: int, remove_qty: int) -> tuple[int, int]:
    """
    扣减堆叠。

    返回:
        (新数量, 实际扣减量)。
    """
    removed = min(current_qty, remove_qty)
    return current_qty - removed, removed


def aggregate_materials_needed(
    materials: list[dict[str, Any]],
    inventory_counts: dict[str, int],
) -> tuple[bool, list[str]]:
    """
    校验材料是否足够。

    返回:
        (是否足够, 缺失的 item_id 列表)。
    """
    missing: list[str] = []
    for mat in materials:
        item_id = str(mat["item_id"])
        need = int(mat["quantity"])
        have = int(inventory_counts.get(item_id, 0))
        if have < need:
            missing.append(item_id)
    return len(missing) == 0, missing
