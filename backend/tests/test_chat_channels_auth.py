"""M7 L4：五频道鉴权 + 世界/私聊互通 + 宗门拒散修 + 组队。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.chat_service import ChatService, reset_chat_rate_buckets_for_tests
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from app.services.sect_service import SectService
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "gm_enabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "friends_system_enabled", True)
    monkeypatch.setattr(settings, "sect_system_enabled", True)
    monkeypatch.setattr(settings, "chat_system_enabled", True)
    monkeypatch.setattr(settings, "chat_ws_push_enabled", False)
    clear_game_config_cache()
    reset_chat_rate_buckets_for_tests()
    yield
    clear_game_config_cache()
    reset_chat_rate_buckets_for_tests()


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


def test_world_and_dm_two_accounts(tmp_path: Path) -> None:
    """两账号世界互通；私聊双方可读历史。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "chat_world.db") as factory:
            async with factory() as session:
                a = await _register(session, "ca@example.com", "聊甲")
                b = await _register(session, "cb@example.com", "聊乙")
                chat = ChatService(session)
                sent = await chat.send(
                    a,
                    channel_type="world",
                    body_zh="天下修士共听此言",
                )
                await session.commit()
                assert sent["channel_ref"] == "world"
                hist_b = await chat.history(b, channel_ref="world")
                assert any(m["body_zh"] == "天下修士共听此言" for m in hist_b["items"])

                dm = await chat.send(
                    a,
                    channel_type="dm",
                    body_zh="道友安好",
                    peer_name="聊乙",
                )
                await session.commit()
                cref = dm["channel_ref"]
                hist_a = await chat.history(a, channel_ref=cref)
                hist_peer = await chat.history(b, channel_ref=cref)
                assert hist_a["items"][-1]["body_zh"] == "道友安好"
                assert hist_peer["items"][-1]["body_zh"] == "道友安好"

                # 第三方不可读私聊
                c = await _register(session, "cc@example.com", "聊丙")
                with pytest.raises(AppError) as exc:
                    await chat.history(c, channel_ref=cref)
                assert exc.value.code == 40130

    _run(_body())


def test_sect_channel_rejects_wanderer(tmp_path: Path) -> None:
    """散修不可发宗门频；入宗后可发。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "chat_sect.db") as factory:
            async with factory() as session:
                a = await _register(session, "cs@example.com", "宗聊甲")
                await GmService(session).gm_set_character(
                    a,
                    major_realm="qi_refining",
                    spirit_stones=10_000,
                )
                await session.commit()
                chat = ChatService(session)
                with pytest.raises(AppError) as exc:
                    await chat.send(a, channel_type="sect", body_zh="散修妄语")
                assert exc.value.code == 40130

                sect = SectService(session)
                await sect.join(a, template_id="qingyun_zong")
                await session.commit()
                sent = await chat.send(a, channel_type="sect", body_zh="本宗弟子报道")
                await session.commit()
                assert sent["channel_ref"].startswith("sect:")

                # mentor 锁定
                with pytest.raises(AppError) as exc2:
                    await chat.send(a, channel_type="mentor", body_zh="师尊在否")
                assert exc2.value.code == 40130

    _run(_body())


def test_party_create_and_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """空队 + 邀请接受后队伍频道可互通；未入队拒 40130。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "chat_party.db") as factory:
            async with factory() as session:
                a = await _register(session, "pa@example.com", "队甲")
                b = await _register(session, "pb@example.com", "队乙")
                c = await _register(session, "pc@example.com", "队丙")
                monkeypatch.setattr(
                    ChatService,
                    "is_character_online_for_party",
                    lambda self, character_id: True,
                )
                from app.services.friend_service import FriendService

                friends = FriendService(session)
                applied = await friends.apply(
                    a,
                    target_character_id=None,
                    target_name="队乙",
                )
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                chat = ChatService(session)
                await chat.party_action(a, action="create")
                await session.commit()
                invited = await chat.party_action(
                    a,
                    action="invite",
                    peer_name="队乙",
                )
                await session.commit()
                accepted = await chat.party_action(
                    b,
                    action="accept",
                    invite_id=int(invited["invite"]["id"]),
                )
                await session.commit()
                party = accepted["party"]
                assert party is not None
                cref = party["channel_ref"]
                await chat.send(a, channel_type="party", body_zh="集合出发")
                await session.commit()
                hist = await chat.history(b, channel_ref=cref)
                assert any(m["body_zh"] == "集合出发" for m in hist["items"])
                with pytest.raises(AppError) as exc:
                    await chat.history(c, channel_ref=cref)
                assert exc.value.code == 40130

                # 敏感词占位
                filtered = await chat.send(
                    a,
                    channel_type="world",
                    body_zh="含违禁词样例的话",
                )
                assert "*" in filtered["message"]["body_zh"]

    _run(_body())


def test_rate_limit_40131(tmp_path: Path) -> None:
    """限速触发 40131。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "chat_rate.db") as factory:
            async with factory() as session:
                a = await _register(session, "ra@example.com", "速甲")
                from app.services.realm_config import get_game_config

                cfg = get_game_config()
                object.__setattr__(cfg.chat, "rate_max_messages", 2)
                object.__setattr__(cfg.chat, "rate_window_sec", 60)
                chat = ChatService(session)
                await chat.send(a, channel_type="world", body_zh="一")
                await chat.send(a, channel_type="world", body_zh="二")
                with pytest.raises(AppError) as exc:
                    await chat.send(a, channel_type="world", body_zh="三")
                assert exc.value.code == 40131

    _run(_body())
