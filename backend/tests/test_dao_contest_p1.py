"""M6-D06 P1：道主之争报名 / 立刻开赛。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import AdminUser, DaoContest, DaoContestEntry, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.admin_ops_service import AdminOpsService
from app.services.admin_rbac import roles_to_storage
from app.services.dao_contest_service import DaoContestService
from app.services.gm_service import GmService
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
    monkeypatch.setattr(settings, "dao_system_enabled", True)
    monkeypatch.setattr(settings, "dao_lord_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


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


def test_dao_contest_register_and_force_start(tmp_path: Path) -> None:
    """有主时非道主可报名；立刻开赛后不可再报。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_p1.db") as factory:
            async with factory() as session:
                lord = await _user_with_fate(
                    session,
                    "contest_lord@example.com",
                    "炎道主",
                    as_lord=True,
                )
                challenger = await _user_with_fate(
                    session,
                    "contest_chal@example.com",
                    "挑战者甲",
                    as_lord=False,
                )
                svc = DaoContestService(session)
                # 道主不可报名
                with pytest.raises(AppError) as exc_lord:
                    await svc.register(lord)
                assert exc_lord.value.code == 40088

                data = await svc.register(challenger)
                await session.commit()
                assert data["me"]["registered"] is True
                assert data["contest"]["status"] == "registration"
                assert data["contest"]["total_entrants"] >= 1

                # 取消再报
                await svc.unregister(challenger)
                await session.commit()
                data2 = await svc.register(challenger)
                await session.commit()
                assert data2["me"]["registered"] is True

                admin = AdminUser(
                    username="contestops",
                    password_hash=hash_password("ops-pass-123"),
                    display_name="ContestOps",
                    roles=roles_to_storage(["viewer", "publisher"]),
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                await session.refresh(admin)

                ops = AdminOpsService(session)
                closed = await ops.force_start_dao_contest(admin, note="test")
                await session.commit()
                assert closed["contest"]["status"] in (
                    "settled",
                    "cancelled",
                    "rsvp",
                    "arena",
                )
                assert closed["contest"]["can_register"] is False

                with pytest.raises(AppError) as exc_late:
                    await svc.register(challenger)
                assert exc_late.value.code == 40098

                row = (
                    await session.execute(select(DaoContest).order_by(DaoContest.id.desc()))
                ).scalars().first()
                assert row is not None
                assert row.force_started is True

    _run(_body())


def test_dao_contest_force_start_zero_entrants_cancelled(tmp_path: Path) -> None:
    """无人报名立刻开赛 → cancelled。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "contest_empty.db") as factory:
            async with factory() as session:
                await _user_with_fate(
                    session,
                    "empty_lord@example.com",
                    "空场道主",
                    as_lord=True,
                )
                svc = DaoContestService(session)
                await svc.ensure_current()
                await session.commit()
                result = await svc.force_start(note="empty")
                await session.commit()
                assert result["contest"]["status"] == "cancelled"
                assert result["contest"]["total_entrants"] == 0
                # entries 表无行
                n = (
                    await session.execute(select(DaoContestEntry))
                ).scalars().all()
                assert len(n) == 0

    _run(_body())
