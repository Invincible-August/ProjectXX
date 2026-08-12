"""Party invite / accept / reject with online gate (monkeypatched)."""

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
from app.services.friend_service import FriendService
from app.services.realm_config import clear_game_config_cache
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
    monkeypatch.setattr(settings, "chat_system_enabled", True)
    monkeypatch.setattr(settings, "chat_ws_push_enabled", False)
    # Force online gate True even if party_dev_assume_online is off
    monkeypatch.setattr(
        ChatService,
        "is_character_online_for_party",
        lambda self, character_id: True,
    )
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


def test_party_invite_accept_flow(tmp_path: Path) -> None:
    """Create empty → invite friend → accept → party channel works; reject path."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "party_invite.db") as factory:
            async with factory() as session:
                a = await _register(session, "pi_a@example.com", "队甲")
                b = await _register(session, "pi_b@example.com", "队乙")
                c = await _register(session, "pi_c@example.com", "队丙")

                # 先结为道友
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

                # create = 空队，不可再强制拉人
                created = await chat.party_action(a, action="create")
                await session.commit()
                assert created["party"] is not None
                assert len(created["party"]["members"]) == 1

                me_b = await chat.party_me(b)
                assert me_b["party"] is None
                assert me_b["pending_invites"] == []

                invited = await chat.party_action(
                    a,
                    action="invite",
                    peer_name="队乙",
                )
                await session.commit()
                invite = invited["invite"]
                assert invite is not None
                assert invite["status"] == "pending"

                me_b2 = await chat.party_me(b)
                assert len(me_b2["pending_invites"]) == 1
                assert me_b2["pending_invites"][0]["id"] == invite["id"]

                accepted = await chat.party_action(
                    b,
                    action="accept",
                    invite_id=int(invite["id"]),
                )
                await session.commit()
                party = accepted["party"]
                assert party is not None
                assert len(party["members"]) == 2
                cref = party["channel_ref"]

                await chat.send(a, channel_type="party", body_zh="集合出发")
                await session.commit()
                hist = await chat.history(b, channel_ref=cref)
                assert any(m["body_zh"] == "集合出发" for m in hist["items"])

                with pytest.raises(AppError) as exc:
                    await chat.history(c, channel_ref=cref)
                assert exc.value.code == 40130

                # 离队后另起邀请再拒绝
                await chat.party_action(b, action="leave")
                await session.commit()
                # 队甲可能已解散（仅一人）；再邀需重建
                me_a = await chat.party_me(a)
                if me_a["party"] is None:
                    await chat.party_action(a, action="create")
                    await session.commit()

                invited2 = await chat.party_action(
                    a,
                    action="invite",
                    peer_name="队乙",
                )
                await session.commit()
                inv2 = invited2["invite"]
                rejected = await chat.party_action(
                    b,
                    action="reject",
                    invite_id=int(inv2["id"]),
                )
                await session.commit()
                assert rejected["invite"]["status"] == "rejected"
                me_b3 = await chat.party_me(b)
                assert me_b3["party"] is None
                assert me_b3["pending_invites"] == []

    _run(_body())


def test_party_invite_requires_online(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline gate rejects invite when helper returns False."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "party_offline.db") as factory:
            async with factory() as session:
                a = await _register(session, "po_a@example.com", "离甲")
                b = await _register(session, "po_b@example.com", "离乙")
                friends = FriendService(session)
                applied = await friends.apply(
                    a,
                    target_character_id=None,
                    target_name="离乙",
                )
                await session.commit()
                await friends.accept(b, int(applied["friendship_id"]))
                await session.commit()

                monkeypatch.setattr(
                    ChatService,
                    "is_character_online_for_party",
                    lambda self, character_id: False,
                )
                chat = ChatService(session)
                with pytest.raises(AppError) as exc:
                    await chat.party_action(a, action="invite", peer_name="离乙")
                assert "不在线" in exc.value.message

    _run(_body())


def test_party_kick_and_leader_only_invite(tmp_path: Path) -> None:
    """仅队长可邀请/踢人；成员摘要含境界等字段。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "party_kick.db") as factory:
            async with factory() as session:
                a = await _register(session, "pk_a@example.com", "踢甲")
                b = await _register(session, "pk_b@example.com", "踢乙")
                c = await _register(session, "pk_c@example.com", "踢丙")
                friends = FriendService(session)
                for name, peer in (("踢乙", b), ("踢丙", c)):
                    applied = await friends.apply(
                        a,
                        target_character_id=None,
                        target_name=name,
                    )
                    await session.commit()
                    await friends.accept(peer, int(applied["friendship_id"]))
                    await session.commit()
                # 乙丙也结友，便于乙尝试邀请
                ab = await friends.apply(b, target_character_id=None, target_name="踢丙")
                await session.commit()
                await friends.accept(c, int(ab["friendship_id"]))
                await session.commit()

                chat = ChatService(session)
                await chat.party_action(a, action="create")
                await session.commit()
                inv_b = await chat.party_action(a, action="invite", peer_name="踢乙")
                await session.commit()
                await chat.party_action(
                    b,
                    action="accept",
                    invite_id=int(inv_b["invite"]["id"]),
                )
                await session.commit()

                me = await chat.party_me(a)
                members = me["party"]["members"]
                assert len(members) == 2
                for m in members:
                    assert "major_realm" in m
                    assert "status_name" in m
                    assert "base_atk" in m
                    assert "technique_summary" in m
                    assert "constitution_equipped" in m
                    assert "online" in m

                # 非队长不可邀请
                with pytest.raises(AppError) as exc_invite:
                    await chat.party_action(b, action="invite", peer_name="踢丙")
                assert "队长" in exc_invite.value.message

                # 队长踢人
                kicked = await chat.party_action(a, action="kick", peer_name="踢乙")
                await session.commit()
                assert kicked["party"] is not None
                assert len(kicked["party"]["members"]) == 1
                me_b = await chat.party_me(b)
                assert me_b["party"] is None

                # 非队长不可踢（重新拉乙入队后由乙踢甲）
                inv_b2 = await chat.party_action(a, action="invite", peer_name="踢乙")
                await session.commit()
                await chat.party_action(
                    b,
                    action="accept",
                    invite_id=int(inv_b2["invite"]["id"]),
                )
                await session.commit()
                with pytest.raises(AppError) as exc_kick:
                    await chat.party_action(b, action="kick", peer_name="踢甲")
                assert "队长" in exc_kick.value.message

    _run(_body())
