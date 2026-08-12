"""挂机境界基础速率与加成通道测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.env_preview import build_idle_env_preview
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.calendar_service import clear_calendar_overrides
from app.services.env_preview_service import build_idle_env_bundle, resolve_idle_bonus_channels
from app.services.idle_service import IdleService
from app.services.realm_config import (
    clear_game_config_cache,
    gain_per_tick_for,
    get_game_config,
)
from app.services.weather_service import clear_weather_state
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


def test_gain_per_tick_differs_by_major_realm() -> None:
    """不同大境界基础速率取自 gain_per_tick_by_realm 表。"""
    idle = get_game_config().idle
    body = SimpleNamespace(major_realm="body_tempering")
    jindan = SimpleNamespace(major_realm="jindan")
    body_rate = gain_per_tick_for(body, "spirit")
    jindan_rate = gain_per_tick_for(jindan, "spirit")
    assert body_rate == idle.gain_by_realm["spirit"]["body_tempering"]
    assert jindan_rate == idle.gain_by_realm["spirit"]["jindan"]
    assert jindan_rate > body_rate


def test_gain_per_tick_falls_back_when_major_missing() -> None:
    """未列表境界回落 directions.*_per_tick。"""
    idle = get_game_config().idle
    unknown = SimpleNamespace(major_realm="not_a_real_major")
    assert gain_per_tick_for(unknown, "spirit") == idle.spirit.gain_per_tick
    assert gain_per_tick_for(unknown, "body") == idle.body.gain_per_tick


def test_idle_env_preview_includes_realm_base_and_channel() -> None:
    """预览拆解含 realm_base；通道乘入 effective。"""
    preview = build_idle_env_preview(
        base_per_tick=10,
        shichen_id="si",
        weather_id="clear",
        shichen_mult=1.0,
        weather_mult=1.0,
        tag_mults_breakdown=[],
        clamp_min=0.5,
        clamp_max=1.5,
        shichen_catalog_entry={},
        weather_catalog_entry={},
        shichen_label="巳时",
        weather_label="晴",
        realm_major="jindan",
        realm_label="金丹",
        channel_mults_breakdown=[
            ("constitution", "test", "体质", 1.2),
        ],
        channel_mult=1.2,
    )
    sources = {row["source"] for row in preview["breakdown"]}
    assert "realm_base" in sources
    assert "constitution" in sources
    assert preview["base_per_tick"] == 10
    assert preview["effective_per_tick"] == int(10 * 1.2 * 1.0)


def test_world_bundle_uses_fallback_without_realm_row() -> None:
    """世界预览无角色时不强制 realm_base。"""
    bundle = build_idle_env_bundle(tags=())
    sources = {row["source"] for row in bundle["spirit"]["breakdown"]}
    assert "realm_base" not in sources
    assert bundle["spirit"]["base_per_tick"] == get_game_config().idle.spirit.gain_per_tick


def test_settle_spirit_gain_scales_with_major(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """settle 修灵产出随大境界基础表变化（关闭环境乘区便于整数对比）。"""
    from app.core.config import get_settings
    from app.db.models import User
    from sqlalchemy import select

    settings = get_settings()
    monkeypatch.setattr(settings, "calendar_enabled", False)
    monkeypatch.setattr(settings, "weather_enabled", False)

    async def _settle_as(major: str, db_name: str) -> int:
        async with open_test_session_factory(tmp_path / db_name) as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(
                        password="password123",
                        email=f"{major}@example.com",
                    ),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == f"{major}@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(
                        name="锻体测" if major == "body_tempering" else "金丹测",
                    ),
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.major_realm = major
                character.idle_direction = "spirit"
                character.spirit_stones = 10000
                character.cultivation_points = 0
                now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = now - timedelta(seconds=60)
                await session.commit()
                channel_mult, _ = await resolve_idle_bonus_channels(session, character)
                result = IdleService(session).settle(
                    character,
                    now=now,
                    channel_mult=channel_mult,
                )
                await session.commit()
                assert result.ticks == 1
                expected_base = gain_per_tick_for(character, "spirit")
                assert expected_base == get_game_config().idle.gain_by_realm["spirit"][major]
                # 无环境时：产出 = floor(base * channel)；默认体质通道 ×1
                assert result.gained_cultivation == int(expected_base * channel_mult)
                return int(result.gained_cultivation)

    low = _run(_settle_as("body_tempering", "low.db"))
    high = _run(_settle_as("jindan", "high.db"))
    assert high > low
    assert high == get_game_config().idle.gain_by_realm["spirit"]["jindan"]
    assert low == get_game_config().idle.gain_by_realm["spirit"]["body_tempering"]


def test_constitution_idle_mult_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """装备词条含 idle_mult 时通道乘区抬高 settle 产出。"""
    from app.core.config import get_settings
    from app.db.models import User
    from app.db.models.constitution import ConstitutionItem, ConstitutionSlot
    from sqlalchemy import select

    settings = get_settings()
    monkeypatch.setattr(settings, "calendar_enabled", False)
    monkeypatch.setattr(settings, "weather_enabled", False)

    clear_game_config_cache()
    iron = get_game_config().constitution.items["sample_main_affix_iron"]
    iron.effects["idle_mult"] = 1.5

    async def _run_case() -> tuple[float, int, int]:
        async with open_test_session_factory(tmp_path / "cons.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="cons@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "cons@example.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="体质钩子"),
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None

                item_row = (
                    await session.execute(
                        select(ConstitutionItem).where(
                            ConstitutionItem.character_id == character.id,
                            ConstitutionItem.def_id == "sample_main_affix_iron",
                        ),
                    )
                ).scalar_one()
                slot = (
                    await session.execute(
                        select(ConstitutionSlot).where(
                            ConstitutionSlot.character_id == character.id,
                            ConstitutionSlot.slot_type == "main",
                            ConstitutionSlot.slot_index == 0,
                        ),
                    )
                ).scalar_one()
                slot.item_instance_id = item_row.id
                item_row.is_equipped = True
                await session.commit()

                channel_mult, items = await resolve_idle_bonus_channels(session, character)
                assert abs(channel_mult - 1.5) < 1e-9
                assert any(i.source == "constitution" and i.mult == 1.5 for i in items)

                character.idle_direction = "spirit"
                character.spirit_stones = 10000
                character.cultivation_points = 0
                now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = now - timedelta(seconds=60)
                await session.commit()

                base = gain_per_tick_for(character, "spirit")
                result = IdleService(session).settle(
                    character,
                    now=now,
                    channel_mult=channel_mult,
                )
                await session.commit()
                return channel_mult, base, int(result.gained_cultivation)

    try:
        channel_mult, base, gained = _run(_run_case())
        assert abs(channel_mult - 1.5) < 1e-9
        assert gained == int(base * 1.5)
    finally:
        iron.effects.pop("idle_mult", None)
        clear_game_config_cache()