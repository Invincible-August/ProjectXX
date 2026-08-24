"""M6 开道 / 道池单测（服务层）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.dao_service import DaoService
from app.services.gm_service import GmService
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
    monkeypatch.setattr(settings, "dao_system_enabled", True)
    monkeypatch.setattr(settings, "avatar_enabled", True)
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_dao_config_loads() -> None:
    """dao.yaml 进入 Bundle。"""
    cfg = get_game_config()
    assert "dao_flame" in cfg.dao.entries
    assert cfg.dao.entries["dao_flame"]["label_zh"] == "炎道"
    assert "true_immortal" in cfg.realms


def test_dao_open_flow(tmp_path: Path) -> None:
    """未真仙 40080；真仙 roll→choose 本命锁定且池≥3；再 roll 40081。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dao_open.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="dao01@example.com"),
                )
                await session.commit()
                result = await session.execute(
                    select(User).where(User.email == "dao01@example.com"),
                )
                user = result.scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="开道测甲"),
                )
                await session.commit()

                dao = DaoService(session)
                with pytest.raises(AppError) as exc:
                    await dao.roll_open(user)
                assert exc.value.code == 40080

                await GmService(session).gm_set_character(
                    user,
                    force_true_immortal=True,
                )
                await session.commit()

                offer = await dao.roll_open(user)
                await session.commit()
                assert len(offer["options"]) == 3
                chosen = offer["options"][0]["dao_id"]

                chosen_data = await dao.choose_open(
                    user,
                    dao_id=chosen,
                    session_id=offer["session_id"],
                )
                await session.commit()
                assert chosen_data["dao"]["fate_dao_id"] == chosen
                assert chosen_data["dao"]["locked"] is True
                assert chosen_data["dao"]["pool_count"] >= 3

                with pytest.raises(AppError) as exc2:
                    await dao.roll_open(user)
                assert exc2.value.code == 40081

    _run(_body())


def test_avatar_dao_independent_of_main(tmp_path: Path) -> None:
    """化身金丹不可悟道；真仙后独立开道，道值不与本体共享。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "dao_avatar.db") as factory:
            async with factory() as session:
                from app.db.models.avatar import Avatar
                from app.db.models.character import Character
                from app.services.avatar_service import AvatarService

                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="daoav@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "daoav@example.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="化身开道测"),
                )
                await session.commit()

                await GmService(session).gm_set_character(
                    user,
                    force_true_immortal=True,
                    spirit_stones=5000,
                )
                await session.commit()

                dao = DaoService(session)
                character = (
                    await session.execute(select(Character).where(Character.user_id == user.id))
                ).scalar_one()
                await dao.gm_lock_fate_dao(character, "dao_flame")
                await dao.gm_set_resources(character, dao_qi=999)
                await session.commit()

                panel = await AvatarService(session).condense(user)
                assert panel["major_realm"] == "jindan"
                await session.commit()

                with pytest.raises(AppError) as exc:
                    await dao.roll_open(user, actor="avatar")
                assert exc.value.code == 40080

                avatar = (
                    await session.execute(select(Avatar).where(Avatar.character_id == character.id))
                ).scalar_one()
                avatar.major_realm = "true_immortal"
                await session.flush()

                offer = await dao.roll_open(user, actor="avatar")
                await session.commit()
                assert offer["actor"] == "avatar"
                chosen = offer["options"][0]["dao_id"]
                result = await dao.choose_open(
                    user,
                    dao_id=chosen,
                    session_id=offer["session_id"],
                    actor="avatar",
                )
                await session.commit()
                assert result["dao"]["actor"] == "avatar"
                assert result["dao"]["fate_dao_id"] == chosen
                assert result["dao"]["qi"] != 999

                main = await dao.enrich_dao_summary(character)
                assert main is not None
                assert main["fate_dao_id"] == "dao_flame"
                assert main["qi"] == 999

                av_sum = await dao.enrich_avatar_dao_summary(character, avatar)
                assert av_sum is not None
                assert av_sum["fate_dao_id"] == chosen
                assert av_sum["qi"] != 999

    _run(_body())
