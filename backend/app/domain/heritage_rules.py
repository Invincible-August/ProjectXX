"""传承（红包）拆分纯规则（M7 L5 · 无 IO）。"""

from __future__ import annotations

import random
from typing import Any


def split_spirit_random(
    total: int,
    share_count: int,
    *,
    rng: random.Random,
) -> list[int]:
    """
    拼手气拆分灵石（经典剩余均值二倍算法）。

    Args:
        total: 总额（须 >= share_count，保证每份至少 1）。
        share_count: 份数。
        rng: 可复现随机源。

    Returns:
        list[int]: 长度 = share_count，和为 total。
    """
    n = int(share_count)
    remain = int(total)
    if n <= 0:
        return []
    if remain < n:
        # 不足 1/份：尽量前 remain 份各 1，其余 0
        out = [1] * remain + [0] * (n - remain)
        return out
    parts: list[int] = []
    for i in range(n, 0, -1):
        if i == 1:
            parts.append(remain)
            break
        # 本份上限：剩余均值的 2 倍，至少 1，且留给后人每人至少 1
        max_take = max(1, min(remain - (i - 1), (remain * 2) // i))
        take = rng.randint(1, max_take) if max_take > 1 else 1
        parts.append(take)
        remain -= take
    return parts


def split_spirit_fixed(
    total: int,
    share_count: int,
    *,
    remainder_policy: str = "last_share",
) -> list[int]:
    """
    定额均分灵石。

    Args:
        total: 总额。
        share_count: 份数。
        remainder_policy: ``last_share`` 余数进末份；``recycle`` 余数不进份（调用方回收）。

    Returns:
        list[int]: 各份灵石；若 recycle，末份不含余数且返回列表之和可能 < total。
    """
    n = max(1, int(share_count))
    total_i = max(0, int(total))
    base = total_i // n
    rem = total_i % n
    parts = [base] * n
    if remainder_policy == "recycle":
        return parts
    if rem and parts:
        parts[-1] += rem
    return parts


def split_item_quantities(
    quantity: int,
    share_count: int,
    *,
    mode: str,
    rng: random.Random,
    remainder_policy: str = "last_share",
) -> list[int]:
    """
    将单行物品数量拆到各份。

    Args:
        quantity: 总数量。
        share_count: 份数。
        mode: random | fixed。
        rng: 随机源。
        remainder_policy: fixed 余数策略。

    Returns:
        list[int]: 每份数量。
    """
    qty = max(0, int(quantity))
    n = max(1, int(share_count))
    if qty == 0:
        return [0] * n
    if mode == "random":
        return split_spirit_random(qty, n, rng=rng)
    return split_spirit_fixed(qty, n, remainder_policy=remainder_policy)


def build_share_plan(
    *,
    spirit_stones: int,
    items: list[dict[str, Any]],
    share_count: int,
    mode: str,
    seed: int,
    remainder_policy: str = "last_share",
) -> list[dict[str, Any]]:
    """
    预计算每份内容（权威拆分，客户端禁止本地随机）。

    Args:
        spirit_stones: 总灵石。
        items: ``[{item_id, quantity}]``。
        share_count: 份数。
        mode: random | fixed。
        seed: RNG 种子。
        remainder_policy: fixed 余数。

    Returns:
        list[dict]: 每份 ``{spirit_stones, items}``。
    """
    n = max(1, int(share_count))
    rng = random.Random(int(seed))
    mode_l = str(mode or "fixed").lower()
    if mode_l == "random":
        stone_parts = split_spirit_random(int(spirit_stones), n, rng=rng)
    else:
        stone_parts = split_spirit_fixed(
            int(spirit_stones),
            n,
            remainder_policy=remainder_policy,
        )
    item_parts: list[list[dict[str, Any]]] = [[] for _ in range(n)]
    for line in items:
        item_id = str(line.get("item_id") or "").strip()
        qty = int(line.get("quantity") or 0)
        if not item_id or qty <= 0:
            continue
        qs = split_item_quantities(
            qty,
            n,
            mode=mode_l,
            rng=rng,
            remainder_policy=remainder_policy,
        )
        for i, q in enumerate(qs):
            if q > 0:
                item_parts[i].append({"item_id": item_id, "quantity": int(q)})
    return [
        {"spirit_stones": int(stone_parts[i]), "items": item_parts[i]}
        for i in range(n)
    ]


def fixed_recycle_remainder(total: int, share_count: int) -> int:
    """fixed+recycle 时余数灵石。"""
    n = max(1, int(share_count))
    return max(0, int(total)) % n
