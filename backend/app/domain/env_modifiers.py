"""
环境修正叠加纯函数（M5 D4）：``base * shichen * weather`` 后 clamp。
"""

from __future__ import annotations

from typing import Mapping


def clamp_multiplier(
    value: float,
    *,
    min_value: float = 0.5,
    max_value: float = 1.5,
) -> float:
    """
    Clamp a multiplier into ``[min_value, max_value]``.

    Args:
        value: Raw multiplier.
        min_value: Lower bound.
        max_value: Upper bound.

    Returns:
        float: Clamped multiplier.
    """
    return max(min_value, min(max_value, float(value)))


def combine_env_multipliers(
    *,
    base: float = 1.0,
    shichen_mult: float = 1.0,
    weather_mult: float = 1.0,
    clamp_min: float = 0.5,
    clamp_max: float = 1.5,
) -> float:
    """
    Combine shichen and weather multipliers then clamp.

    Args:
        base: Base rate (e.g. gain_per_tick).
        shichen_mult: Multiplier from calendar table.
        weather_mult: Multiplier from weather table.
        clamp_min: Lower clamp.
        clamp_max: Upper clamp.

    Returns:
        float: ``clamp(base * shichen * weather)``.
    """
    raw = float(base) * float(shichen_mult) * float(weather_mult)
    return clamp_multiplier(raw, min_value=clamp_min, max_value=clamp_max)


def lookup_modifier(
    table: Mapping[str, float] | None,
    key: str,
    *,
    default: float = 1.0,
) -> float:
    """
    Look up a modifier coefficient with a safe default.

    Args:
        table: Id → multiplier mapping.
        key: Shichen or weather id.
        default: Fallback when missing.

    Returns:
        float: Multiplier.
    """
    if not table:
        return default
    if key not in table:
        return default
    return float(table[key])


def resolve_idle_cultivation_mult(
    *,
    shichen_id: str,
    weather_id: str,
    shichen_table: Mapping[str, float] | None,
    weather_table: Mapping[str, float] | None,
    clamp_min: float = 0.5,
    clamp_max: float = 1.5,
) -> float:
    """
    Resolve idle cultivation multiplier for one settle segment.

    Args:
        shichen_id: Current segment shichen.
        weather_id: Current segment weather.
        shichen_table: Calendar idle_cultivation modifiers.
        weather_table: Weather idle_cultivation modifiers.
        clamp_min: Lower clamp.
        clamp_max: Upper clamp.

    Returns:
        float: Final multiplier applied to base gain.
    """
    return combine_env_multipliers(
        base=1.0,
        shichen_mult=lookup_modifier(shichen_table, shichen_id),
        weather_mult=lookup_modifier(weather_table, weather_id),
        clamp_min=clamp_min,
        clamp_max=clamp_max,
    )


def resolve_craft_branch_mult(
    *,
    weather_id: str,
    branch: str,
    craft_tables: Mapping[str, Mapping[str, float]] | None,
    clamp_min: float = 0.5,
    clamp_max: float = 1.5,
) -> float:
    """
    Resolve craft efficiency multiplier for a locked weather + branch.

    Args:
        weather_id: Locked weather at craft start.
        branch: Recipe branch (alchemy / smithing / …).
        craft_tables: Nested ``branch → weather → mult``.
        clamp_min: Lower clamp.
        clamp_max: Upper clamp.

    Returns:
        float: Efficiency multiplier.
    """
    branch_table = (craft_tables or {}).get(branch) or {}
    mult = lookup_modifier(branch_table, weather_id, default=1.0)
    return clamp_multiplier(mult, min_value=clamp_min, max_value=clamp_max)
