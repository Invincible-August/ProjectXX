"""
六时历法服务：公式推算 + GM 强制覆盖（内存）（M5 E1）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.core.time_utils import now_utc, to_utc_iso
from app.domain.calendar_rules import current_shichen
from app.services.m5_features import require_calendar_enabled
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

# GM 强制时辰：进程内覆盖（memory 后端）
_gm_force_shichen: str | None = None


def clear_calendar_overrides() -> None:
    """Clear GM shichen override (tests)."""
    global _gm_force_shichen
    _gm_force_shichen = None


def set_gm_force_shichen(shichen_id: str | None) -> None:
    """
    Set or clear GM forced shichen id.

    Args:
        shichen_id: Shichen id or None to clear.
    """
    global _gm_force_shichen
    _gm_force_shichen = shichen_id
    logger.info("gm force_shichen=%s", shichen_id)


class CalendarService:
    """
    Authoritative six-shichen calendar reader.

    Attributes:
        None: Stateless aside from module-level GM override.
    """

    def get_snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        """
        Return current calendar snapshot for API / consumers.

        When ``CALENDAR_ENABLED=false``, returns fixed noon placeholder.

        Args:
            now: Optional frozen UTC time.

        Returns:
            dict: shichen_id, slot, labels, next_at, server_now, forced flag.
        """
        settings = get_settings()
        cfg = get_game_config().calendar
        current = now_utc(now)

        if not settings.calendar_enabled:
            return {
                "shichen_id": "noon",
                "slot": 1,
                "label": cfg.labels.get("noon", "正午"),
                "next_at": to_utc_iso(current),
                "server_now": to_utc_iso(current),
                "slot_seconds": cfg.slot_seconds,
                "forced": False,
                "disabled": True,
            }

        snap = current_shichen(
            current,
            cfg.epoch_utc,
            slot_seconds=cfg.slot_seconds,
            shichen_order=cfg.shichen_order,
            labels=cfg.labels,
        )
        shichen_id = snap.shichen_id
        slot = snap.slot
        forced = False
        if _gm_force_shichen:
            shichen_id = _gm_force_shichen
            if shichen_id in cfg.shichen_order:
                slot = cfg.shichen_order.index(shichen_id)
            forced = True

        return {
            "shichen_id": shichen_id,
            "slot": slot,
            "label": cfg.labels.get(shichen_id) or f"未知({shichen_id})",
            "next_at": to_utc_iso(snap.next_at),
            "server_now": to_utc_iso(snap.server_now),
            "slot_seconds": cfg.slot_seconds,
            "forced": forced,
            "disabled": False,
            "order": list(cfg.shichen_order),
            "labels": dict(cfg.labels),
        }

    def require_and_get(self, now: datetime | None = None) -> dict[str, Any]:
        """
        Gate on calendar enabled then return snapshot.

        Args:
            now: Optional frozen time.

        Returns:
            dict: Calendar snapshot.
        """
        require_calendar_enabled()
        return self.get_snapshot(now=now)
