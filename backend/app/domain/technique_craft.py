"""Technique-craft card rolls: elements from a spirit-root pool, weighted efficacy."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any


def roll_elements(pool: Sequence[str], rng: Any = None) -> list[str]:
    """
    Pick 1..len(pool) distinct elements from the actor's available pool.

    Args:
        pool: Unique element ids (already mapped from spirit-root tags).
        rng: Optional random source with ``randint`` / ``sample`` (tests inject).

    Returns:
        list[str]: Chosen element ids. Empty if ``pool`` is empty — callers
        must reject that case with 40220 before consuming the type card.
    """
    items = [str(x) for x in pool if str(x)]
    if not items:
        return []
    picker = rng if rng is not None else random.Random()
    count = int(picker.randint(1, len(items)))
    return list(picker.sample(items, count))


def roll_efficacy(weights: Mapping[str, float], rng: Any = None) -> str:
    """
    Weighted pick of one efficacy id from ``technique_craft.efficacy_weights``.

    Args:
        weights: efficacy id → weight (non-positive entries ignored).
        rng: Optional random source with ``choices``.

    Returns:
        str: Chosen efficacy id.

    Raises:
        ValueError: if no positive weight remains.
    """
    keys: list[str] = []
    vals: list[float] = []
    for key, raw in weights.items():
        weight = float(raw)
        if weight > 0:
            keys.append(str(key))
            vals.append(weight)
    if not keys:
        raise ValueError("efficacy_weights has no positive entries")
    picker = rng if rng is not None else random.Random()
    if hasattr(picker, "choices"):
        return str(picker.choices(keys, weights=vals, k=1)[0])
    return keys[0]
