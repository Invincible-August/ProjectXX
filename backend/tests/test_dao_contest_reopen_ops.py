"""运营重新开放报名：settled → registration。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DaoContest, DaoContestEntry, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.dao_contest_service import DaoContestService, _SPECTATE_SLOTS
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run
from tests.contest_staging_helpers import force_start_and_settle


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "gm_enabled", True)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "dao_system_enabled", True)
    monkeypatch.setattr(settings, "dao_lord_enabled", True)
    clear_game_config_cache()
    _SPECTATE_SLOTS.clear()
    yield
    clear_game_config_cache()
    _SPECTATE_SLOTS.clear()


async def _user_with_fate(session, email: str, name: str, *, as_lord: bool):
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
    kwargs: dict = {
        "force_true_immortal": True,
        "lock_fate_dao": "dao_flame",
        "set_dao_level": 2,
    }
    if as_lord:
        kwargs["set_dao_lord"] = "dao_flame"
    await GmService(session).gm_set_character(user, **kwargs)
    await session.commit()
    return user


def test_ops_reopen_clears_entries_and_allows_reregister(tmp_path: Path) -> None:
    """收口后 reopen → registration，可再报名。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "reopen.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session, "re_lord@example.com", "ReLord", as_lord=True,
                )
                a = await _user_with_fate(
                    session, "re_a@example.com", "ReChallA", as_lord=False,
                )
                b = await _user_with_fate(
                    session, "re_b@example.com", "ReChallB", as_lord=False,
                )
                svc = DaoContestService(session)
                await svc.register(a)
                await svc.register(b)
                await session.commit()
                closed = await force_start_and_settle(svc, a, b)
                assert closed["contest"]["status"] == "settled"

                reopened = await svc.reopen_for_ops(note="test")
                await session.commit()
                assert reopened["contest"]["status"] == "registration"
                assert reopened["ops_hints"]["can_force_start"] is True
                assert reopened["contest"]["total_entrants"] == 0

                entries = list(
                    (
                        await session.execute(select(DaoContestEntry))
                    ).scalars().all(),
                )
                assert entries == []

                again = await svc.register(a)
                assert again["me"]["registered"] is True
                row = (
                    await session.execute(select(DaoContest).order_by(DaoContest.id.desc()))
                ).scalars().first()
                assert row is not None
                assert row.status == "registration"

    _run(_body())
