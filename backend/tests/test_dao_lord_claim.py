"""M6 道主空位自动就任 / 有主须走赛会。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DaoLordship, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.dao_lord_service import DaoLordService
from app.services.dao_service import DaoService
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
    monkeypatch.setattr(settings, "dao_lord_force_window", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


async def _user_with_dao(session, email: str, name: str, *, level: int = 1):
    """注册并开道；开道后若等级达标会自动就任空位。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=name),
    )
    await session.commit()
    await GmService(session).gm_set_character(user, force_true_immortal=True)
    await session.commit()
    dao = DaoService(session)
    offer = await dao.roll_open(user)
    await session.commit()
    await dao.choose_open(
        user,
        dao_id=offer["options"][0]["dao_id"],
        session_id=offer["session_id"],
    )
    character = await character_service.get_character_by_user_id(session, user.id)
    row = await dao._get_or_create_row(character.id)
    if int(row.dao_level) != level:
        row.dao_level = level
        row.dao_exp = 250 if level >= 2 else int(row.dao_exp)
        await session.flush()
        await DaoLordService(session).try_auto_inaugurate(character)
    await session.commit()
    return user, offer["options"][0]["dao_id"]


def test_dao_lord_auto_inaugurate_on_open(tmp_path: Path) -> None:
    """空位 + 达标：开道后自动就任，无需手动夺位。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dao_lord_auto.db") as factory:
            async with factory() as session:
                user, dao_id = await _user_with_dao(
                    session,
                    "lord_auto@example.com",
                    "道主测甲",
                    level=1,
                )
                character = await character_service.get_character_by_user_id(session, user.id)
                lord = (
                    await session.execute(
                        select(DaoLordship).where(DaoLordship.dao_id == dao_id),
                    )
                ).scalar_one_or_none()
                assert lord is not None
                assert lord.character_id == character.id

                # 兼容 claim 入口：已是本人 → 幂等成功；或已有主 → 40089
                lord_svc = DaoLordService(session)
                with pytest.raises(AppError) as exc:
                    await lord_svc.claim(user, dao_id=dao_id)
                # 已是道主时 _inaugurate 返回成功；claim 在 seat_occupied 时走 40089
                assert exc.value.code == 40089

                board = await lord_svc.get_board(user)
                seat = next(s for s in board["seats"] if s["dao_id"] == dao_id)
                assert seat["lord_character_id"] == character.id
                assert seat["can_claim"] is False
                assert seat["vacant"] is False

    _run(_body())


def test_dao_lord_second_player_must_use_contest(tmp_path: Path) -> None:
    """有主后第二人不可 claim，须走道主之争赛会。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dao_lord_chal.db") as factory:
            async with factory() as session:
                user_a, dao_id = await _user_with_dao(
                    session,
                    "lord_a@example.com",
                    "道主甲",
                    level=1,
                )
                # 乙：同一本命道（GM 锁同道）
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="lord_b@example.com"),
                )
                await session.commit()
                user_b = (
                    await session.execute(
                        select(User).where(User.email == "lord_b@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user_b,
                    CreateCharacterRequest(name="道主乙"),
                )
                await session.commit()
                await GmService(session).gm_set_character(
                    user_b,
                    force_true_immortal=True,
                    lock_fate_dao=dao_id,
                    set_dao_level=2,
                )
                await session.commit()

                lord_svc = DaoLordService(session)
                with pytest.raises(AppError) as exc:
                    await lord_svc.claim(user_b, dao_id=dao_id)
                assert exc.value.code == 40089

                # 甲仍是道主
                character_a = await character_service.get_character_by_user_id(
                    session,
                    user_a.id,
                )
                lord = (
                    await session.execute(
                        select(DaoLordship).where(DaoLordship.dao_id == dao_id),
                    )
                ).scalar_one()
                assert lord.character_id == character_a.id

    _run(_body())
