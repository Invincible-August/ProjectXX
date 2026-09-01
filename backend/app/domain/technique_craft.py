"""Technique-craft rolls: elements, efficacy, embed, and affix pick."""

from __future__ import annotations

import random
import secrets
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.constants.technique_craft import (
    AFFIX_RARITY_DEFAULT,
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


def roll_three_weighted(
    pool: Sequence[str],
    weights: Mapping[str, float],
    rng: Any = None,
) -> list[str]:
    """
    Weighted pick of three affix ids (prefer unique when pool allows).

    Weights come from rarity tables. Non-positive / missing weights fall back to 1.

    Args:
        pool: Candidate affix ids.
        weights: affix_id → relative weight.
        rng: Optional random source with ``random``.

    Returns:
        list[str]: Exactly three ids.

    Raises:
        ValueError: if ``pool`` is empty.
    """
    items = [str(x) for x in pool if str(x)]
    if not items:
        raise ValueError("affix pool is empty")
    picker = rng if rng is not None else random.Random()

    def _weight(aid: str) -> float:
        raw = float(weights.get(aid, 1.0) or 0.0)
        return raw if raw > 0 else 1.0

    def _pick_one(candidates: list[str]) -> str:
        total = sum(_weight(a) for a in candidates)
        if total <= 0:
            return candidates[0]
        target = float(picker.random()) * total
        acc = 0.0
        for aid in candidates:
            acc += _weight(aid)
            if target <= acc:
                return aid
        return candidates[-1]

    remaining = list(items)
    chosen: list[str] = []
    while len(chosen) < 3 and remaining:
        pick = _pick_one(remaining)
        chosen.append(pick)
        remaining = [x for x in remaining if x != pick]
    while len(chosen) < 3:
        chosen.append(_pick_one(items))
    return chosen


def resolve_affix_rarity(affix_id: str, *, fallback: str | None = None) -> str:
    """Catalog rarity for an affix id, defaulting to white."""
    craft = get_game_config().research.technique_craft
    body = craft.affixes.get(str(affix_id or ""))
    rarity = str(getattr(body, "rarity", "") or "").strip()
    if rarity and rarity in craft.affix_rarities:
        return rarity
    fb = str(fallback or AFFIX_RARITY_DEFAULT)
    return fb if fb in craft.affix_rarities else AFFIX_RARITY_DEFAULT


def affix_rarity_def(rarity_id: str | None) -> Any:
    """Return rarity config row; white when unknown."""
    craft = get_game_config().research.technique_craft
    key = str(rarity_id or AFFIX_RARITY_DEFAULT)
    return craft.affix_rarities.get(key) or craft.affix_rarities.get(AFFIX_RARITY_DEFAULT)


def effective_affix_stats(
    affix_id: str,
    *,
    level: int = 0,
    rarity: str | None = None,
    rank_boost: int = 0,
) -> dict[str, float]:
    """
    Initial (and leveled) ATTR for a catalog affix.

    ``stats`` in YAML are white-baseline; multiplied by rarity ``base_mult``,
    then by ``1 + affix_level_mult * upgrade_mult * level + breakthrough_affix_bonus * rank_boost``.
    ``rank_boost`` stacks on breakthrough for affixes that already existed; new
    empty slots start at 0.
    """
    craft = get_game_config().research.technique_craft
    body = craft.affixes.get(str(affix_id or ""))
    if body is None:
        return {}
    rid = str(rarity or getattr(body, "rarity", "") or AFFIX_RARITY_DEFAULT)
    rare = affix_rarity_def(rid)
    base_mult = float(getattr(rare, "base_mult", 1.0) or 1.0)
    upgrade_mult = float(getattr(rare, "upgrade_mult", 1.0) or 1.0)
    level_mult = float(craft.affix_level_mult)
    bt_bonus = float(getattr(craft, "breakthrough_affix_bonus", 0.0) or 0.0)
    scale = base_mult * (
        1.0
        + level_mult * upgrade_mult * max(0, int(level))
        + bt_bonus * max(0, int(rank_boost))
    )
    out: dict[str, float] = {}
    for key, raw in (getattr(body, "stats", None) or {}).items():
        val = float(raw or 0) * scale
        if abs(val) > 1e-12:
            out[str(key)] = val
    return out


def affix_public_view(
    affix_id: str,
    *,
    level: int = 0,
    rarity: str | None = None,
    rank_boost: int = 0,
) -> dict[str, Any]:
    """Player-facing affix card: label, rarity, color, effective stats."""
    craft = get_game_config().research.technique_craft
    body = craft.affixes.get(str(affix_id or ""))
    rid = resolve_affix_rarity(affix_id, fallback=rarity)
    if rarity and str(rarity) in craft.affix_rarities:
        rid = str(rarity)
    rare = affix_rarity_def(rid)
    return {
        "id": str(affix_id or ""),
        "label_zh": str(getattr(body, "label_zh", None) or affix_id or "未知词条"),
        "rarity": rid,
        "rarity_label_zh": str(getattr(rare, "label_zh", None) or rid),
        "color": str(getattr(rare, "color", None) or "#ffffff"),
        "stats": effective_affix_stats(
            affix_id, level=level, rarity=rid, rank_boost=rank_boost
        ),
        "base_stats": {
            str(k): float(v)
            for k, v in (getattr(body, "stats", None) or {}).items()
        },
        "rank_boost": max(0, int(rank_boost)),
    }


def affix_upgrade_cost_multiplier(rarity: str | None) -> float:
    """Multiply table upgrade cost by rarity ``cost_mult``."""
    rare = affix_rarity_def(rarity)
    return float(getattr(rare, "cost_mult", 1.0) or 1.0)


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


def learner_meets_manual_rank(learner_major: str, snapshot_rank: str) -> bool:
    """
    True iff the learner's major-realm height is at least the snapshot rank.

    Unknown realm ids are fail-closed (False). Heights come from the
    ``realms.yaml`` ``next_major`` chain via ``major_realm_order``.
    """
    heights = _major_heights()
    learner_height = heights.get(str(learner_major))
    rank_height = heights.get(str(snapshot_rank))
    if learner_height is None or rank_height is None:
        return False
    return int(learner_height) >= int(rank_height)


def next_rank_id(current_rank: str) -> str | None:
    """Next major id from realms.yaml, or None at the end of the chain."""
    major = get_game_config().realms.get(str(current_rank))
    if major is None:
        return None
    nxt = getattr(major, "next_major", None)
    return str(nxt) if nxt else None


def major_rank_label_zh(rank_id: str | None) -> str:
    """
    Chinese display name for a technique major rank.

    Uses ``realms.yaml`` ``name``; never returns the raw English id.

    Args:
        rank_id: Major realm / craft rank id (e.g. ``true_immortal``).

    Returns:
        str: e.g. ``真仙``, or ``未知阶`` when missing.
    """
    key = str(rank_id or "").strip()
    if not key:
        return "未知阶"
    major = get_game_config().realms.get(key)
    name = getattr(major, "name", None) if major is not None else None
    label = str(name or "").strip()
    return label or "未知阶"


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


def enrich_affix_slots_public(slots: Sequence[Any]) -> list[dict[str, Any]]:
    """
    Attach option_views / chosen_view / next_upgrade_cost for player UI.

    Args:
        slots: Raw affix slot dicts from draft or payload.

    Returns:
        list[dict[str, Any]]: Enriched copies (does not mutate input items).
    """
    craft = get_game_config().research.technique_craft
    costs = tuple(int(x) for x in craft.affix_upgrade_cost)
    out: list[dict[str, Any]] = []
    for raw in slots:
        if not isinstance(raw, Mapping):
            continue
        cell = dict(raw)
        options = [str(x) for x in (cell.get("options") or [])]
        cell["option_views"] = [
            affix_public_view(aid, level=0, rank_boost=0) for aid in options
        ]
        chosen = str(cell.get("chosen_id") or "").strip()
        rarity = str(cell.get("chosen_rarity") or "").strip() or None
        rank_boost = max(0, int(cell.get("rank_boost") or 0))
        cell["rank_boost"] = rank_boost
        if chosen:
            if not rarity:
                rarity = resolve_affix_rarity(chosen)
                cell["chosen_rarity"] = rarity
            level = int(cell.get("chosen_level") or 0)
            cell["chosen_view"] = affix_public_view(
                chosen, level=level, rarity=rarity, rank_boost=rank_boost
            )
            table_cost = int(costs[min(max(level, 0), len(costs) - 1)]) if costs else 0
            cell["next_upgrade_cost"] = int(
                round(table_cost * affix_upgrade_cost_multiplier(rarity))
            )
        else:
            cell["chosen_view"] = None
            cell["next_upgrade_cost"] = None
        out.append(cell)
    return out


def payload_attr_grants(payload: Mapping[str, Any]) -> dict[str, float]:
    """
    Combat ATTR from cultivated payload: base clicks mapped by efficacy, plus scaled affixes.

    Affix YAML ``stats`` are white-baseline; rarity ``base_mult`` / ``upgrade_mult``,
    ``affix_level_mult``, and per-cell ``rank_boost`` × ``breakthrough_affix_bonus``
    scale the final grants.
    """
    craft = get_game_config().research.technique_craft
    per_click = float(craft.base_stat_per_click)
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

    slots = payload.get("affixes") or []
    if isinstance(slots, Sequence) and not isinstance(slots, (str, bytes)):
        for cell in slots:
            if not isinstance(cell, Mapping):
                continue
            aid = str(cell.get("chosen_id") or "").strip()
            if not aid:
                continue
            rarity = str(cell.get("chosen_rarity") or "").strip() or None
            for key, amount in effective_affix_stats(
                aid,
                level=int(cell.get("chosen_level") or 0),
                rarity=rarity,
                rank_boost=int(cell.get("rank_boost") or 0),
            ).items():
                _add(str(key), float(amount))
    return totals

