"""后台运营：剔除道主 → 席位空缺。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import AdminUser, DaoLordship, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.admin_ops_service import AdminOpsService
from app.services.admin_rbac import roles_to_storage
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
    clear_game_config_cache()
    yield
    clear_game_config_cache()


def test_admin_remove_dao_lord_vacates_seat(tmp_path: Path) -> None:
    """publisher 剔除后该道无主。"""

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "admin_ops_lord.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="kicklord@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(
                        select(User).where(User.email == "kicklord@example.com"),
                    )
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="被剔道主"),
                )
                await session.commit()
                await GmService(session).gm_set_character(
                    user,
                    force_true_immortal=True,
                    lock_fate_dao="dao_flame",
                    set_dao_level=2,
                    set_dao_lord="dao_flame",
                )
                await session.commit()
                character = await character_service.get_character_by_user_id(session, user.id)
                lord = (
                    await session.execute(
                        select(DaoLordship).where(DaoLordship.dao_id == "dao_flame"),
                    )
                ).scalar_one()
                assert lord.character_id == character.id

                admin = AdminUser(
                    username="kickops",
                    password_hash=hash_password("ops-pass-123"),
                    display_name="KickOps",
                    roles=roles_to_storage(["viewer", "publisher"]),
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                await session.refresh(admin)

                ops = AdminOpsService(session)
                result = await ops.remove_dao_lord(
                    admin,
                    dao_id="dao_flame",
                    note="单测剔除",
                )
                await session.commit()
                assert result["removed"] is True
                gone = (
                    await session.execute(
                        select(DaoLordship).where(DaoLordship.dao_id == "dao_flame"),
                    )
                ).scalar_one_or_none()
                assert gone is None

                # 再剔一次：空位
                again = await ops.remove_dao_lord(admin, dao_id="dao_flame")
                assert again["removed"] is False

                # viewer 不可剔
                viewer = AdminUser(
                    username="viewer_only",
                    password_hash=hash_password("ops-pass-123"),
                    display_name="Viewer",
                    roles=roles_to_storage(["viewer"]),
                    is_active=True,
                )
                session.add(viewer)
                await session.commit()
                await session.refresh(viewer)
                with pytest.raises(AppError) as exc:
                    await ops.remove_dao_lord(viewer, dao_id="dao_flame")
                assert exc.value.code == 40300

    _run(_body())
