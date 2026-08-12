"""
天气池纯函数：加权抽取与环境锁定结构（M5 D2 / D3）。
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EnvLock:
    """开战 / 渡劫 / 工坊开工瞬间锁定的世界环境（过程中滚动不影响已锁实例）。"""

    shichen: str  # 锁定时辰键
    weather: str  # 锁定世界天气键（渡劫伤害用锁前天气）
    region_id: str = "default"  # 区域；M5 仅 default

    def to_dict(self) -> dict[str, Any]:
        """Serialize lock for JSON columns / API."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "EnvLock | None":
        """
        Parse an env lock from a mapping.

        Args:
            raw: Mapping with ``shichen`` / ``weather`` keys.

        Returns:
            EnvLock or None when raw is empty.
        """
        if not raw:
            return None
        return cls(
            shichen=str(raw["shichen"]),
            weather=str(raw["weather"]),
            region_id=str(raw.get("region_id", "default")),
        )


def weighted_pick(
    pool: Mapping[str, int | float],
    rng: random.Random | None = None,
) -> str:
    """
    Pick one weather id from a weight pool.

    Args:
        pool: Mapping of weather_id → weight (non-positive entries ignored).
        rng: Optional RNG; defaults to module ``random``.

    Returns:
        str: Selected weather id.

    Raises:
        ValueError: When the pool has no positive weights.
    """
    items: list[tuple[str, float]] = []
    for weather_id, weight in pool.items():
        w = float(weight)
        if w > 0:
            items.append((str(weather_id), w))
    if not items:
        raise ValueError("weather pool has no positive weights")
    picker = rng if rng is not None else random
    total = sum(w for _, w in items)
    roll = picker.random() * total
    cumulative = 0.0
    for weather_id, weight in items:
        cumulative += weight
        if roll <= cumulative:
            return weather_id
    return items[-1][0]


def build_env_lock(
    shichen: str,
    weather: str,
    *,
    region_id: str = "default",
) -> EnvLock:
    """
    Construct an immutable environment lock snapshot.

    Args:
        shichen: Locked shichen id.
        weather: Locked world weather id (pre-tribulation weather for 渡劫).
        region_id: Region key; M5 uses ``default``.

    Returns:
        EnvLock: Frozen lock struct.
    """
    return EnvLock(shichen=shichen, weather=weather, region_id=region_id)
