"""道友列表：修为 / 在线 / 解除。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.friend_service import FriendService
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "friends_system_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _register(session, email: str, name: str):
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
    return user


def test_friends_list_realm_online_and_remove(tmp_path: Path) -> None:
    """结交后列表含境界/在线；可解除。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "friends_rich.db") as factory:
            async with factory() as session:
                a = await _register(session, "fa@example.com", "友甲")
                b = await _register(session, "fb@example.com", "友乙")
                svc = FriendService(session)
                applied = await svc.apply(a, target_character_id=None, target_name="友乙")
                await session.commit()
                fid = int(applied["friendship_id"])
                # 乙接受
                await svc.accept(b, fid)
                await session.commit()

                listed = await svc.list_friends(a)
                assert listed["friend_count"] == 1
                peer = listed["friends"][0]
                assert peer["peer_name"] == "友乙"
                assert peer.get("peer_major_realm")
                assert "online" in peer
                # 列表用真实 Presence（无 DEV 假定）；无 WS 时为离线
                assert peer["online"] is False

                removed = await svc.remove(a, fid)
                await session.commit()
                assert removed["friend_count"] == 0
                listed2 = await svc.list_friends(a)
                assert listed2["friend_count"] == 0

    _run(_body())


def test_friend_profile_privacy_and_snapshot(tmp_path: Path) -> None:
    """遮掩天机拒绝；允许后可查看；快照可刷新。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "friends_profile.db") as factory:
            async with factory() as session:
                a = await _register(session, "pa@example.com", "窥甲")
                b = await _register(session, "pb@example.com", "窥乙")
                svc = FriendService(session)
                applied = await svc.apply(a, target_character_id=None, target_name="窥乙")
                await session.commit()
                await svc.accept(b, int(applied["friendship_id"]))
                await session.commit()

                bch = await character_service.get_character_by_user_id(session, b.id)
                assert bch is not None
                await svc.set_privacy(b, friend_profile_visible=False)
                await session.commit()
                from app.schemas.common import AppError

                with pytest.raises(AppError) as exc:
                    await svc.get_friend_profile(a, bch.id)
                assert exc.value.code == 40130
                assert "遮掩" in exc.value.message

                await svc.set_privacy(b, friend_profile_visible=True)
                await session.commit()
                card = await svc.get_friend_profile(a, bch.id)
                assert card["name"] == "窥乙"
                assert "combat_final" in card
                assert card["source"] in ("live", "snapshot", "fallback")

    _run(_body())
