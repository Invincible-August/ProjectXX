"""运营跳过整备/等待并推进至对战演出。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DaoContest, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.dao_contest_service import DaoContestService, _SPECTATE_SLOTS
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run
from dataclasses import replace


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


def test_ops_advance_skips_adjust_into_playing(tmp_path: Path) -> None:
    """长整备下运营 advance → 进入 playing（或收口）。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "ops_advance.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session, "adv_lord@example.com", "AdvLord", as_lord=True,
                )
                a = await _user_with_fate(
                    session, "adv_a@example.com", "AdvA", as_lord=False,
                )
                b = await _user_with_fate(
                    session, "adv_b@example.com", "AdvB", as_lord=False,
                )
                svc = DaoContestService(session)
                original = svc._contest_cfg

                def _cfg():
                    cfg = original()
                    return replace(
                        cfg,
                        staging_enabled=True,
                        rsvp_seconds=0,
                        arena_first_round_countdown_seconds=0,
                        round_gap_seconds=0,
                        live_adjust_seconds=180,
                        live_prep_seconds=5,
                        live_playback_seconds=30,
                        dev_assume_online=True,
                        leave_during_playback_forfeit=True,
                    )

                svc._contest_cfg = _cfg  # type: ignore[method-assign]
                await svc.register(a)
                await svc.register(b)
                await session.commit()
                await svc.force_start(note="adv")
                await svc.submit_rsvp(a, accept=True)
                await svc.submit_rsvp(b, accept=True)

                contest = (
                    await session.execute(
                        select(DaoContest).order_by(DaoContest.id.desc()).limit(1),
                    )
                ).scalar_one()

                # 推到 adjust，但不耗尽 180s
                for _ in range(40):
                    await svc.tick_arena(contest.id)
                    await session.refresh(contest)
                    if contest.phase == "adjust":
                        break
                    # 其它等待阶段用 expire
                    from datetime import datetime, timedelta, timezone

                    from app.services.dao_contest_arena import (
                        _iso,
                        load_arena_state,
                        save_arena_state,
                    )

                    state = load_arena_state(contest)
                    past = datetime.now(timezone.utc) - timedelta(seconds=1)
                    state["phase_ends_at"] = _iso(past)
                    contest.phase_ends_at = past
                    save_arena_state(contest, state)
                    await session.flush()

                assert contest.phase == "adjust"
                payload = await svc.advance_arena_for_ops(
                    note="test",
                    until_playing=True,
                )
                await session.refresh(contest)
                assert payload["ops_hints"]["can_advance_arena"] is (
                    contest.status in ("rsvp", "arena")
                )
                assert contest.phase in ("playing", "round_gap", "idle") or contest.status == "settled"
                assert payload.get("ops_advance", {}).get("steps")
                # 从 adjust 至少推进一步
                steps = payload["ops_advance"]["steps"]
                assert any(s.get("from") == "adjust" for s in steps)

    _run(_body())
