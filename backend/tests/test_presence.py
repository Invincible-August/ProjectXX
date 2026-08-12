"""Presence / WsHub online index + grace + purpose DEV assume."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.presence_service import (
    PresencePurpose,
    PresenceService,
    get_presence,
    reset_presence_for_tests,
)
from app.services.realm_config import clear_game_config_cache
from app.services.ws_hub_service import WsHubService, get_ws_hub, reset_ws_hub_for_tests
from tests.async_db import run_async


class _FakeWs:
    """Minimal WebSocket stub for Hub register/auth."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        return None


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "development")
    reset_ws_hub_for_tests()
    reset_presence_for_tests()
    clear_game_config_cache()
    yield
    reset_ws_hub_for_tests()
    reset_presence_for_tests()
    clear_game_config_cache()


def test_hub_index_multi_conn_and_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two conns stay online; last disconnect with grace_sec=0 goes offline."""

    async def _run() -> None:
        hub = WsHubService()
        events: list[tuple[int, bool]] = []

        async def _listen(cid: int, online: bool) -> None:
            events.append((cid, online))

        hub.set_presence_listener(_listen)
        monkeypatch.setattr(hub, "_grace_sec", lambda: 0)

        await hub.register("c1", _FakeWs())  # type: ignore[arg-type]
        await hub.register("c2", _FakeWs())  # type: ignore[arg-type]
        await hub.authenticate("c1", user_id=1, character_id=10)
        assert hub.is_character_online(10) is True
        assert events[-1] == (10, True)

        await hub.authenticate("c2", user_id=1, character_id=10)
        assert hub.has_live_connection(10) is True

        await hub.unregister("c1")
        assert hub.is_character_online(10) is True
        assert hub.has_live_connection(10) is True

        await hub.unregister("c2")
        assert hub.has_live_connection(10) is False
        assert hub.is_character_online(10) is False
        assert events[-1] == (10, False)

    run_async(_run())


def test_hub_grace_keeps_online(monkeypatch: pytest.MonkeyPatch) -> None:
    """With grace_sec>0, last disconnect still online until grace cleared."""

    async def _run() -> None:
        hub = WsHubService()
        monkeypatch.setattr(hub, "_grace_sec", lambda: 30)
        monkeypatch.setattr(hub, "_schedule_grace_expiry", lambda *_a, **_k: None)

        await hub.register("c1", _FakeWs())  # type: ignore[arg-type]
        await hub.authenticate("c1", user_id=1, character_id=22)
        await hub.unregister("c1")
        assert hub.has_live_connection(22) is False
        assert hub.is_character_online(22) is True

    run_async(_run())


def test_presence_dev_assume_party_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Party purpose can be assumed online while assist is not."""
    svc = PresenceService()
    monkeypatch.setattr(get_settings(), "app_env", "development")

    fake = SimpleNamespace(
        presence=SimpleNamespace(
            grace_sec=30,
            dev_assume_online=False,
            dev_assume_by_purpose={"party": True, "assist": False},
        ),
        chat=SimpleNamespace(party_dev_assume_online=False),
        trade=SimpleNamespace(face_dev_assume_online=False),
        friends=SimpleNamespace(dev_assume_online=False, assist_dev_assume_online=False),
        avatar=SimpleNamespace(
            friend_assist=SimpleNamespace(assist_dev_assume_online=False),
        ),
        dao_lord=SimpleNamespace(contest=SimpleNamespace(dev_assume_online=False)),
    )
    monkeypatch.setattr(
        "app.services.presence_service.get_game_config",
        lambda: fake,
    )
    monkeypatch.setattr(svc, "is_online", lambda _cid: False)

    assert svc.is_online_for(PresencePurpose.PARTY, 1) is True
    assert svc.is_online_for(PresencePurpose.ASSIST, 1) is False


def test_presence_production_ignores_dev_assume(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production never applies DEV assume."""
    svc = PresenceService()
    monkeypatch.setattr(get_settings(), "app_env", "production")
    fake = SimpleNamespace(
        presence=SimpleNamespace(
            grace_sec=0,
            dev_assume_online=True,
            dev_assume_by_purpose={"party": True},
        ),
        chat=SimpleNamespace(party_dev_assume_online=True),
        trade=SimpleNamespace(face_dev_assume_online=True),
        friends=SimpleNamespace(dev_assume_online=True, assist_dev_assume_online=True),
        avatar=SimpleNamespace(
            friend_assist=SimpleNamespace(assist_dev_assume_online=True),
        ),
        dao_lord=SimpleNamespace(contest=SimpleNamespace(dev_assume_online=True)),
    )
    monkeypatch.setattr(
        "app.services.presence_service.get_game_config",
        lambda: fake,
    )
    monkeypatch.setattr(svc, "is_online", lambda _cid: False)
    assert svc.is_online_for(PresencePurpose.PARTY, 9) is False


def test_get_presence_wires_hub_listener() -> None:
    """get_presence registers Hub listener once."""
    reset_ws_hub_for_tests()
    reset_presence_for_tests()
    p = get_presence()
    hub = get_ws_hub()
    assert hub._presence_listener is not None
    assert p is get_presence()
