"""M6-D06 P2～P4：淘汰 / 道主决战 / 直播观战。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DaoContestMatch, DaoLordship, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
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


def test_contest_bracket_and_lord_match(tmp_path: Path) -> None:
    """两人报名立刻开赛 → 决赛 + 道主决战落库；可拉对阵与战报。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_p2.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session,
                    "p2_lord@example.com",
                    "炎道主P2",
                    as_lord=True,
                )
                c1 = await _user_with_fate(
                    session,
                    "p2_a@example.com",
                    "挑战甲",
                    as_lord=False,
                )
                c2 = await _user_with_fate(
                    session,
                    "p2_b@example.com",
                    "挑战乙",
                    as_lord=False,
                )
                svc = DaoContestService(session)
                await svc.register(c1)
                await svc.register(c2)
                await session.commit()

                closed = await force_start_and_settle(svc, c1, c2)
                await session.commit()
                assert closed["contest"]["status"] == "settled"
                assert closed["contest"]["match_count"] >= 2
                assert closed["contest"]["bracket_ready"] is True

                bracket = await svc.get_bracket(c1)
                kinds = {m["round_kind"] for m in bracket["matches"]}
                assert "final" in kinds or "semi" in kinds
                assert "lord" in kinds

                lord_matches = [m for m in bracket["matches"] if m["round_kind"] == "lord"]
                assert len(lord_matches) == 1
                mid = lord_matches[0]["id"]
                report = await svc.get_match_report(c1, mid)
                assert "report" in report
                assert report["match"]["is_live_round"] is True

                # 收口后直播窗可能已结束：仍可拉战报；单槽逻辑在直播窗内测
                if report.get("live_active"):
                    spec = await svc.spectate_match(c1, mid)
                    assert spec.get("spectating") is True
                    other_live = [
                        m
                        for m in bracket["matches"]
                        if m["id"] != mid and m.get("can_spectate_live")
                    ]
                    if other_live:
                        with pytest.raises(AppError) as exc2:
                            await svc.spectate_match(c1, other_live[0]["id"])
                        assert exc2.value.code == 40097

                rows = list(
                    (await session.execute(select(DaoContestMatch))).scalars().all(),
                )
                assert len(rows) >= 2

    _run(_body())


def test_contest_single_entrant_lord_match(tmp_path: Path) -> None:
    """单人报名 → 跳过淘汰直战道主。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_p3.db") as factory:
            async with factory() as session:
                lord_user = await _user_with_fate(
                    session,
                    "p3_lord@example.com",
                    "卫冕道主",
                    as_lord=True,
                )
                chal = await _user_with_fate(
                    session,
                    "p3_chal@example.com",
                    "唯一挑战",
                    as_lord=False,
                )
                svc = DaoContestService(session)
                await svc.register(chal)
                await session.commit()
                closed = await force_start_and_settle(svc, chal, lord_user)
                await session.commit()
                assert closed["contest"]["status"] == "settled"
                tracks = (closed["contest"].get("summary") or {}).get("tracks") or []
                assert tracks
                assert tracks[0]["entrant_count"] == 1
                assert tracks[0].get("match_ids") or tracks[0].get("lord_match_id")

                bracket = await svc.get_bracket(chal, dao_id="dao_flame")
                kinds = [m["round_kind"] for m in bracket["matches"]]
                assert "lord" in kinds

                # 道主仍存在（卫冕或更替后仍有席位）
                lord = (
                    await session.execute(
                        select(DaoLordship).where(DaoLordship.dao_id == "dao_flame"),
                    )
                ).scalar_one_or_none()
                assert lord is not None
                _ = lord_user  # 保留引用避免未使用告警

    _run(_body())
