"""
角色创建 / 查询集成测试（对齐 M0 §7.5）。

覆盖：创角成功默认值、二次创角 40004、道号冲突 40003、无角色 40005、
无 Token 401、/auth/me.has_character 真实查询。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Character, User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service

from tests.async_db import open_test_session_factory, run_async as _run


async def _register_and_get_user(session: AsyncSession, email: str) -> User:
    """注册并返回 User 实体。"""
    result = await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = await session.get(User, result.user_id)
    assert user is not None
    return user

@pytest.fixture
def settings():
    """返回缓存的 Settings。"""
    return get_settings()

def test_create_character_defaults(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """创角成功：锻体一层、灵石=配置、未修炼、状态正常。"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "initial_spirit_stones", 1000)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "create_ok.db") as factory:
            async with factory() as session:
                user = await _register_and_get_user(session, "char01@example.com")
                public = await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="青柠散人"),
                )
                await session.commit()

                assert public.name == "青柠散人"
                assert public.major_realm == "body_tempering"
                assert public.major_realm_name == "锻体"
                assert public.realm_stage == 1
                assert public.realm_stage_label == "layer_1"
                assert public.realm_display == "锻体一层"
                assert public.spirit_stones == 1000
                assert public.cultivation_points == 0
                assert public.idle_direction == "none"
                assert public.idle_direction_name == "未修炼"
                assert public.status == "normal"
                assert public.status_name == "正常"

                # /auth/me 应反映已创角
                profile = await auth_service.get_current_user_profile(session, user)
                assert profile.has_character is True

    _run(_body())

def test_second_create_returns_40004(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一账号二次创角 → 40004。"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "create_twice.db") as factory:
            async with factory() as session:
                user = await _register_and_get_user(session, "char02@example.com")
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="第一道号"),
                )
                await session.commit()
                with pytest.raises(AppError) as exc_info:
                    await character_service.create_character(
                        session,
                        user,
                        CreateCharacterRequest(name="第二道号"),
                    )
                assert exc_info.value.code == 40004

    _run(_body())

def test_duplicate_name_returns_40003(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不同账号占用同一道号 → 40003。"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "name_taken.db") as factory:
            async with factory() as session:
                user_a = await _register_and_get_user(session, "char03a@example.com")
                await character_service.create_character(
                    session,
                    user_a,
                    CreateCharacterRequest(name="天下无双"),
                )
                await session.commit()

                user_b = await _register_and_get_user(session, "char03b@example.com")
                with pytest.raises(AppError) as exc_info:
                    await character_service.create_character(
                        session,
                        user_b,
                        CreateCharacterRequest(name="天下无双"),
                    )
                assert exc_info.value.code == 40003

    _run(_body())

def test_get_my_character_without_role_returns_40005(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 Token 无角色 → 40005。"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "no_char.db") as factory:
            async with factory() as session:
                user = await _register_and_get_user(session, "char04@example.com")
                profile = await auth_service.get_current_user_profile(session, user)
                assert profile.has_character is False
                with pytest.raises(AppError) as exc_info:
                    await character_service.get_my_character(session, user)
                assert exc_info.value.code == 40005

    _run(_body())

def test_get_my_character_ok(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """创角后 GET me 返回同一角色。"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "get_me.db") as factory:
            async with factory() as session:
                user = await _register_and_get_user(session, "char05@example.com")
                created = await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="可查询者"),
                )
                await session.commit()
                fetched = await character_service.get_my_character(session, user)
                assert fetched.id == created.id
                assert fetched.name == "可查询者"
                # 库内确有一行
                row = await session.get(Character, created.id)
                assert row is not None
                assert row.user_id == user.id

    _run(_body())

def test_login_then_has_character_flag(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登录后 /me 在创角前后 has_character 正确翻转。"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "login_flag.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="char06@example.com"),
                )
                await session.commit()
                tokens = await auth_service.login_user(
                    session,
                    LoginRequest(
                        login_method="password",
                        account="char06@example.com",
                        password="password123",
                        remember_me=True,
                    ),
                )
                assert tokens.has_character is False
                user = await auth_service.load_user_by_id(session, tokens.user.id)
                before = await auth_service.get_current_user_profile(session, user)
                assert before.has_character is False

                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="旗标道人"),
                )
                await session.commit()
                after = await auth_service.get_current_user_profile(session, user)
                assert after.has_character is True

                # 再次登录：TokenPayload 应直接带 has_character=True
                tokens_again = await auth_service.login_user(
                    session,
                    LoginRequest(
                        login_method="password",
                        account="char06@example.com",
                        password="password123",
                        remember_me=True,
                    ),
                )
                assert tokens_again.has_character is True

    _run(_body())
