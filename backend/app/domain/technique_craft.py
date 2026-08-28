"""Technique-craft card rolls: elements, efficacy, and embed success."""

from __future__ import annotations

import random
import secrets
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


def roll_embed_success(fail_rate: float, rng: Any = None) -> bool:
    """
    Whether a formal-card embed succeeds.

    A uniform draw in ``[0, 1)`` strictly below ``fail_rate`` fails.
    Rate ``<= 0`` always succeeds; ``>= 1`` always fails.

    Args:
        fail_rate: ``technique_craft.embed_fail_rate`` from YAML.
        rng: Optional source with ``random()`` (tests inject).

    Returns:
        bool: True to write the card onto the draft; False to consume only.
    """
    rate = float(fail_rate)
    if rate <= 0:
        return True
    if rate >= 1:
        return False
    if rng is not None:
        draw = float(rng.random())
    else:
        draw = secrets.randbelow(10000) / 10000.0
    return draw >= rate
