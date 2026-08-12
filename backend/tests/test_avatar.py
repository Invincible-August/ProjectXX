"""
M4 化身凝练测试（§10.4）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.avatar_service import AvatarService
from app.services.gm_service import GmService
from app.services.realm_config import clear_game_config_cache

from tests.async_db import open_test_session_factory, run_async as _run


async def _user_with_character(session: AsyncSession, email: str) -> User:
    """注册并创角。"""
    await auth_service.register_user(
        session,
        RegisterRequest(password="password123", email=email),
    )
    await session.commit()
    from sqlalchemy import select
    from app.db.models import User as UserModel

    result = await session.execute(select(UserModel).where(UserModel.email == email))
    user = result.scalar_one()
    await character_service.create_character(
        session,
        user,
        CreateCharacterRequest(name=email.split("@")[0][:16]),
    )
    await session.commit()
    return user


@pytest.fixture(autouse=True)
def _reload_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """重置配置缓存。"""
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_condense_rejected_below_jindan(tmp_path: Path) -> None:
    """炼气/锻体不可凝练 → 40050。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "av1.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "av01@example.com")
                svc = AvatarService(session)
                with pytest.raises(AppError) as exc:
                    await svc.condense(user)
                assert exc.value.code == 40050

    _run(_body())


def test_condense_success_after_gm_jindan(tmp_path: Path) -> None:
    """GM 金丹后可凝练 1 个化身。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "av2.db") as factory:
            async with factory() as session:
                user = await _user_with_character(session, "av02@example.com")
                await GmService(session).gm_set_character(user, force_jindan=True, spirit_stones=5000)
                await session.commit()
                svc = AvatarService(session)
                panel = await svc.condense(user)
                assert panel is not None
                assert panel["status"] == "idle"
                with pytest.raises(AppError) as exc:
                    await svc.condense(user)
                assert exc.value.code == 40051

    _run(_body())
