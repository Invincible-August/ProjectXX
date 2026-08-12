"""
体力系统单测（M3 · S4/D10）：惰性恢复、扣减、40049、门禁开关。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.domain.stamina import settle_stamina
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.realm_config import clear_game_config_cache
from app.services.stamina_service import StaminaService

from tests.async_db import open_test_session_factory, run_async as _run

_NOW = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)


async def _prepare(session: AsyncSession, email: str, name: str) -> User:
    """注册 + 创角。"""
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
    """开发态配置 + 清配置缓存。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "stamina_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_settle_stamina_lazy_regen() -> None:
    """纯函数：1 点/分钟 → 30 分钟恢复 30 点，封顶 cap。"""
    reading = settle_stamina(
        50,
        _NOW,
        _NOW + timedelta(minutes=30),
        cap=120,
        regen_per_minute=1.0,
    )
    assert reading.current == 80
    # 已满不再涨
    full = settle_stamina(
        119,
        _NOW,
        _NOW + timedelta(hours=10),
        cap=120,
        regen_per_minute=1.0,
    )
    assert full.current == 120
    assert full.next_point_in_seconds == 0
    # 差一点时给出恢复倒计时
    partial = settle_stamina(
        50,
        _NOW,
        _NOW + timedelta(seconds=30),
        cap=120,
        regen_per_minute=1.0,
    )
    assert partial.current == 50
    assert 0 < partial.next_point_in_seconds <= 30


def test_spend_and_insufficient(tmp_path: Path) -> None:
    """扣减成功推进锚点；不足 → 40049 且不扣。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "stamina.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "sta01@example.com", "体力测试者")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                service = StaminaService(session)

                # 创角默认满体力；扣一次 PVE
                state = service.spend(character, "battle_pve", now=_NOW)
                cost = state["cap"] - state["left"]
                assert cost > 0

                # 清空后再扣 → 40049
                character.stamina = 0
                character.stamina_updated_at = _NOW
                with pytest.raises(AppError) as exc:
                    service.spend(character, "battle_pve", now=_NOW)
                assert exc.value.code == 40049
                assert int(character.stamina) == 0

                # 30 分钟后按配置速率恢复
                reading = service.read(character, now=_NOW + timedelta(minutes=30))
                assert reading["left"] == int(30 * reading["regen_per_minute"])

    _run(_body())


def test_gate_disabled_bypasses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STAMINA_ENABLED=false：0 体力也放行且不扣减。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "stamina_off.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "sta02@example.com", "免体力者")
                character = await character_service.get_character_by_user_id(
                    session,
                    user.id,
                )
                assert character is not None
                settings = get_settings()
                monkeypatch.setattr(settings, "stamina_enabled", False)
                character.stamina = 0
                character.stamina_updated_at = _NOW
                state = StaminaService(session).spend(
                    character,
                    "battle_pve",
                    now=_NOW,
                )
                assert state["left"] == 0  # 未扣成负数，直接放行

    _run(_body())
