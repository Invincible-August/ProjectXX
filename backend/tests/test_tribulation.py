"""渡劫状态机测试（M5 E4）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import User
from app.domain.tribulation_rules import map_grade_to_tribulation, lower_power_tier
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.tribulation_service import TribulationService, needs_tribulation_for_advance
from app.services.weather_service import clear_weather_state
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "tribulation_enabled", True)
    clear_game_config_cache()
    clear_weather_state()
    yield
    clear_weather_state()
    clear_game_config_cache()


async def _prepare_yuanying_peak(session, email: str, name: str) -> User:
    """注册创角并抬到元婴大圆满满进度。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    character = await character_service.get_character_by_user_id(session, user.id)
    assert character is not None
    character.major_realm = "yuanying"
    character.realm_stage = 4
    character.realm_stage_label = "perfection"
    character.realm_progress = 220000
    character.spirit_stones = 100000
    await session.commit()
    return user


def test_grade_mapping_and_tier_down() -> None:
    """品阶映射与降档。"""
    cfg = get_game_config().tribulation
    dims = map_grade_to_tribulation("heavenly", cfg.grade_to_tribulation)
    assert dims.power_tier == "apocalypse"
    assert dims.count_tier == "myriad"
    assert lower_power_tier("apocalypse") == "jealousy"
    assert lower_power_tier("mercy") == "mercy"


def test_needs_tribulation_yuanying_peak() -> None:
    """元婴圆满跨境需要渡劫；小境界（层进阶）即使已首劫也不渡劫。"""
    from app.db.models.character import Character

    peak = Character(
        user_id=1,
        name="x",
        major_realm="yuanying",
        realm_stage=4,
        realm_stage_label="perfection",
    )
    assert needs_tribulation_for_advance(
        peak,
        advance_type="major",
        target_major="huashen",
    )
    low = Character(
        user_id=1,
        name="y",
        major_realm="body_tempering",
        realm_stage=1,
        realm_stage_label="layer_1",
    )
    assert not needs_tribulation_for_advance(
        low,
        advance_type="layer",
        target_major=None,
    )
    # 已完成首劫：化神期内小境界进阶不渡劫；再跨境才渡劫
    after = Character(
        user_id=1,
        name="z",
        major_realm="huashen",
        realm_stage=1,
        realm_stage_label="early",
        story_flags_json='{"experienced_nodes": [], "first_tribulation_done": true}',
    )
    assert not needs_tribulation_for_advance(
        after,
        advance_type="layer",
        target_major=None,
    )
    assert needs_tribulation_for_advance(
        after,
        advance_type="major",
        target_major="lianxu",
    )


def test_tribulation_flow_fall(tmp_path: Path) -> None:
    """准备→确认→开渡→自动结算→陨落待引渡。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "trib.db") as factory:
            async with factory() as session:
                user = await _prepare_yuanying_peak(session, "trib@example.com", "渡劫者")
                svc = TribulationService(session)
                started = await svc.start_prep(user)
                await session.commit()
                assert started["session"]["phase"] == "preparing"
                await svc.commit_prep(user)
                await session.commit()
                await svc.begin(user)
                await session.commit()
                result = await svc.auto_resolve(user)
                await session.commit()
                assert result["outcome"]["result"] == "fallen"
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                assert character.status == "awaiting_ferry"

    _run(_body())


def test_idle_blocked_during_tribulation(tmp_path: Path) -> None:
    """渡劫中改挂机方向 → 40061。"""
    from app.services.idle_service import IdleService

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "trib_idle.db") as factory:
            async with factory() as session:
                user = await _prepare_yuanying_peak(session, "trib2@example.com", "渡劫挂机")
                await TribulationService(session).start_prep(user)
                await session.commit()
                with pytest.raises(AppError) as exc:
                    await IdleService(session).set_direction(user, "spirit")
                assert exc.value.code == 40061

    _run(_body())
