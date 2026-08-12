"""DM persistence: trim to dm_history_limit + clear API."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import User
from app.db.models.chat import ChatMessage
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.chat_service import ChatService, reset_chat_rate_buckets_for_tests
from app.services.realm_config import clear_game_config_cache, get_game_config
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
    clear_game_config_cache()
    reset_chat_rate_buckets_for_tests()
    # 放宽限速便于连发
    monkeypatch.setattr(ChatService, "_assert_rate", lambda self, cid: None)
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


def test_dm_trim_keeps_newest_n(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sending past dm_history_limit drops oldest rows."""

    async def _body() -> None:
        base = get_game_config()
        patched = replace(
            base,
            chat=replace(base.chat, dm_history_limit=5, history_limit=100),
        )
        monkeypatch.setattr(
            "app.services.chat_service.get_game_config",
            lambda: patched,
        )

        async with open_test_session_factory(tmp_path / "dm_trim.db") as factory:
            async with factory() as session:
                a = await _register(session, "dmt1@example.com", "私甲")
                b = await _register(session, "dmt2@example.com", "私乙")
                chat = ChatService(session)
                cref = None
                for i in range(8):
                    sent = await chat.send(
                        a,
                        channel_type="dm",
                        body_zh=f"msg-{i}",
                        peer_name="私乙",
                    )
                    cref = sent["channel_ref"]
                    await session.commit()
                    reset_chat_rate_buckets_for_tests()

                assert cref
                count = (
                    await session.execute(
                        select(func.count()).select_from(ChatMessage).where(
                            ChatMessage.channel_ref == cref,
                        ),
                    )
                ).scalar_one()
                assert int(count) == 5
                hist = await chat.history(a, channel_ref=cref)
                bodies = [m["body_zh"] for m in hist["items"]]
                assert bodies == [f"msg-{i}" for i in range(3, 8)]

                # 世界频不受 dm_history_limit 裁剪
                for i in range(6):
                    await chat.send(a, channel_type="world", body_zh=f"w-{i}")
                    await session.commit()
                    reset_chat_rate_buckets_for_tests()
                wcount = (
                    await session.execute(
                        select(func.count()).select_from(ChatMessage).where(
                            ChatMessage.channel_type == "world",
                        ),
                    )
                ).scalar_one()
                assert int(wcount) >= 6

    _run(_body())


def test_dm_clear_and_forbidden(tmp_path: Path) -> None:
    """Clear wipes history; third party cannot clear."""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dm_clear.db") as factory:
            async with factory() as session:
                a = await _register(session, "dmc1@example.com", "清甲")
                b = await _register(session, "dmc2@example.com", "清乙")
                c = await _register(session, "dmc3@example.com", "清丙")
                chat = ChatService(session)
                sent = await chat.send(
                    a,
                    channel_type="dm",
                    body_zh="要被清空",
                    peer_name="清乙",
                )
                await session.commit()
                cref = sent["channel_ref"]
                hist = await chat.history(b, channel_ref=cref)
                assert len(hist["items"]) == 1

                with pytest.raises(AppError) as exc:
                    await chat.clear_dm(c, channel_ref=cref)
                assert exc.value.code == 40130

                cleared = await chat.clear_dm(a, peer_name="清乙")
                await session.commit()
                assert cleared["channel_ref"] == cref
                hist2 = await chat.history(a, channel_ref=cref)
                assert hist2["items"] == []
                hist_b = await chat.history(b, channel_ref=cref)
                assert hist_b["items"] == []

    _run(_body())
