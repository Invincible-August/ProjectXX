"""半决起直播：准备倒计时 + 观众脱敏布阵。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.services import auth_service, character_service
from app.services.dao_contest_service import DaoContestService, _SPECTATE_SLOTS
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run
from tests.contest_staging_helpers import patch_fast_staging
from app.db.models import DaoContest
from datetime import datetime, timedelta, timezone
from app.services.dao_contest_arena import load_arena_state, save_arena_state, _iso


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


def test_live_prep_spectator_hides_formation(tmp_path: Path) -> None:
    """观众准备阶段仅见倒计时；选手可见布阵锁定。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_live.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session,
                    "live_lord@example.com",
                    "直播道主",
                    as_lord=True,
                )
                c1 = await _user_with_fate(
                    session,
                    "live_a@example.com",
                    "选手甲",
                    as_lord=False,
                )
                c2 = await _user_with_fate(
                    session,
                    "live_b@example.com",
                    "选手乙",
                    as_lord=False,
                )
                # 观众：第三人（同道但未上场——再开一号看直播）
                spectator = await _user_with_fate(
                    session,
                    "live_spec@example.com",
                    "观众丙",
                    as_lord=False,
                )
                svc = DaoContestService(session)
                patch_fast_staging(svc)
                await svc.register(c1)
                await svc.register(c2)
                await session.commit()
                await svc.force_start(note="live-prep")
                await session.commit()
                await svc.submit_rsvp(c1, accept=True)
                await svc.submit_rsvp(c2, accept=True)
                # 推进到 playing（保留直播窗）
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
                    # 快进阶段计时
                    state = load_arena_state(contest)
                    state["phase_ends_at"] = _iso(
                        datetime.now(timezone.utc) - timedelta(seconds=1),
                    )
                    contest.phase_ends_at = datetime.now(timezone.utc) - timedelta(
                        seconds=1,
                    )
                    save_arena_state(contest, state)
                    await session.flush()
                await session.commit()
                assert contest.phase == "playing"

                bracket = await svc.get_bracket(c1)
                # 取本人上场的直播场（决赛优先；勿取道主战中败者视角）
                live_matches = [
                    m
                    for m in bracket["matches"]
                    if m["is_live_round"] and m.get("live_active")
                ]
                assert live_matches, "应有直播场次"
                my_id = bracket.get("me_character_id")
                mid = None
                for m in live_matches:
                    sides = {
                        (m.get("side_a") or {}).get("character_id"),
                        (m.get("side_b") or {}).get("character_id"),
                    }
                    if my_id in sides:
                        mid = m["id"]
                        break
                if mid is None:
                    mid = live_matches[0]["id"]

                # 选手视角：准备阶段可见布阵
                as_player = await svc.get_live_state(c1, mid)
                assert as_player["phase"] == "prep"
                assert as_player["viewer_role"] == "participant"
                assert as_player["formation_visible"] is True
                assert as_player["formation"] is not None
                assert as_player["countdown_seconds"] >= 0

                # 观众：无布阵，仅倒计时提示
                await svc.spectate_match(spectator, mid)
                as_spec = await svc.get_live_state(spectator, mid)
                assert as_spec["viewer_role"] == "spectator"
                assert as_spec["phase"] == "prep"
                assert as_spec["formation_visible"] is False
                assert as_spec["formation"] is None
                assert as_spec["spectator_prep_hint_zh"]
                kinds = {t.get("kind") for t in as_spec["visible_ticks"]}
                assert "formation_lock" not in kinds

                # report 接口对观众同样脱敏
                report = await svc.get_match_report(spectator, mid)
                pipe = (report.get("report") or {}).get("live_pipeline") or {}
                assert "formation" not in pipe
                assert report["viewer_role"] == "spectator"

    _run(_body())
