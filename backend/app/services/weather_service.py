"""
区域天气服务：惰性滚动 + GM 强制 + 劫云 overlay（内存）（M5 E2）。
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.time_utils import now_utc, to_utc_iso
from app.domain.weather_rules import weighted_pick
from app.services.m5_features import require_weather_enabled
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

# region_id → {weather_id, next_roll_at}
_weather_state: dict[str, dict[str, Any]] = {}
_gm_force_weather: str | None = None
# 劫云 overlays：list of {region_id, source_character_id, cloud_radius, expires_at}
_cloud_overlays: list[dict[str, Any]] = []


def clear_weather_state() -> None:
    """Reset memory weather / overlays / GM force (tests)."""
    global _gm_force_weather
    _weather_state.clear()
    _cloud_overlays.clear()
    _gm_force_weather = None


def set_gm_force_weather(weather_id: str | None) -> None:
    """Set or clear GM forced weather."""
    global _gm_force_weather
    _gm_force_weather = weather_id
    logger.info("gm force_weather=%s", weather_id)


class WeatherService:
    """
    Default-region weather roller with optional tribulation cloud overlay.

    Attributes:
        _rng: Optional injected RNG for tests.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        """
        Args:
            rng: Optional RNG for weighted rolls.
        """
        self._rng = rng

    def _region(self, region_id: str = "default") -> Any:
        """Load region pool config."""
        cfg = get_game_config().weather
        return cfg.regions.get(region_id) or cfg.regions.get("default")

    def _ensure_state(self, region_id: str, now: datetime) -> dict[str, Any]:
        """Lazy-init and roll weather when due."""
        region = self._region(region_id)
        if region is None:
            return {"weather_id": "clear", "next_roll_at": now}

        state = _weather_state.get(region_id)
        if state is None:
            weather_id = weighted_pick(region.pool, self._rng)
            next_at = now + timedelta(seconds=region.roll_interval_seconds)
            state = {"weather_id": weather_id, "next_roll_at": next_at}
            _weather_state[region_id] = state
            logger.info(
                "weather init region=%s weather=%s next=%s",
                region_id,
                weather_id,
                next_at,
            )
            return state

        next_roll = state["next_roll_at"]
        if isinstance(next_roll, datetime) and now >= next_roll:
            weather_id = weighted_pick(region.pool, self._rng)
            next_at = now + timedelta(seconds=region.roll_interval_seconds)
            state = {"weather_id": weather_id, "next_roll_at": next_at}
            _weather_state[region_id] = state
            logger.info(
                "weather rolled region=%s weather=%s",
                region_id,
                weather_id,
            )
        return state

    def get_snapshot(
        self,
        *,
        region_id: str = "default",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Return current weather for region (lazy roll).

        Args:
            region_id: Region key; M5 uses ``default``.
            now: Optional frozen time.

        Returns:
            dict: weather_id, label, next_roll_at, in_cloud, forced.
        """
        settings = get_settings()
        cfg = get_game_config().weather
        current = now_utc(now)

        if not settings.weather_enabled:
            return {
                "region_id": region_id,
                "weather_id": "clear",
                "label": cfg.labels.get("clear", "晴"),
                "next_roll_at": to_utc_iso(current),
                "server_now": to_utc_iso(current),
                "forced": False,
                "in_cloud": False,
                "disabled": True,
            }

        state = self._ensure_state(region_id, current)
        weather_id = str(state["weather_id"])
        forced = False
        if _gm_force_weather:
            weather_id = _gm_force_weather
            forced = True

        in_cloud = self.is_region_under_cloud(region_id, now=current)
        # 表现：有劫云时顶栏可显示 tribulation_cloud，但结算仍用锁前天气
        display_weather = "tribulation_cloud" if in_cloud and not forced else weather_id

        return {
            "region_id": region_id,
            "weather_id": weather_id,
            "display_weather_id": display_weather,
            "label": cfg.labels.get(display_weather) or (
                "劫云" if display_weather == "tribulation_cloud" else f"未知({display_weather})"
            ),
            "next_roll_at": to_utc_iso(state["next_roll_at"]),
            "server_now": to_utc_iso(current),
            "forced": forced,
            "in_cloud": in_cloud,
            "disabled": False,
        }

    def require_and_get(
        self,
        *,
        region_id: str = "default",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Gate on weather enabled then snapshot."""
        require_weather_enabled()
        return self.get_snapshot(region_id=region_id, now=now)

    def is_region_under_cloud(
        self,
        region_id: str = "default",
        now: datetime | None = None,
    ) -> bool:
        """Return whether any non-expired cloud overlay covers the region."""
        current = now_utc(now)
        for overlay in _cloud_overlays:
            if overlay.get("region_id") != region_id:
                continue
            expires = overlay.get("expires_at")
            if expires is None or current < expires:
                return True
        return False

    def begin_cloud(
        self,
        *,
        region_id: str,
        source_character_id: int,
        cloud_radius: int,
        expires_at: datetime | None = None,
    ) -> None:
        """
        Register a tribulation cloud overlay for the region.

        Args:
            region_id: Region key.
            source_character_id: Character who began tribulation.
            cloud_radius: Configured radius (marker only in M5).
            expires_at: Optional expiry; None = until clear.
        """
        _cloud_overlays.append(
            {
                "region_id": region_id,
                "source_character_id": source_character_id,
                "cloud_radius": int(cloud_radius),
                "expires_at": expires_at,
            },
        )
        logger.info(
            "cloud begin region=%s character_id=%s radius=%s",
            region_id,
            source_character_id,
            cloud_radius,
        )

    def clear_cloud_for_character(self, character_id: int) -> None:
        """Remove overlays sourced by the given character."""
        global _cloud_overlays
        before = len(_cloud_overlays)
        _cloud_overlays = [
            o for o in _cloud_overlays if o.get("source_character_id") != character_id
        ]
        if len(_cloud_overlays) != before:
            logger.info("cloud cleared character_id=%s", character_id)

    def get_underlying_weather_id(
        self,
        *,
        region_id: str = "default",
        now: datetime | None = None,
    ) -> str:
        """
        Return roll/GM weather without cloud display override (for locking).

        Args:
            region_id: Region.
            now: Optional frozen time.

        Returns:
            str: Weather id suitable for env lock.
        """
        snap = self.get_snapshot(region_id=region_id, now=now)
        return str(snap["weather_id"])
