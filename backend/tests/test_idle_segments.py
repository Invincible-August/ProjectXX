"""
M5-D11：挂机跨时辰切段 settle 单测。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.domain.idle_segments import group_ticks_by_env
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.idle_service import IdleService
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


def test_group_ticks_by_env_merges_same_key() -> None:
    """同环境键连续 tick 合并为一段。"""
    last = datetime(2026, 8, 7, 0, 0, tzinfo=timezone.utc)

    def resolve(_at: datetime) -> tuple[str, str]:
        return "noon", "clear"

    groups = group_ticks_by_env(last, 5, 60, resolve_env=resolve)
    assert len(groups) == 1
    assert groups[0].tick_count == 5
    assert groups[0].shichen_id == "noon"


def test_group_ticks_by_env_splits_on_change() -> None:
    """环境键变化时切开多段。"""
    last = datetime(2026, 8, 7, 0, 0, tzinfo=timezone.utc)

    def resolve(at: datetime) -> tuple[str, str]:
        # 前 2 tick → dawn；其后 → night
        elapsed = (at - last).total_seconds()
        if elapsed <= 120:
            return "dawn", "clear"
        return "night", "clear"

    groups = group_ticks_by_env(last, 4, 60, resolve_env=resolve)
    assert len(groups) == 2
    assert groups[0].tick_count == 2
    assert groups[0].shichen_id == "dawn"
    assert groups[1].tick_count == 2
    assert groups[1].shichen_id == "night"


def test_memoize_env_resolve_buckets() -> None:
    """同桶只调用底层 resolve 一次。"""
    from app.domain.idle_segments import memoize_env_resolve

    calls: list[datetime] = []

    def resolve(at: datetime) -> tuple[str, str]:
        calls.append(at)
        return "noon", "clear"

    cached = memoize_env_resolve(resolve, bucket_seconds=60)
    t0 = datetime(2026, 8, 7, 0, 0, 10, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 7, 0, 0, 50, tzinfo=timezone.utc)
    assert cached(t0) == ("noon", "clear")
    assert cached(t1) == ("noon", "clear")
    assert len(calls) == 1


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "calendar_enabled", True)
    monkeypatch.setattr(settings, "weather_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _prepare(session: AsyncSession, email: str, name: str) -> User:
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


def test_settle_returns_segments(tmp_path: Path) -> None:
    """在线 settle 响应含 segments，且修为按段汇总。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "seg.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "seg01@example.com", "切段修士")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                character.idle_direction = "spirit"
                character.spirit_stones = 10_000
                # 跨两个时辰槽（默认 slot_seconds=60）
                character.last_settled_at = datetime(
                    2026,
                    1,
                    1,
                    0,
                    0,
                    0,
                    tzinfo=timezone.utc,
                )
                now = character.last_settled_at + timedelta(seconds=150)
                result = IdleService(session).settle(character, now=now)
                await session.commit()
                assert result.ticks > 0
                assert result.segments is not None
                assert len(result.segments) >= 1
                assert sum(int(s["cultivation"]) for s in result.segments) == (
                    result.gained_cultivation
                )

    _run(_body())
