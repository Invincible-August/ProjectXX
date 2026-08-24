"""
Pure research helpers (no IO).
"""

from __future__ import annotations

import re
from typing import Any, Sequence

_CJK = re.compile(r"[\u4e00-\u9fff]")


def is_valid_zh_label(label: str, *, min_len: int = 2, max_len: int = 16) -> bool:
    """Return True when label is a short Chinese-visible name."""
    text = (label or "").strip()
    if not (min_len <= len(text) <= max_len):
        return False
    return len(_CJK.findall(text)) >= min_len


def pick_affix_ids(
    pool: Sequence[str],
    *,
    roll: int,
    slots: int,
    extra_affix_roll: int,
) -> list[str]:
    """
    Deterministically pick 1..slots affix ids from pool using the dice roll.

    Args:
        pool: Whitelist affix ids (order from YAML).
        roll: Dice face.
        slots: Max affix count.
        extra_affix_roll: Inclusive threshold to grant a second affix.

    Returns:
        list[str]: Unique affix ids.
    """
    if not pool:
        return []
    count = 1
    if slots >= 2 and roll >= extra_affix_roll:
        count = min(slots, 2)
    count = min(count, len(pool), max(1, slots))
    start = roll % len(pool)
    picked: list[str] = []
    idx = start
    while len(picked) < count:
        candidate = str(pool[idx % len(pool)])
        if candidate not in picked:
            picked.append(candidate)
        idx += 1
        if idx - start > len(pool) * 2:
            break
    return picked


def sum_affix_stats(affix_ids: Sequence[str], affixes: dict[str, Any]) -> dict[str, float]:
    """Sum stats dicts for selected affixes."""
    totals: dict[str, float] = {}
    for affix_id in affix_ids:
        body = affixes.get(str(affix_id))
        if body is None:
            continue
        stats = getattr(body, "stats", None) or {}
        for key, val in stats.items():
            totals[str(key)] = totals.get(str(key), 0.0) + float(val)
    return totals
