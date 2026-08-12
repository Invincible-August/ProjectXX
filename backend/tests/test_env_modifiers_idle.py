"""环境修正接入挂机测试（M5 E3）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.domain.env_modifiers import combine_env_multipliers, resolve_idle_cultivation_mult
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.calendar_service import clear_calendar_overrides, set_gm_force_shichen
from app.services.idle_service import IdleService
from app.services.realm_config import clear_game_config_cache
from app.services.weather_service import clear_weather_state, set_gm_force_weather
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "idle_tick_seconds", 60)
    clear_game_config_cache()
    clear_calendar_overrides()
    clear_weather_state()
    yield
    clear_calendar_overrides()
    clear_weather_state()
    clear_game_config_cache()


def test_combine_env_clamp() -> None:
    """叠加后 clamp。"""
    assert combine_env_multipliers(base=1.0, shichen_mult=2.0, weather_mult=2.0) == 1.5
    assert combine_env_multipliers(base=1.0, shichen_mult=0.1, weather_mult=0.1) == 0.5


def test_idle_env_multiplier_differs_by_shichen(tmp_path: Path) -> None:
    """不同时辰 settle 产出可测差异。"""
    from app.db.models import User
    from sqlalchemy import select

    async def _settle_with(force_shichen: str, db_name: str) -> int:
        set_gm_force_shichen(force_shichen)
        set_gm_force_weather("clear")
        async with open_test_session_factory(tmp_path / db_name) as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(
                        password="password123",
                        email=f"{force_shichen}@example.com",
                    ),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == f"{force_shichen}@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name=f"择时{force_shichen}"),
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.idle_direction = "spirit"
                character.spirit_stones = 10000
                now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = now - timedelta(seconds=60)
                await session.commit()
                result = IdleService(session).settle(character, now=now)
                await session.commit()
                return result.gained_cultivation

    dawn_gain = _run(_settle_with("dawn", "idle_dawn.db"))
    dusk_gain = _run(_settle_with("dusk", "idle_dusk.db"))
    # dawn 1.05 * clear 1.05 > dusk 0.98 * clear 1.05
    assert dawn_gain >= dusk_gain
    assert resolve_idle_cultivation_mult(
        shichen_id="dawn",
        weather_id="clear",
        shichen_table={"dawn": 1.05},
        weather_table={"clear": 1.05},
    ) > resolve_idle_cultivation_mult(
        shichen_id="dusk",
        weather_id="clear",
        shichen_table={"dusk": 0.98},
        weather_table={"clear": 1.05},
    )
