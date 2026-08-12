"""
法宝耐久与一击破坏纯函数（M5 D15）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactStrikeResult:
    """Result of applying one tribulation strike to an artifact."""

    shattered: bool
    durability_left: int
    destroyed: bool


def resolve_artifact_strike(
    *,
    durability: int,
    cost_per_strike: int = 1,
    base_shatter_chance: float = 0.03,
    rng: random.Random,
) -> ArtifactStrikeResult:
    """
    Resolve shatter check then durability drain for one strike.

    Order: shatter first (ignores durability/power); if not shattered, subtract cost.
    Durability ≤ 0 → permanently destroyed.

    Args:
        durability: Current durability.
        cost_per_strike: Durability lost per strike when not shattered.
        base_shatter_chance: Flat shatter probability.
        rng: RNG instance.

    Returns:
        ArtifactStrikeResult: Shatter / durability / destroyed flags.
    """
    if rng.random() < float(base_shatter_chance):
        return ArtifactStrikeResult(shattered=True, durability_left=0, destroyed=True)

    left = max(0, int(durability) - max(0, int(cost_per_strike)))
    return ArtifactStrikeResult(
        shattered=False,
        durability_left=left,
        destroyed=left <= 0,
    )
