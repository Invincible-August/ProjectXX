"""
跨境品阶掷骰与历史测试（M2）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, breakthrough_service, character_service, grade_service
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run


async def _prepare(session, email: str) -> User:
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
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "offline_preview_threshold_seconds", 300)
    monkeypatch.setattr(
        "app.services.breakthrough_service.BreakthroughService._async_enabled",
        staticmethod(lambda: False),
    )
    clear_game_config_cache()
    yield
    clear_game_config_cache()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", None)
    monkeypatch.setattr(settings, "grade_rng_seed", None)


def test_major_breakthrough_writes_grade_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """跨境成功写入品阶与历史。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)
    monkeypatch.setattr(settings, "grade_rng_seed", 42)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "grade_hist.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "grade@example.com")
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
                assert data["grade"] is not None

                history = await breakthrough_service.list_grade_history(session, user)
                assert len(history) >= 1
                assert history[0]["grade"] == data["grade"]

    _run(_body())


def test_layer_advance_no_grade_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """层内进阶不改变品阶。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "breakthrough_rng_seed", 1)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "grade_layer.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "layer@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.realm_progress = 100
                character.spirit_stones = 200
                await session.commit()

                data = await breakthrough_service.attempt_breakthrough(session, user)
                await session.commit()
                assert data["success"] is True
                assert data["advance_type"] == "layer"
                assert "grade" not in data
                assert data["character"]["breakthrough_grade"] == "none"

    _run(_body())


def test_constitution_bonus_affects_weights() -> None:
    """有主词条 vs 无：良品+权重池不同。"""
    from app.services.realm_config import get_game_config

    grades_cfg = get_game_config().grades
    no_bonus = grade_service._build_adjusted_weights(
        grades_cfg,
        {"main_affix_count": 0, "vitality": 0},
    )
    with_bonus = grade_service._build_adjusted_weights(
        grades_cfg,
        {"main_affix_count": 1, "vitality": 5},
    )
    good_no = next(w for g, w in no_bonus if g.grade_id == "good")
    good_yes = next(w for g, w in with_bonus if g.grade_id == "good")
    assert good_yes > good_no
