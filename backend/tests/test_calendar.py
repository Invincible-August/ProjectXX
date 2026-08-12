"""六时历法纯函数与配置加载测试（M5 E1）。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.calendar_rules import current_shichen, parse_epoch_utc
from app.services.calendar_service import CalendarService, clear_calendar_overrides, set_gm_force_shichen
from app.services.realm_config import clear_game_config_cache, get_game_config


@pytest.fixture(autouse=True)
def _cfg() -> None:
    """Reset config cache and GM overrides."""
    clear_game_config_cache()
    clear_calendar_overrides()
    yield
    clear_calendar_overrides()
    clear_game_config_cache()


def test_current_shichen_slot_formula() -> None:
    """epoch 起算 0～59s 为 slot0；60～119s 为 slot1。"""
    epoch = parse_epoch_utc("2026-01-01T00:00:00Z")
    now0 = datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
    snap0 = current_shichen(now0, epoch, slot_seconds=60)
    assert snap0.slot == 0
    assert snap0.shichen_id == "dawn"

    now1 = datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)
    snap1 = current_shichen(now1, epoch, slot_seconds=60)
    assert snap1.slot == 1
    assert snap1.shichen_id == "noon"


def test_calendar_cycles_six() -> None:
    """满 6 个 slot 回到 dawn。"""
    epoch = "2026-01-01T00:00:00Z"
    now = datetime(2026, 1, 1, 0, 6, 0, tzinfo=timezone.utc)
    snap = current_shichen(now, epoch, slot_seconds=60)
    assert snap.slot == 0
    assert snap.shichen_id == "dawn"


def test_calendar_service_gm_force() -> None:
    """GM 强制时辰覆盖公式结果。"""
    set_gm_force_shichen("night")
    snap = CalendarService().get_snapshot(
        now=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
    )
    assert snap["shichen_id"] == "night"
    assert snap["forced"] is True


def test_calendar_yaml_loaded() -> None:
    """GameConfigBundle 含 calendar。"""
    cfg = get_game_config().calendar
    assert len(cfg.shichen_order) == 6
    assert cfg.slot_seconds == 60
    assert "idle_cultivation" in cfg.modifiers
