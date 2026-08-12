"""活动互斥状态机单测。"""

from __future__ import annotations

import pytest

from app.domain.activity_mutex import (
    ERR_FINISH_CRAFT_FIRST,
    ERR_STOP_IDLE_FIRST,
    Activity,
    assert_can_perform,
    build_activity_snapshot,
)
from app.schemas.common import AppError


def test_enter_idle_blocked_by_craft_running() -> None:
    with pytest.raises(AppError) as ei:
        assert_can_perform(
            status="normal",
            idle_direction="none",
            activity=Activity.ENTER_IDLE,
            craft_running=1,
        )
    assert ei.value.code == ERR_FINISH_CRAFT_FIRST


def test_start_craft_blocked_while_idle() -> None:
    with pytest.raises(AppError) as ei:
        assert_can_perform(
            status="normal",
            idle_direction="spirit",
            activity=Activity.START_CRAFT,
        )
    assert ei.value.code == ERR_STOP_IDLE_FIRST


def test_start_battle_ok_when_free() -> None:
    assert_can_perform(
        status="normal",
        idle_direction="none",
        activity=Activity.START_BATTLE,
        craft_running=0,
    )


def test_snapshot_mode_idle() -> None:
    snap = build_activity_snapshot(
        status="normal",
        idle_direction="spirit",
        craft_running=0,
    )
    assert snap["mode"] == "idle"
    assert snap["can_start_battle"] is False
    assert snap["can_enter_idle"] is True
