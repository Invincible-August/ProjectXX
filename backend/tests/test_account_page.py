"""玩家账号页：改密邮箱核验与打赏/仙缘/广告摘要。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.core.time_utils import now_utc
from app.db.models import AdminUser, PlayerAdWatchRecord, User
from app.schemas.auth import RegisterRequest
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import AppError
from app.services import auth_service, character_service
from app.services.account_service import AccountService
from app.services.admin_player_service import AdminPlayerService
from app.services.admin_rbac import roles_to_storage
from app.services.verification import service as verification_service
from app.services.realm_config import clear_game_config_cache
from tests.async_db import open_test_session_factory, run_async as _run


@pytest.fixture(autouse=True)
def _cfg(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "app_env", "development")
    clear_game_config_cache()
    yield
    clear_game_config_cache()


@pytest.fixture
def settings():
    return get_settings()


def _disable_email_code(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)


def test_change_password_without_email_code(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开关关闭时仅原密码+新密码即可改密。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_email_code(settings, monkeypatch)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pwd_off.db") as factory:
            async with factory() as session:
                result = await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="pwd_off@example.com"),
                )
                await session.commit()
                user = await session.get(User, result.user_id)
                assert user is not None
                data = await auth_service.AuthService(session).change_password(
                    user,
                    old_password="password123",
                    new_password="password456",
                )
                await session.commit()
                await session.refresh(user)
                assert data["message"] == "密码已更新"
                assert verify_password("password456", user.password_hash)

    _run(_body())


def test_change_password_requires_email_ticket(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开关开启时无 ticket 拒绝；持有效 email_ticket 成功并消费票据。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_email_code(settings, monkeypatch)
    email = "pwd_on@example.com"

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pwd_on.db") as factory:
            async with factory() as session:
                result = await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email=email),
                )
                await session.commit()
                user = await session.get(User, result.user_id)
                assert user is not None
                monkeypatch.setattr(settings, "register_require_email_code", True)
                svc = auth_service.AuthService(session)
                with pytest.raises(AppError) as exc_info:
                    await svc.change_password(
                        user,
                        old_password="password123",
                        new_password="password456",
                    )
                assert exc_info.value.code == 40017

                await verification_service.send_email(session, email)
                ticket = await verification_service.confirm_email(
                    session,
                    email,
                    settings.debug_verify_code,
                )
                data = await svc.change_password(
                    user,
                    old_password="password123",
                    new_password="password456",
                    email_ticket=ticket,
                )
                await session.commit()
                await session.refresh(user)
                assert data["message"] == "密码已更新"
                assert verify_password("password456", user.password_hash)
                assert user.email_verified is True

    _run(_body())


def test_account_summary_and_tips(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """摘要含仙缘/累计打赏/广告次数；账单展示途径原文。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_email_code(settings, monkeypatch)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "acct.db") as factory:
            async with factory() as session:
                result = await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email="acct@example.com"),
                )
                await session.commit()
                user = (
                    await session.execute(select(User).where(User.email == "acct@example.com"))
                ).scalar_one()
                await character_service.create_character(
                    session,
                    user,
                    CreateCharacterRequest(name="账单测号"),
                )
                await session.commit()

                admin = AdminUser(
                    username="acct_admin",
                    password_hash=hash_password("adminpass1"),
                    display_name="Ops",
                    roles=roles_to_storage(["admin"]),
                    is_active=True,
                )
                session.add(admin)
                await session.flush()
                ops = AdminPlayerService(session)
                await ops.grant_fate_luck(admin, user_id=user.id, amount=12)
                await ops.create_tip_record(
                    admin,
                    user_id=user.id,
                    paid_at="2026-08-14 12:00:00",
                    channel="对公转账",
                    order_no="OTH-001",
                    amount=30,
                )
                session.add(
                    PlayerAdWatchRecord(
                        user_id=user.id,
                        watched_at=now_utc(),
                        platform="test",
                    ),
                )
                await session.commit()
                await session.refresh(user)

                acct = AccountService(session)
                summary = await acct.get_summary(user)
                assert summary["fate_luck"] == 12
                assert summary["total_recharge_amount"] == 30
                assert summary["ad_watch_count"] == 1
                tips = await acct.list_tips(user)
                assert tips["total"] == 1
                assert tips["items"][0]["channel"] == "对公转账"
                assert tips["items"][0]["order_no"] == "OTH-001"
                assert tips["items"][0]["amount"] == 30

    _run(_body())
