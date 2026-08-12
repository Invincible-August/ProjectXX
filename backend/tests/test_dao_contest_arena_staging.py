"""道主之争擂台：RSVP 弃权与离场判负。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DaoContest, DaoContestMatch, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.dao_contest_arena import load_arena_state, save_arena_state, _iso
from app.services.dao_contest_service import DaoContestService, _SPECTATE_SLOTS
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run
from tests.contest_staging_helpers import patch_fast_staging


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


def test_rsvp_decline_forfeit_and_settle(tmp_path: Path) -> None:
    """两人报名，一人弃权 → 另一人直通道主战并收口。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "rsvp.db") as factory:
            async with factory() as session:
                lord = await _user_with_fate(
                    session, "rsvp_lord@example.com", "LordRSVP", as_lord=True,
                )
                a = await _user_with_fate(
                    session, "rsvp_a@example.com", "ChallA", as_lord=False,
                )
                b = await _user_with_fate(
                    session, "rsvp_b@example.com", "ChallB", as_lord=False,
                )
                svc = DaoContestService(session)
                patch_fast_staging(svc)
                await svc.register(a)
                await svc.register(b)
                await session.commit()
                await svc.force_start(note="rsvp")
                await session.commit()
                await svc.submit_rsvp(a, accept=True)
                await svc.submit_rsvp(b, accept=False)
                await svc.submit_rsvp(lord, accept=False)  # 道主快照
                contest = (
                    await session.execute(
                        select(DaoContest).order_by(DaoContest.id.desc()).limit(1),
                    )
                ).scalar_one()
                await svc.drain_arena(contest.id)
                await session.commit()
                cur = await svc.get_current(a)
                assert cur["contest"]["status"] == "settled"
                bracket = await svc.get_bracket(a)
                assert any(m["round_kind"] == "lord" for m in bracket["matches"])

    _run(_body())


def test_leave_forfeit_overrides_winner(tmp_path: Path) -> None:
    """演出中离场 → leave_forfeit 覆盖胜者。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "leave.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session, "lf_lord@example.com", "LordLeave", as_lord=True,
                )
                a = await _user_with_fate(
                    session, "lf_a@example.com", "LeaveA", as_lord=False,
                )
                b = await _user_with_fate(
                    session, "lf_b@example.com", "LeaveB", as_lord=False,
                )
                svc = DaoContestService(session)
                patch_fast_staging(svc)
                await svc.register(a)
                await svc.register(b)
                await session.commit()
                await svc.force_start(note="leave")
                await svc.submit_rsvp(a, accept=True)
                await svc.submit_rsvp(b, accept=True)
                contest = (
                    await session.execute(
                        select(DaoContest).order_by(DaoContest.id.desc()).limit(1),
                    )
                ).scalar_one()
                for _ in range(80):
                    await svc.tick_arena(contest.id)
                    await session.refresh(contest)
                    if contest.phase == "playing":
                        break
                    state = load_arena_state(contest)
                    state["phase_ends_at"] = _iso(
                        datetime.now(timezone.utc) - timedelta(seconds=1),
                    )
                    contest.phase_ends_at = datetime.now(timezone.utc) - timedelta(
                        seconds=1,
                    )
                    save_arena_state(contest, state)
                    await session.flush()
                assert contest.phase == "playing"
                playing = list(
                    (
                        await session.execute(
                            select(DaoContestMatch).where(
                                DaoContestMatch.contest_id == contest.id,
                                DaoContestMatch.status == "playing",
                            ),
                        )
                    ).scalars().all(),
                )
                assert playing
                match = playing[0]
                leaver = match.side_a_character_id
                assert leaver is not None
                result = await svc.apply_leave_forfeit(match.id, int(leaver))
                assert result["changed"] is True
                await session.refresh(match)
                assert match.resolve_reason == "leave_forfeit"
                assert match.presence_override is True
                assert match.winner_character_id != leaver or match.side_b_character_id is None

    _run(_body())


def test_adjust_leave_forfeit_skips_remaining_adjust(tmp_path: Path) -> None:
    """整备中一方离场判负 → 立刻跳过剩余整备，不再空等倒计时。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "adjust_leave.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session, "adj_lord@example.com", "AdjLord", as_lord=True,
                )
                a = await _user_with_fate(
                    session, "adj_a@example.com", "AdjA", as_lord=False,
                )
                b = await _user_with_fate(
                    session, "adj_b@example.com", "AdjB", as_lord=False,
                )
                svc = DaoContestService(session)
                # 整备留长倒计时，验证离场后被跳过
                original = svc._contest_cfg

                def _cfg():
                    from dataclasses import replace

                    cfg = original()
                    return replace(
                        cfg,
                        staging_enabled=True,
                        rsvp_seconds=0,
                        arena_first_round_countdown_seconds=0,
                        round_gap_seconds=0,
                        live_adjust_seconds=120,
                        live_prep_seconds=5,
                        live_playback_seconds=20,
                        dev_assume_online=True,
                        leave_during_playback_forfeit=True,
                    )

                svc._contest_cfg = _cfg  # type: ignore[method-assign]
                await svc.register(a)
                await svc.register(b)
                await session.commit()
                await svc.force_start(note="adjust-leave")
                await svc.submit_rsvp(a, accept=True)
                await svc.submit_rsvp(b, accept=True)
                contest = (
                    await session.execute(
                        select(DaoContest).order_by(DaoContest.id.desc()).limit(1),
                    )
                ).scalar_one()

                # 推到 adjust（倒计时未到期）
                for _ in range(80):
                    await svc.tick_arena(contest.id)
                    await session.refresh(contest)
                    if contest.phase == "adjust":
                        break
                    state = load_arena_state(contest)
                    state["phase_ends_at"] = _iso(
                        datetime.now(timezone.utc) - timedelta(seconds=1),
                    )
                    contest.phase_ends_at = datetime.now(timezone.utc) - timedelta(
                        seconds=1,
                    )
                    save_arena_state(contest, state)
                    await session.flush()

                assert contest.phase == "adjust"
                assert contest.phase_ends_at is not None
                # 仍有较长整备窗（配置 120s）；离场后应被跳过
                from app.services.dao_contest_arena import _as_utc

                remaining = (
                    _as_utc(contest.phase_ends_at) - datetime.now(timezone.utc)
                ).total_seconds()
                assert remaining > 30

                adjusting = list(
                    (
                        await session.execute(
                            select(DaoContestMatch).where(
                                DaoContestMatch.contest_id == contest.id,
                                DaoContestMatch.status == "adjusting",
                            ),
                        )
                    ).scalars().all(),
                )
                assert adjusting
                match = adjusting[0]
                leaver = match.side_a_character_id
                assert leaver is not None

                result = await svc.apply_leave_forfeit(match.id, int(leaver))
                assert result["changed"] is True
                await session.refresh(match)
                await session.refresh(contest)

                assert match.resolve_reason == "leave_forfeit"
                assert match.status == "finished"
                # 已离开 adjust：进入 playing / round_gap / idle，不再空等 120s 整备
                assert contest.phase != "adjust"
                state = load_arena_state(contest)
                assert state.get("action") in {
                    "adjust_skip_forfeit",
                    "playback_start",
                    "round_gap",
                    "settled",
                } or contest.phase in ("playing", "round_gap", "idle")

    _run(_body())
