"""道友 / 交易领域纯规则（M7 L2 · 无 IO）。"""

from __future__ import annotations

from typing import Any


def item_may_trade(
    *,
    tradable: bool,
    bound: bool,
    unique: bool = False,
) -> tuple[bool, str | None]:
    """
    校验物品是否可上架/面交/易物/发机缘。

    Args:
        tradable: 配置可交易标记。
        bound: 绑定物标记。
        unique: 唯一物标记（不可拆分发放）。

    Returns:
        tuple: (允许, 中文拒绝原因)。
    """
    if bound:
        return False, "绑定物不可交易"
    if unique:
        return False, "唯一物不可交易"
    if not tradable:
        return False, "该物品不可交易"
    return True, None


def listing_fee_amount(price: int, fee_pct: float) -> int:
    """
    一口价手续费（向下取整，至少 0）。

    Args:
        price: 成交灵石价。
        fee_pct: 费率 0~1。

    Returns:
        int: 手续费灵石。
    """
    if price <= 0 or fee_pct <= 0:
        return 0
    return max(0, int(price * float(fee_pct)))


def barter_fee_for_realm(
    major_realm: str,
    fee_by_realm: dict[str, int],
    default_fee: int,
) -> int:
    """
    易物固定手续费（按上架者大境界）。

    Args:
        major_realm: 大境界键。
        fee_by_realm: YAML 表。
        default_fee: 缺省。

    Returns:
        int: 手续费。
    """
    if major_realm in fee_by_realm:
        return int(fee_by_realm[major_realm])
    return int(default_fee)


def auction_min_next_bid(current_price: int, min_increment_pct: float) -> int:
    """
    下一次最低有效出价。

    Args:
        current_price: 当前价（或起拍价）。
        min_increment_pct: 加价比例。

    Returns:
        int: 最低出价。
    """
    base = max(1, int(current_price))
    incr = max(1, int(base * float(min_increment_pct)))
    return base + incr


def friendship_pair_key(a: int, b: int) -> tuple[int, int]:
    """
    无向关系键：较小 id 在前。

    Args:
        a: 角色 id。
        b: 角色 id。

    Returns:
        tuple[int, int]: 规范化对。
    """
    return (a, b) if a < b else (b, a)


def parse_item_lines(raw: Any) -> list[dict[str, Any]]:
    """
    规范化物品行 ``[{item_id, quantity}]``。

    Args:
        raw: 列表或空。

    Returns:
        list: 规范化行。

    Raises:
        ValueError: 结构非法。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("物品列表须为数组")
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("物品行须为对象")
        item_id = str(row.get("item_id") or "").strip()
        qty = int(row.get("quantity") or 0)
        if not item_id or qty <= 0:
            raise ValueError("物品行须含 item_id 与正数量")
        out.append({"item_id": item_id, "quantity": qty})
    return out
