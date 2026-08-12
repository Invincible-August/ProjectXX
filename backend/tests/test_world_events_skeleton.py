"""
世界事件骨架：房间 id / 报名 / Hub 在场人数。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.realm_config import clear_game_config_cache
from app.services.world_event_service import WorldEventService, _REGISTRATIONS
from app.services.ws_hub_service import get_ws_hub
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
    monkeypatch.setattr(settings, "world_events_enabled", True)
    clear_game_config_cache()
    _REGISTRATIONS.clear()
    yield
    _REGISTRATIONS.clear()
    clear_game_config_cache()


def test_world_event_register_creates_room(tmp_path: Path) -> None:
    """开启后报名返回 room_id，并在 Hub 建房；在场人数以 WS 成员为准。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "we_room.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="we_a@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "we_a@example.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="事件甲"),
                )
                await session.commit()

                svc = WorldEventService(session)
                current = await svc.list_current(user)
                assert current["enabled"] is True
                assert current["events"]
                boss = next(e for e in current["events"] if e["id"] == "world_boss_sample")
                assert boss["open"] is True
                assert boss["room_id"] == "world_event:world_boss_sample"
                assert boss["presence_count"] == 0

                hub = get_ws_hub()
                assert hub.room_member_count(boss["room_id"]) == 0
                # ensure_room 已建房
                assert boss["room_id"] in hub._rooms  # noqa: SLF001 — 骨架断言

                result = await svc.register(user, "world_boss_sample")
                assert result["registered"] is True
                assert result["room_id"] == "world_event:world_boss_sample"
                assert result["event"]["registered"] is True
                # 仅报名未 WS join → 在场仍为 0
                assert result["presence_count"] == 0
                assert result["registered_count"] == 1

    _run(_body())
