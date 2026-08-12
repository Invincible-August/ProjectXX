"""
M4 工坊与背包测试（§10.4）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.craft_service import CraftService
from app.services.gm_service import GmService
from app.services.inventory_service import InventoryService
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    from sqlalchemy import select
    from app.db.models import User as UserModel

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
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_craft_claim_adds_inventory(tmp_path: Path) -> None:
    """配方完成领取 → 背包 +1。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craft01@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job = await craft.start(user, recipe_id="pill_stamina_minor", actor="main")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                from sqlalchemy import select
                from app.db.models.craft_job import CraftJob

                row = await session.get(CraftJob, job["id"])
                assert row is not None
                row.finish_at = now_utc() - timedelta(seconds=1)
                await session.commit()
                await craft.settle_jobs_async(character)
                import random

                result = await craft.claim(user, job["id"], rng=random.Random(0))
                assert result["failed"] is False
                inv = InventoryService(session)
                counts = await inv.material_counts(character.id)
                assert counts.get("stamina_pill_minor", 0) >= 1

    _run(_body())


def test_claim_auto_settles_running_job(tmp_path: Path) -> None:
    """claim 前自动 settle：finish_at 已到但 status 仍为 running 时可领取。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft_auto.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "craftauto@example.com")
                await GmService(session).gm_set_character(
                    user,
                    spirit_stones=5000,
                    set_stamina=200,
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job = await craft.start(user, recipe_id="pill_stamina_minor", actor="main")
                from app.db.models.craft_job import CraftJob

                row = await session.get(CraftJob, job["id"])
                assert row is not None
                row.finish_at = now_utc() - timedelta(seconds=1)
                row.status = "running"
                await session.commit()

                import random

                # 不先调 settle_jobs_async，依赖 claim 内惰性推进
                result = await craft.claim(user, job["id"], rng=random.Random(0))
                assert result["failed"] is False

    _run(_body())


def test_crafting_direction_faster_finish(tmp_path: Path) -> None:
    """本体 crafting 方向开工 → finish_at 早于非 crafting。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "craft2.db") as factory:
            async with factory() as session:
                user_a = await _user_with_character(session, "craftdira@example.com")
                user_b = await _user_with_character(session, "craftdirb@example.com")
                gm = GmService(session)
                await gm.gm_set_character(
                    user_a,
                    spirit_stones=5000,
                    set_stamina=200,
                    idle_direction="crafting",
                    grant_craft_materials=True,
                )
                await gm.gm_set_character(
                    user_b,
                    spirit_stones=5000,
                    set_stamina=200,
                    idle_direction="spirit",
                    grant_craft_materials=True,
                )
                await session.commit()
                craft = CraftService(session)
                job_a = await craft.start(user_a, recipe_id="pill_stamina_minor")
                job_b = await craft.start(user_b, recipe_id="pill_stamina_minor")
                assert job_a["finish_at"] < job_b["finish_at"]

    _run(_body())
