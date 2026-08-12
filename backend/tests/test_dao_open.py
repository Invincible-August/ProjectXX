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
