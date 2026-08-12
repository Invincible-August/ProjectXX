"""
挂机惰性结算测试（M1 + M2 三向）。

覆盖：修灵/炼体/制造业产出、灵石不足停滞、body 方向可切换。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service, idle_service
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
    """注册并创角。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    from app.db.models import User as UserModel
    from sqlalchemy import select

    result = await session.execute(select(UserModel).where(UserModel.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _reload_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例重置配置缓存，并用短 tick 加速。

    M5 环境修正（时辰×天气）在 ``test_env_modifiers_idle`` 单独覆盖；
    本文件断言裸增益，故关闭 CALENDAR/WEATHER 以免天气滚动破坏确定性。
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "idle_tick_seconds", 60)
    monkeypatch.setattr(settings, "offline_preview_threshold_seconds", 300)
    # 关闭 M5 环境乘区，保证 tick 收益断言稳定
    monkeypatch.setattr(settings, "calendar_enabled", False)
    monkeypatch.setattr(settings, "weather_enabled", False)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_settle_gains_cultivation_over_ticks(tmp_path: Path) -> None:
    """修灵 + 有石 + 前进 N tick → 修为池按公式变化。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_gain.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "idle01@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "spirit"
                character.spirit_stones = 1000
                character.cultivation_points = 0
                await session.commit()

                now = start + timedelta(seconds=180)
                settle = idle_service.settle_idle(character, now=now)
                assert settle.ticks == 3
                assert settle.gained_cultivation == 30
                assert settle.gained_body == 0
                assert settle.gained_crafting == 0
                assert settle.spent_spirit_stones == 3
                assert character.cultivation_points == 30
                assert character.spirit_stones == 997

    _run(_body())


def test_settle_body_direction_gains_body_points(tmp_path: Path) -> None:
    """炼体方向涨炼体度池，修为池不增。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_body_gain.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "body01@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "body"
                character.spirit_stones = 100
                await session.commit()

                now = start + timedelta(seconds=120)
                settle = idle_service.settle_idle(character, now=now)
                assert settle.ticks == 2
                assert settle.gained_body == 16
                assert settle.gained_cultivation == 0
                assert character.body_tempering_points == 16
                assert character.cultivation_points == 0

    _run(_body())


def test_settle_crafting_direction(tmp_path: Path) -> None:
    """制造业方向涨 crafting_exp。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_craft.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craft01@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "crafting"
                character.spirit_stones = 50
                await session.commit()

                now = start + timedelta(seconds=60)
                settle = idle_service.settle_idle(character, now=now)
                assert settle.ticks == 1
                assert settle.gained_crafting == 8
                assert character.crafting_exp == 8

    _run(_body())


def test_settle_stalled_when_no_stones(tmp_path: Path) -> None:
    """灵石不足：is_stalled，池不涨，锚点不飞。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_stall.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "idle02@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "spirit"
                character.spirit_stones = 0
                character.cultivation_points = 50
                await session.commit()

                now = start + timedelta(seconds=600)
                settle = idle_service.settle_idle(character, now=now)
                assert settle.ticks == 0
                assert settle.stalled is True
                assert character.cultivation_points == 50
                assert character.last_settled_at == start
                assert idle_service.is_currently_stalled(character) is True

    _run(_body())


def test_set_direction_body_ok(tmp_path: Path) -> None:
    """M2：切换炼体成功。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_body.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "idle03@example.com")
                data = await idle_service.set_idle_direction(session, user, "body")
                await session.commit()
                assert data["character"]["idle_direction"] == "body"
                assert data["next_tick_at"] is not None

    _run(_body())


def test_set_direction_spirit_ok(tmp_path: Path) -> None:
    """切换修灵成功，并返回 next_tick_at。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_spirit.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "idle04@example.com")
                data = await idle_service.set_idle_direction(session, user, "spirit")
                await session.commit()
                assert data["character"]["idle_direction"] == "spirit"
                assert data["character"]["idle_cultivation_per_tick"] == 10
                assert data["next_tick_at"] is not None

    _run(_body())


def test_set_direction_blocked_when_pending(tmp_path: Path) -> None:
    """有 pending 时切换方向 → 40030。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "idle_pending.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "pend01@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.pending_offline_json = '{"settled_ticks": 1}'
                await session.commit()
                with pytest.raises(AppError) as exc_info:
                    await idle_service.set_idle_direction(session, user, "spirit")
                assert exc_info.value.code == 40030

    _run(_body())
