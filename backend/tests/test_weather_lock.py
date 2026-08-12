"""天气锁定与加权抽取测试（M5 E2）。"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.weather_rules import EnvLock, build_env_lock, weighted_pick
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.craft_service import CraftService
from app.services.realm_config import clear_game_config_cache
from app.services.weather_service import WeatherService, clear_weather_state, set_gm_force_weather
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset weather memory + config; relax register."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "craft_enabled", True)
    clear_game_config_cache()
    clear_weather_state()
    yield
    clear_weather_state()
    clear_game_config_cache()


def test_weighted_pick_respects_weights() -> None:
    """权重全在 clear 时应几乎总是 clear。"""
    rng = random.Random(1)
    picks = [weighted_pick({"clear": 100, "rain": 0}, rng) for _ in range(20)]
    assert all(p == "clear" for p in picks)


def test_env_lock_roundtrip() -> None:
    """EnvLock 序列化往返。"""
    lock = build_env_lock("dawn", "thunderstorm")
    assert EnvLock.from_dict(lock.to_dict()) == lock


def test_weather_service_gm_force() -> None:
    """GM 强制天气。"""
    set_gm_force_weather("thunderstorm")
    snap = WeatherService().get_snapshot(
        now=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert snap["weather_id"] == "thunderstorm"
    assert snap["forced"] is True


def test_craft_start_writes_env_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """工坊开工写入 env_lock_json。"""
    from app.core.config import get_settings
    from app.db.models import User
    from sqlalchemy import select

    settings = get_settings()
    monkeypatch.setattr(settings, "stamina_enabled", False)
    set_gm_force_weather("rain")

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_lock.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="wxlock@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "wxlock@example.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="天气锁测试"),
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.spirit_stones = 100000
                await session.commit()

                # 需要有材料：GM 式直接塞库存
                from app.services.inventory_service import InventoryService
                from app.services.realm_config import get_game_config

                inv = InventoryService(session)
                recipes = get_game_config().craft_recipes.recipes
                recipe_id = next(iter(recipes.keys()))
                recipe = recipes[recipe_id]
                for mat in recipe.materials:
                    await inv.add_item(
                        character.id,
                        item_type="material",
                        item_id=mat.item_id,
                        quantity=mat.quantity * 2,
                    )
                await session.commit()

                job = await CraftService(session).start(user, recipe_id=recipe_id)
                await session.commit()
                assert job.get("id")
                # 重新读 ORM
                from app.db.models.craft_job import CraftJob

                row = (
                    await session.execute(select(CraftJob).where(CraftJob.id == job["id"]))
                ).scalar_one()
                assert row.env_lock_json
                lock = json.loads(row.env_lock_json)
                assert lock["weather"] == "rain"
                assert "shichen" in lock

    _run(_body())
