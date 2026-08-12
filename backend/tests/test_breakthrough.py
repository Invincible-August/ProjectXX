"""
突破测试（M1 + M2 realm_progress / 品阶）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, breakthrough_service, character_service
from app.services.realm_config import clear_game_config_cache
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
    """每用例重置配置缓存与 RNG seed；旧用例走同步 attempt。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "offline_preview_threshold_seconds", 300)
    # 本文件覆盖同步路径；真读条见 test_breakthrough_async_channel.py
    monkeypatch.setattr(
        "app.services.breakthrough_service.BreakthroughService._async_enabled",
        staticmethod(lambda: False),
    )
    clear_game_config_cache()
    yield
    clear_game_config_cache()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", None)
    monkeypatch.setattr(settings, "grade_rng_seed", None)


def test_breakthrough_success_layer_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """seed 保证成功：锻体一层 → 二层；扣 realm_progress。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_ok.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bt01@example.com", "突破成功者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user)
                await session.commit()
                assert data["success"] is True
                assert data["advance_type"] == "layer"
                assert data["character"]["realm_stage"] == 2
                assert data["character"]["realm_progress"] == 0
                assert data["character"]["spirit_stones"] == 200  # 筑基前突破免费
                assert data["character"]["breakthrough_grade"] == "none"

    _run(_body())


def test_breakthrough_failure_keeps_ratio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失败：realm_progress 按 keep_ratio 回退。"""
    settings = get_settings()
    import random as _random

    fail_seed = None
    for candidate in range(0, 5000):
        if _random.Random(candidate).random() >= 0.85:
            fail_seed = candidate
            break
    assert fail_seed is not None
    monkeypatch.setattr(settings, "breakthrough_rng_seed", fail_seed)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_fail.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bt02@example.com", "突破失败者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user)
                await session.commit()
                assert data["success"] is False
                assert data["character"]["realm_stage"] == 1
                assert data["character"]["realm_progress"] == 70
                assert data["character"]["spirit_stones"] == 200  # 筑基前免费，失败亦不扣

    _run(_body())


def test_breakthrough_insufficient_realm_progress(tmp_path: Path) -> None:
    """境界进度不足 → 40023。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_low.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bt03@example.com", "进度不足者")
                with pytest.raises(AppError) as exc_info:
                    await breakthrough_service.attempt_breakthrough(session, user)
                assert exc_info.value.code == 40023

    _run(_body())


def test_breakthrough_major_qi_to_foundation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """炼气圆满 → 筑基初期 + 品阶。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)
    monkeypatch.setattr(settings, "grade_rng_seed", 1)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_major.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bt04@example.com", "跨境炼气者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = "qi_refining"
                character.realm_stage = 10
                character.realm_stage_label = "perfection"
                character.realm_progress = 13000
                character.spirit_stones = 500
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user)
                await session.commit()
                assert data["success"] is True
                assert data["advance_type"] == "major"
                assert data["character"]["major_realm"] == "foundation"
                assert "grade" in data
                assert data["character"]["breakthrough_grade"] != "none"
                assert data["character"]["divine_ability_slots"] >= 0
                # 炼气圆满→筑基：扣 major_advance 灵石
                assert data["character"]["spirit_stones"] == 300

    _run(_body())


def test_breakthrough_huashen_peak_cap_returns_40026(tmp_path: Path) -> None:
    """已达化神圆满再突破 → 40026（M5 版本上限）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_cap.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bt05@example.com", "化神上限者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = "huashen"
                character.realm_stage = 4
                character.realm_stage_label = "perfection"
                character.realm_progress = 600000
                character.spirit_stones = 1000
                await session.commit()

                with pytest.raises(AppError) as exc_info:
                    await breakthrough_service.attempt_breakthrough(session, user)
                assert exc_info.value.code == 40026

    _run(_body())


def test_pre_foundation_breakthrough_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """锻体层进阶与锻体→炼气跨境均不扣灵石；灵石为 0 也可突破。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "bt_free.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "bt_free@example.com", "免费突破者")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 0
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user)
                await session.commit()
                assert data["success"] is True
                assert data["spirit_stones_delta"] == 0
                assert data["character"]["spirit_stones"] == 0

    _run(_body())
