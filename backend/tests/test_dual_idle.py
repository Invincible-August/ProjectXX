"""
M4 双线程挂机测试（§10.4）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.avatar_service import AvatarService
from app.services.gm_service import GmService
from app.services.idle_service import IdleService
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


def test_dual_idle_both_threads_gain(tmp_path: Path) -> None:
    """本体+化身双线程同时挂机，两池均涨、灵石按两线程扣。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "dual01@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=5000,
                    idle_direction="spirit",
                )
                await session.commit()
                av_svc = AvatarService(session)
                await av_svc.condense(user)
                await av_svc.set_idle(user, "spirit")
                await session.commit()

                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                avatar = await av_svc.get_avatar_row(character.id)
                assert avatar is not None

                start = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                avatar.last_settled_at = start
                character.cultivation_points = 0
                avatar.cultivation_points = 0
                stones_before = int(character.spirit_stones)
                await session.commit()

                now = start + timedelta(seconds=180)
                idle = IdleService(session)
                dual = await idle.settle_dual_async(character, now=now)
                assert dual.main.ticks == 3
                assert dual.avatar is not None
                assert dual.avatar.ticks == 3
                assert character.cultivation_points > 0
                assert avatar.cultivation_points > 0
                assert character.spirit_stones < stones_before

    _run(_body())


def test_offline_pending_splits_avatar_gains(tmp_path: Path) -> None:
    """D10：长离线 pending 分列 avatar_gains，领取后化身池与锚点更新。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dual_off.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "dualoff@example.com")
                await GmService(session).gm_set_character(
                    user,
                    force_jindan=True,
                    spirit_stones=100000,
                    idle_direction="spirit",
                )
                await session.commit()
                av_svc = AvatarService(session)
                await av_svc.condense(user)
                await av_svc.set_idle(user, "spirit")
                await session.commit()

                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                avatar = await av_svc.get_avatar_row(character.id)
                assert avatar is not None

                start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                avatar.last_settled_at = start
                character.cultivation_points = 0
                avatar.cultivation_points = 0
                await session.commit()

                now = start + timedelta(hours=20)
                idle = IdleService(session)
                pending = await idle.prepare_offline_or_settle_async(character, now=now)
                assert isinstance(pending, dict)
                assert pending["capped"] is True
                assert pending.get("avatar_gains") is not None
                assert int(pending["avatar_gains"]["settled_ticks"]) > 0
                assert int(pending["avatar_gains"]["gained_cultivation"]) > 0
                assert character.cultivation_points == 0
                assert avatar.cultivation_points == 0

                applied = await idle.claim_offline_pending_async(character, now=now)
                await session.commit()
                assert applied.get("avatar_gains") is not None
                assert character.cultivation_points > 0
                assert avatar.cultivation_points > 0
                assert character.pending_offline_json is None

    _run(_body())
