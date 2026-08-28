"""Technique-craft rolls: elements, efficacy, embed, and affix pick."""

from __future__ import annotations

import random
import secrets
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.constants.technique_craft import (
    AFFIX_ROLE_DEFENSE,
    ATTACK_EFFICACIES,
    MARTIAL_EFFICACIES,
    SPELL_EFFICACIES,
)
from app.services.realm_config import get_game_config


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


def _affix_field(item: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a dataclass, mapping, or dict-like affix."""
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _str_tuple(raw: Any) -> tuple[str, ...]:
    """Normalize a YAML list/string field into a tuple of ids."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,) if raw else ()
    return tuple(str(x) for x in raw if str(x))


def _family_for_efficacy(efficacy: str) -> frozenset[str] | None:
    """Spell vs martial family used to hide cross-type affixes."""
    if efficacy in SPELL_EFFICACIES:
        return SPELL_EFFICACIES
    if efficacy in MARTIAL_EFFICACIES:
        return MARTIAL_EFFICACIES
    return None


def filter_affixes(
    catalog: Mapping[str, Any] | Sequence[Any],
    *,
    efficacy: str,
    elements: Sequence[str] | None = None,
    element_limit: str | None = None,
    weapon_limit: str | None = None,
) -> list[Any]:
    """
    Keep catalog entries compatible with the draft's efficacy and conditions.

    Rules:
        * ``efficacy`` must be listed in ``efficacy_allow``.
        * Spell drafts (``SPELL_EFFICACIES``) drop martial-only affixes; martial
          drafts drop spell-only affixes.
        * ``role=defense`` is dropped when ``efficacy`` is in ``ATTACK_EFFICACIES``.
        * Empty ``weapon_limit`` does not filter weapons. A set limit only
          drops affixes that declare a non-empty ``weapon_allow`` excluding it.
        * Affixes with ``element_allow`` must intersect the draft elements
          (and ``element_limit`` when that box is set).

    Args:
        catalog: YAML affix map or a sequence of affix objects.
        efficacy: Draft efficacy id.
        elements: Embedded element ids (optional extra filter).
        element_limit: Confirmed element condition, or empty.
        weapon_limit: Confirmed weapon condition, or empty.

    Returns:
        list[Any]: Surviving catalog values, original order.
    """
    wanted = str(efficacy or "")
    family = _family_for_efficacy(wanted)
    element_set = {str(x) for x in (elements or ()) if str(x)}
    limit_el = str(element_limit or "").strip()
    limit_wp = str(weapon_limit or "").strip()

    if isinstance(catalog, Mapping):
        items_iter: Sequence[Any] = list(catalog.values())
    else:
        items_iter = catalog

    kept: list[Any] = []
    for item in items_iter:
        allow = set(_str_tuple(_affix_field(item, "efficacy_allow")))
        if wanted not in allow:
            continue
        if family is not None and allow.isdisjoint(family):
            continue
        role = str(_affix_field(item, "role", "") or "")
        if role == AFFIX_ROLE_DEFENSE and wanted in ATTACK_EFFICACIES:
            continue
        weapon_allow = _str_tuple(_affix_field(item, "weapon_allow"))
        if limit_wp and weapon_allow and limit_wp not in weapon_allow:
            continue
        element_allow = _str_tuple(_affix_field(item, "element_allow"))
        if element_allow:
            if limit_el and limit_el not in element_allow:
                continue
            if element_set and element_set.isdisjoint(element_allow):
                continue
        kept.append(item)
    return kept


def roll_three(pool: Sequence[str], rng: Any = None) -> list[str]:
    """
    Pick three affix ids. Duplicates are allowed when the pool is smaller than 3.

    A 1-item pool always yields that id three times. A pool of 3+ samples
    without replacement.

    Args:
        pool: Candidate affix ids (already filtered).
        rng: Optional source with ``sample`` / ``choice`` / ``shuffle``.

    Returns:
        list[str]: Exactly three ids.

    Raises:
        ValueError: if ``pool`` is empty.
    """
    items = [str(x) for x in pool if str(x)]
    if not items:
        raise ValueError("affix pool is empty")
    picker = rng if rng is not None else random.Random()
    if len(items) >= 3:
        return list(picker.sample(items, 3))
    chosen = list(items)
    while len(chosen) < 3:
        chosen.append(str(picker.choice(items)))
    picker.shuffle(chosen)
    return chosen


def roll_affix_upgrade_success(fail_rate: float, rng: Any = None) -> bool:
    """Whether an affix upgrade succeeds. Same draw rules as embed."""
    return roll_embed_success(fail_rate, rng)


def roll_breakthrough_success(fail_rate: float, rng: Any = None) -> bool:
    """Whether a rank breakthrough succeeds. Same draw rules as embed."""
    return roll_embed_success(fail_rate, rng)


def upgrade_points_for_base_level(n: int) -> int:
    """
    Upgrade points granted when the Nth (1-based) base click succeeds.

    Reads ``technique_craft.base_bonus_points``; index is ``min(n-1, len-1)``.
    """
    table = get_game_config().research.technique_craft.base_bonus_points
    if n < 1 or not table:
        return 0
    return int(table[min(n - 1, len(table) - 1)])


def upgrade_points_for_affix_level(n: int) -> int:
    """Upgrade points granted when an affix reaches 1-based level ``n``."""
    table = get_game_config().research.technique_craft.affix_upgrade_points
    if n < 1 or not table:
        return 0
    return int(table[min(n - 1, len(table) - 1)])


def _major_heights(realms: Mapping[str, Any] | None = None) -> dict[str, int]:
    """Height along realms.yaml ``next_major`` chain (root = 0)."""
    from app.domain.avatar_rules import major_realm_order

    source = realms if realms is not None else get_game_config().realms
    return {str(rid): i for i, rid in enumerate(major_realm_order(source))}


def next_rank_id(current_rank: str) -> str | None:
    """Next major id from realms.yaml, or None at the end of the chain."""
    major = get_game_config().realms.get(str(current_rank))
    if major is None:
        return None
    nxt = getattr(major, "next_major", None)
    return str(nxt) if nxt else None


def rank_cap(character_major: str, rank_ids: Iterable[str]) -> str:
    """
    Highest configured craft rank whose height ≤ the character's major realm.

    Args:
        character_major: Character ``major_realm`` id.
        rank_ids: Keys of ``technique_craft.ranks``.
    """
    heights = _major_heights()
    char_h = heights.get(str(character_major), -1)
    best = ""
    best_h = -1
    for rid in rank_ids:
        key = str(rid)
        height = heights.get(key, -1)
        if height < 0 or height > char_h:
            continue
        if height >= best_h:
            best = key
            best_h = height
    return best or "body_tempering"


def can_breakthrough(
    current_rank: str,
    upgrade_points: int,
    character_major: str,
    ranks: Mapping[str, Any],
) -> bool:
    """
    True when next rank exists in ``ranks``, height ≤ character, and points meet the gate.

    Next id comes from realms.yaml ``next_major``, not from iterating rank keys.
    """
    nxt = next_rank_id(current_rank)
    if not nxt or nxt not in ranks:
        return False
    heights = _major_heights()
    if heights.get(nxt, 10**9) > heights.get(str(character_major), -1):
        return False
    body = ranks[nxt]
    required = int(getattr(body, "upgrade_points_required", 0) or 0)
    if isinstance(body, Mapping):
        required = int(body.get("upgrade_points_required") or 0)
    return int(upgrade_points) >= required


def payload_attr_grants(payload: Mapping[str, Any]) -> dict[str, float]:
    """
    Combat ATTR from cultivated payload: base clicks mapped by efficacy, plus scaled affixes.

    Base attack/defense/speed map to magic_* for ``SPELL_EFFICACIES`` and phys_* for
    ``MARTIAL_EFFICACIES``. Affix catalog stats scale by ``1 + affix_level_mult * chosen_level``.
    """
    craft = get_game_config().research.technique_craft
    per_click = float(craft.base_stat_per_click)
    level_mult = float(craft.affix_level_mult)
    efficacy = str(payload.get("efficacy") or "")
    if efficacy in SPELL_EFFICACIES:
        atk_key, def_key = "magic_atk", "magic_def"
    else:
        atk_key, def_key = "phys_atk", "phys_def"
    base_raw = payload.get("base") or {}
    base = dict(base_raw) if isinstance(base_raw, Mapping) else {}
    totals: dict[str, float] = {}

    def _add(key: str, amount: float) -> None:
        if abs(amount) <= 1e-12:
            return
        totals[key] = totals.get(key, 0.0) + amount

    _add(atk_key, int(base.get("attack") or 0) * per_click)
    _add(def_key, int(base.get("defense") or 0) * per_click)
    _add("speed", int(base.get("speed") or 0) * per_click)

    catalog = craft.affixes
    slots = payload.get("affixes") or []
    if isinstance(slots, Sequence) and not isinstance(slots, (str, bytes)):
        for cell in slots:
            if not isinstance(cell, Mapping):
                continue
            aid = str(cell.get("chosen_id") or "").strip()
            if not aid:
                continue
            body = catalog.get(aid)
            stats = getattr(body, "stats", None) if body is not None else None
            if not stats:
                continue
            scale = 1.0 + level_mult * int(cell.get("chosen_level") or 0)
            for key, raw in stats.items():
                _add(str(key), float(raw or 0) * scale)
    return totals

