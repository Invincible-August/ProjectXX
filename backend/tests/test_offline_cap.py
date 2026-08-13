"""
离线帽与 pending/claim 测试（M2）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service, idle_service
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
    monkeypatch.setattr(settings, "idle_tick_seconds", 60)
    monkeypatch.setattr(settings, "offline_preview_threshold_seconds", 300)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_offline_cap_12h_free(tmp_path: Path) -> None:
    """离线 20h + free 帽 → pending 最多 12h tick。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_cap.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "offline@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "spirit"
                character.spirit_stones = 100000
                await session.commit()

                now = start + timedelta(hours=20)
                pending = idle_service.prepare_offline_or_settle(character, now=now)
                assert isinstance(pending, dict)
                assert pending["capped"] is True
                assert pending["cap_hours"] == 12.0
                # 12h = 720 tick at 60s
                assert pending["settled_ticks"] == 720
                assert pending["gained_cultivation"] == 7200
                assert character.cultivation_points == 0

                claim = idle_service.claim_offline_pending(character, now=now)
                await session.commit()
                assert claim["settled_ticks"] == 720
                assert character.cultivation_points == 7200
                assert character.pending_offline_json is None

    _run(_body())


def test_pending_blocks_online_settle(tmp_path: Path) -> None:
    """有 pending 再 sync 不双算。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_no_double.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "nodouble@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.pending_offline_json = json.dumps(
                    {"gained_cultivation": 100, "spent_spirit_stones": 10},
                )
                character.cultivation_points = 0
                await session.commit()

                settle = idle_service.settle_idle(character)
                assert settle.ticks == 0
                assert character.cultivation_points == 0

                data = await idle_service.sync_idle(session, user)
                assert data["settled_ticks"] == 0
                assert data["offline_pending"] is not None

    _run(_body())


def test_claim_without_pending_40031(tmp_path: Path) -> None:
    """无 pending claim → 40031。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_claim.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "noclaim@example.com")
                with pytest.raises(AppError) as exc_info:
                    await idle_service.claim_offline(session, user)
                assert exc_info.value.code == 40031

    _run(_body())


def test_sync_long_offline_creates_pending_not_full_credit(tmp_path: Path) -> None:
    """HTTP 级 sync：长离线只写 pending，不无帽全额入池。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_sync_cap.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "synccap@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "spirit"
                character.spirit_stones = 100000
                character.cultivation_points = 0
                await session.commit()

                now = start + timedelta(hours=20)
                data = await idle_service.sync_idle(session, user, now=now)
                await session.commit()
                await session.refresh(character)

                assert data["offline_pending"] is not None
                assert data["offline_pending"]["capped"] is True
                assert data["offline_pending"]["settled_ticks"] == 720
                # 未领取前池仍为 0
                assert character.cultivation_points == 0
                assert character.pending_offline_json is not None
                assert data["settled_ticks"] == 0

    _run(_body())


def test_get_me_long_offline_creates_pending_not_full_credit(tmp_path: Path) -> None:
    """GET me：长离线写 pending，不绕过 12h 帽全额 settle。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_me_cap.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "mecap@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "spirit"
                character.spirit_stones = 100000
                character.cultivation_points = 0
                await session.commit()

                # 直接改 last_settled_at 后走 get_my_character（内部 ensure pending）
                now = start + timedelta(hours=20)
                # 冻结时间：ensure 用 datetime.now，故手动 prepare 对齐后刷新再 me
                idle_service.ensure_offline_pending(character, now=now)
                await session.commit()

                public = await character_service.get_my_character(session, user)
                assert public.offline_pending is not None
                assert public.offline_pending["capped"] is True
                assert public.cultivation_points == 0

    _run(_body())


def test_claim_insufficient_stones_40038(tmp_path: Path) -> None:
    """claim 时灵石不足 → 40038，不扣成负数。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_claim_stones.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "claimstone@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                character.pending_offline_json = json.dumps(
                    {
                        "gained_cultivation": 100,
                        "gained_body": 0,
                        "gained_crafting": 0,
                        "spent_spirit_stones": 50,
                        "settled_ticks": 10,
                    },
                )
                character.spirit_stones = 10
                await session.commit()

                with pytest.raises(AppError) as exc_info:
                    await idle_service.claim_offline(session, user)
                assert exc_info.value.code == 40038
                await session.refresh(character)
                assert character.spirit_stones == 10
                assert character.pending_offline_json is not None

    _run(_body())


def test_online_presence_long_gap_auto_settles_no_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WS 仍在线时：长缺口带帽直接入账，不留下 offline_pending。"""

    class _OnlinePresence:
        def is_online(self, character_id: int) -> bool:
            _ = character_id
            return True

    monkeypatch.setattr(
        "app.services.presence_service.get_presence",
        lambda: _OnlinePresence(),
    )

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "offline_online_auto.db") as factory:
            async with factory() as session:
                user = await _prepare(session, "onlineauto@example.com")
                character = await character_service.get_character_by_user_id(session, user.id)
                assert character is not None
                start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
                character.last_settled_at = start
                character.idle_direction = "spirit"
                character.spirit_stones = 100000
                character.cultivation_points = 0
                await session.commit()

                now = start + timedelta(minutes=20)
                result = idle_service.prepare_offline_or_settle(character, now=now)
                await session.commit()

                assert not isinstance(result, dict)
                assert character.pending_offline_json is None
                assert character.cultivation_points > 0
                assert result is not None
                assert result.ticks == 20  # 20min / 60s tick

    _run(_body())
