"""
异步真读条突破测试（M5-D05 / M1-D20）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.domain.activity_mutex import Activity, assert_can_perform
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import (
    auth_service,
    battle_service,
    breakthrough_service,
    character_service,
    idle_service,
)
from app.services.realm_config import clear_game_config_cache, get_game_config
from tests.async_db import open_test_session_factory, run_async as _run


async def _prepare(session, email: str, name: str) -> User:
    """注册并创角。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    """启用真读条；缩短时长由用例内 duration 配置决定（默认 yaml）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "offline_preview_threshold_seconds", 300)
    clear_game_config_cache()
    # 确保走异步路径（默认 yaml enabled=true；若被其它用例污染则强制）
    monkeypatch.setattr(
        "app.services.breakthrough_service.BreakthroughService._async_enabled",
        staticmethod(lambda: True),
    )
    yield
    clear_game_config_cache()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", None)
    monkeypatch.setattr(settings, "grade_rng_seed", None)


def test_channel_start_sets_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开读条：status=breaking_through；灵石已扣；境界未变。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_start.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch01@example.com", "闭关者甲")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                data = await breakthrough_service.start_channel(session, user, now=t0)
                await session.commit()
                assert data["success"] is None
                assert data["channel_started"] is True
                assert data["character"]["status"] == "breaking_through"
                assert data["character"]["realm_stage"] == 1
                assert data["character"]["spirit_stones"] == 200  # 筑基前开读条不扣石
                assert data["channel"]["state"] == "in_progress"
                assert data["channel"]["advance_type_label_zh"] == "层进阶"

    _run(_body())


def test_channel_progress_midway_no_realm_change(tmp_path: Path) -> None:
    """未到期 resolve / get_channel 不升境。"""
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    duration = get_game_config().breakthrough.async_channel.duration_for("layer")

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_mid.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch02@example.com", "闭关者乙")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                await breakthrough_service.start_channel(session, user, now=t0)
                await session.commit()

                mid = t0 + timedelta(seconds=max(1, duration // 2))
                with pytest.raises(AppError) as exc_info:
                    await breakthrough_service.resolve_channel(session, user, now=mid)
                assert exc_info.value.code == 40028

                progress = await breakthrough_service.get_channel(session, user, now=mid)
                await session.commit()
                assert progress["channel"]["state"] == "in_progress"
                assert progress["character"]["realm_stage"] == 1
                assert progress["character"]["status"] == "breaking_through"

    _run(_body())


def test_channel_lazy_resolve_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """拨钟后成功升境；status=normal。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    duration = get_game_config().breakthrough.async_channel.duration_for("layer")

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_ok.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch03@example.com", "闭关者丙")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                await breakthrough_service.start_channel(session, user, now=t0)
                await session.commit()

                end = t0 + timedelta(seconds=duration + 1)
                data = await breakthrough_service.get_channel(session, user, now=end)
                await session.commit()
                assert data.get("just_resolved") is True
                assert data["channel"]["state"] == "resolved"
                result = data["channel"]["result"]
                assert result["success"] is True
                assert data["character"]["status"] == "normal"
                assert data["character"]["realm_stage"] == 2
                assert data["character"]["realm_progress"] == 0

    _run(_body())


def test_channel_lazy_resolve_fail_keep_ratio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失败 keep_ratio；灵石已在开读条扣除。"""
    settings = get_settings()
    import random as _random

    fail_seed = None
    for candidate in range(0, 5000):
        if _random.Random(candidate).random() >= 0.85:
            fail_seed = candidate
            break
    assert fail_seed is not None
    monkeypatch.setattr(settings, "breakthrough_rng_seed", fail_seed)
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    duration = get_game_config().breakthrough.async_channel.duration_for("layer")

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_fail.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch04@example.com", "闭关者丁")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                await breakthrough_service.start_channel(session, user, now=t0)
                await session.commit()

                end = t0 + timedelta(seconds=duration + 1)
                data = await breakthrough_service.resolve_channel(session, user, now=end)
                await session.commit()
                assert data["success"] is False
                assert data["character"]["realm_stage"] == 1
                assert data["character"]["realm_progress"] == 70
                assert data["character"]["spirit_stones"] == 200  # 筑基前免费
                assert data["character"]["status"] == "normal"

    _run(_body())


def test_channel_blocks_battle(tmp_path: Path) -> None:
    """读条中开战被互斥拦截。"""
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_bat.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch05@example.com", "闭关者戊")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                character.idle_direction = "none"
                await session.commit()

                await breakthrough_service.start_channel(session, user, now=t0)
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                assert character.status == "breaking_through"

                with pytest.raises(AppError) as exc_info:
                    assert_can_perform(
                        status=character.status,
                        idle_direction="none",
                        activity=Activity.START_BATTLE,
                    )
                assert exc_info.value.code == 40022

                with pytest.raises(AppError):
                    await battle_service.start_pve_battle(session, user, monster_id="murky_frog")

    _run(_body())


def test_channel_idle_zero_gain(tmp_path: Path) -> None:
    """读条中 settle 零产出（锚点可推进）。"""
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_idle.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch06@example.com", "闭关者己")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                character.idle_direction = "spirit"
                character.last_settled_at = t0
                await session.commit()

                # 先停修炼才能开读条
                character.idle_direction = "none"
                await session.commit()
                await breakthrough_service.start_channel(session, user, now=t0)
                await session.commit()

                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                # 模拟异常残留方向：settle 仍零产出
                character.idle_direction = "spirit"
                progress_before = int(character.realm_progress)
                later = t0 + timedelta(seconds=30)
                result = idle_service.settle_idle(character, now=later)
                assert int(character.realm_progress) == progress_before
                assert result.ticks == 0 or result.advanced_only

    _run(_body())


def test_sync_fallback_when_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """flag off 走旧同步 attempt。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)
    monkeypatch.setattr(
        "app.services.breakthrough_service.BreakthroughService._async_enabled",
        staticmethod(lambda: False),
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_sync.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch07@example.com", "同步回退者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user)
                await session.commit()
                assert data["success"] is True
                assert data["character"]["realm_stage"] == 2
                assert "channel" not in data or data.get("channel") is None

    _run(_body())


def test_attempt_compat_starts_channel(tmp_path: Path) -> None:
    """enabled 时 attempt 兼容开读条。"""
    t0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ch_att.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "ch08@example.com", "兼容入口者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user, now=t0)
                await session.commit()
                assert data.get("channel_started") is True
                assert data["character"]["status"] == "breaking_through"

    _run(_body())
