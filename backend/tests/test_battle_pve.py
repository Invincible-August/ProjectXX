"""
教学 PVE 与 GM 测试（M1）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, battle_service, character_service, gm_service
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


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

@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "gm_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()

def test_pve_win_rewards(tmp_path: Path) -> None:
    """锻体一层 atk=10 vs 浊气蛙 hp=80 → 必胜；奖励入账。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pve_win.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "pve01@example.com", "战斗胜者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                before_c = int(character.cultivation_points)
                before_s = int(character.spirit_stones)

                data = await battle_service.start_pve_battle(session, user)
                await session.commit()
                assert data["result"] == "win"
                assert data["monster_id"] == "tutorial_slime"
                assert len(data["rounds"]) > 0
                assert data["rewards"]["cultivation_points"] == 30
                assert data["rewards"]["spirit_stones"] == 20
                assert data["character"]["cultivation_points"] == before_c + 30
                assert data["character"]["spirit_stones"] == before_s + 20

    _run(_body())

def test_pve_unknown_monster(tmp_path: Path) -> None:
    """未知怪 → 40025。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pve_miss.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "pve02@example.com", "打错怪者")
                with pytest.raises(AppError) as exc_info:
                    await battle_service.start_pve_battle(session, user, monster_id="no_such")
                assert exc_info.value.code == 40025

    _run(_body())

def test_pve_blocked_while_cultivating(tmp_path: Path) -> None:
    """修炼中开战 → 40022。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pve_idle.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "pve03@example.com", "修炼中战")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.idle_direction = "spirit"
                await session.commit()
                with pytest.raises(AppError) as exc_info:
                    await battle_service.start_pve_battle(session, user)
                assert exc_info.value.code == 40022

    _run(_body())

def test_gm_set_and_forbidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GM 抬修为成功；非 development → 40310。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "gm.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "gm01@example.com", "GM道人")
                data = await gm_service.gm_set_character(
                    session,
                    user,
                    cultivation_points=500,
                    spirit_stones=50,
                )
                await session.commit()
                assert data["character"]["cultivation_points"] == 500
                assert data["character"]["spirit_stones"] == 50

                settings = get_settings()
                monkeypatch.setattr(settings, "app_env", "production")
                with pytest.raises(AppError) as exc_info:
                    await gm_service.gm_set_character(session, user, cultivation_points=1)
                assert exc_info.value.code == 40310

    _run(_body())


def test_pve_uses_grade_combat_stats(tmp_path: Path) -> None:
    """战斗伤害使用品阶修正后的 atk（与面板一致）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pve_grade.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "pvegrade@example.com", "品阶战力")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                # heavenly atk_mul=1.2；锻体一层 base_atk=10 → 至少 12
                character.breakthrough_grade = "heavenly"
                await session.commit()

                atk, _, _, _ = await character_service.build_combat_stats(session, character)
                assert atk >= 12
                data = await battle_service.start_pve_battle(session, user)
                await session.commit()
                assert data["rounds"][0]["damage"] == atk
                assert data["character"]["base_atk"] == atk

    _run(_body())


def test_gm_whitelist_blocks_other_users(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GM_ALLOWED_USER_IDS 非空时，非白名单用户 → 40311。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "gm_wl.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "gm02@example.com", "非白名单")
                settings = get_settings()
                monkeypatch.setattr(settings, "gm_allowed_user_ids", "99999")
                with pytest.raises(AppError) as exc_info:
                    await gm_service.gm_set_character(session, user, spirit_stones=1)
                assert exc_info.value.code == 40311

    _run(_body())
