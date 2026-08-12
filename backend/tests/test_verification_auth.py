"""
注册核验改造 + 邮箱/手机登录 + 注册开关 + 超级密码集成测试。

覆盖：
1. 默认开关关闭：仅邮箱+密码可注册；
2. 开启全部开关且无票 → ``40017``；
3. 三票齐全注册成功；
4. 超级密码 / 邮箱手机密码 / 短信登录；
5. 邮箱/手机冲突 ``40013``；
6. 禁用号 + 超级密码 ``40300``；
7. 开启实名开关缺 real_name → ``40017``。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User, VerificationChallenge
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.common import AppError
from app.services import auth_service
from app.services.verification import service as verification_service
from tests.async_db import open_test_session_factory, run_async as _run

_VALID_ID_CARD = "110101199003074477"


@pytest.fixture
def settings():
    """返回缓存的 Settings，便于 monkeypatch 属性。"""
    return get_settings()


def _disable_all_register_requirements(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭全部注册材料开关（仅邮箱+密码）。"""
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_real_name", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)


def _enable_all_register_requirements(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """开启全部注册材料开关。"""
    monkeypatch.setattr(settings, "register_require_phone", True)
    monkeypatch.setattr(settings, "register_require_real_name", True)
    monkeypatch.setattr(settings, "register_require_email_code", True)


def test_email_password_only_register(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开关全关时仅邮箱+密码可注册。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_all_register_requirements(settings, monkeypatch)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "email_only.db") as factory:
            async with factory() as session:
                result = await auth_service.register_user(
                    session,
                    RegisterRequest(
                        password="password123",
                        email="only@example.com",
                    ),
                )
                await session.commit()
                assert result.email == "only@example.com"
                assert result.phone is None
                user = await session.get(User, result.user_id)
                assert user is not None
                assert user.email_verified is False
                assert user.phone_verified is False

    _run(_body())


def test_missing_email_returns_40017(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺邮箱应拒绝（40017）。"""
    _disable_all_register_requirements(settings, monkeypatch)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "missing_email.db") as factory:
            async with factory() as session:
                with pytest.raises(AppError) as exc_info:
                    await auth_service.register_user(
                        session,
                        RegisterRequest(password="password123"),
                    )
                assert exc_info.value.code == 40017

    _run(_body())


def test_require_all_missing_tickets_returns_40017(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全部开关开启且无 ticket 时注册应抛 40017。"""
    monkeypatch.setattr(settings, "debug", False)
    _enable_all_register_requirements(settings, monkeypatch)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "prod_missing.db") as factory:
            async with factory() as session:
                with pytest.raises(AppError) as exc_info:
                    await auth_service.register_user(
                        session,
                        RegisterRequest(
                            password="password123",
                            email="prod01@example.com",
                            phone="13800138010",
                            real_name="正式用户",
                            id_card=_VALID_ID_CARD,
                        ),
                    )
                assert exc_info.value.code == 40017

    _run(_body())


def test_full_ticket_register_success(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全部开关开启：完成三票后注册成功，且 ticket 被消费。"""
    _enable_all_register_requirements(settings, monkeypatch)
    monkeypatch.setattr(settings, "id_verify_mode", "format")
    phone = "13800138002"
    email = "full02@example.com"
    real_name = "测试用户"
    id_card = _VALID_ID_CARD

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "full_reg.db") as factory:
            monkeypatch.setattr(settings, "debug", True)
            async with factory() as session:
                await verification_service.send_sms(session, phone)
                sms_ticket = await verification_service.confirm_sms(
                    session,
                    phone,
                    settings.debug_verify_code,
                )
                await verification_service.send_email(session, email)
                email_ticket = await verification_service.confirm_email(
                    session,
                    email,
                    settings.debug_verify_code,
                )
                id_ticket = await verification_service.submit_id(
                    session,
                    real_name=real_name,
                    id_card=id_card,
                )
                await session.commit()

            assert sms_ticket and email_ticket and id_ticket

            monkeypatch.setattr(settings, "debug", False)
            async with factory() as session:
                result = await auth_service.register_user(
                    session,
                    RegisterRequest(
                        password="password123",
                        email=email,
                        phone=phone,
                        real_name=real_name,
                        id_card=id_card,
                        sms_ticket=sms_ticket,
                        email_ticket=email_ticket,
                        id_ticket=id_ticket,
                    ),
                )
                await session.commit()
                assert result.email == email
                user = await session.get(User, result.user_id)
                assert user is not None
                assert user.email_verified is True
                assert user.phone_verified is True
                assert user.id_verified_level == "format"

                for ticket in (sms_ticket, email_ticket, id_ticket):
                    challenge = await session.scalar(
                        select(VerificationChallenge).where(
                            VerificationChallenge.ticket == ticket,
                        ),
                    )
                    assert challenge is not None
                    assert challenge.consumed_at is not None

    _run(_body())


def test_super_password_login_and_bad_password(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超级密码可登录；错误密码仍返回 40002。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_all_register_requirements(settings, monkeypatch)
    super_pw = "super-secret-for-tests-only"
    monkeypatch.setattr(settings, "super_password", super_pw)
    email = "super@example.com"

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "super_login.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email=email),
                )
                await session.commit()

            async with factory() as session:
                tokens = await auth_service.login_user(
                    session,
                    LoginRequest(
                        login_method="password",
                        account=email,
                        password=super_pw,
                        remember_me=True,
                    ),
                )
                assert tokens.access_token
                assert tokens.user.email == email

            async with factory() as session:
                with pytest.raises(AppError) as exc_info:
                    await auth_service.login_user(
                        session,
                        LoginRequest(
                            login_method="password",
                            account=email,
                            password="definitely-wrong-password",
                            remember_me=True,
                        ),
                    )
                assert exc_info.value.code == 40002

    _run(_body())


def test_email_or_phone_password_login(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """邮箱+密码、手机号+密码均可登录。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_all_register_requirements(settings, monkeypatch)
    email = "login@example.com"
    phone = "13800138030"
    password = "password123"

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "pwd_login.db") as factory:
            async with factory() as session:
                # 带手机落库以便测手机密码登录（开关关时 phone 仍可作为可选字段提交）
                await auth_service.register_user(
                    session,
                    RegisterRequest(password=password, email=email, phone=phone),
                )
                await session.commit()

            async with factory() as session:
                by_email = await auth_service.login_user(
                    session,
                    LoginRequest(
                        login_method="password",
                        account=email,
                        password=password,
                    ),
                )
                assert by_email.user.email == email

                by_phone = await auth_service.login_user(
                    session,
                    LoginRequest(
                        login_method="password",
                        account=phone,
                        password=password,
                    ),
                )
                assert by_phone.user.phone == phone

    _run(_body())


def test_sms_code_login(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """手机号 + 短信验证码登录成功；错码 40010。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_all_register_requirements(settings, monkeypatch)
    email = "smslogin@example.com"
    phone = "13800138040"

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "sms_login.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email=email, phone=phone),
                )
                await session.commit()

            async with factory() as session:
                await verification_service.send_sms(session, phone)
                await session.commit()

            async with factory() as session:
                tokens = await auth_service.login_user(
                    session,
                    LoginRequest(
                        login_method="sms",
                        phone=phone,
                        sms_code=settings.debug_verify_code,
                        remember_me=True,
                    ),
                )
                await session.commit()
                assert tokens.access_token
                assert tokens.user.phone == phone

            async with factory() as session:
                with pytest.raises(AppError) as exc_info:
                    await auth_service.login_user(
                        session,
                        LoginRequest(
                            login_method="sms",
                            phone=phone,
                            sms_code=settings.debug_verify_code,
                        ),
                    )
                assert exc_info.value.code == 40010

    _run(_body())


def test_email_or_phone_conflict_returns_40013(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """邮箱或手机已被占用时注册应抛 AppError(40013)。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_all_register_requirements(settings, monkeypatch)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "conflict.db") as factory:
            async with factory() as session:
                await auth_service.register_user(
                    session,
                    RegisterRequest(
                        password="password123",
                        email="taken@example.com",
                        phone="13800138099",
                    ),
                )
                await session.commit()

            async with factory() as session:
                with pytest.raises(AppError) as email_exc:
                    await auth_service.register_user(
                        session,
                        RegisterRequest(
                            password="password123",
                            email="taken@example.com",
                        ),
                    )
                assert email_exc.value.code == 40013

            async with factory() as session:
                with pytest.raises(AppError) as phone_exc:
                    await auth_service.register_user(
                        session,
                        RegisterRequest(
                            password="password123",
                            email="other@example.com",
                            phone="13800138099",
                        ),
                    )
                assert phone_exc.value.code == 40013

    _run(_body())


def test_inactive_user_super_password_returns_40300(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """禁用账号即使用超级密码也拒绝（40300）。"""
    monkeypatch.setattr(settings, "debug", True)
    _disable_all_register_requirements(settings, monkeypatch)
    super_pw = "super-secret-for-tests-only"
    monkeypatch.setattr(settings, "super_password", super_pw)
    email = "inactive@example.com"

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "inactive_super.db") as factory:
            async with factory() as session:
                result = await auth_service.register_user(
                    session,
                    RegisterRequest(password="password123", email=email),
                )
                user = await session.get(User, result.user_id)
                assert user is not None
                user.is_active = False
                await session.commit()

            async with factory() as session:
                with pytest.raises(AppError) as exc_info:
                    await auth_service.login_user(
                        session,
                        LoginRequest(
                            login_method="password",
                            account=email,
                            password=super_pw,
                            remember_me=True,
                        ),
                    )
                assert exc_info.value.code == 40300

    _run(_body())


def test_require_real_name_missing_returns_40017(
    tmp_path: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开启实名开关缺 real_name/id 时应抛 40017。"""
    monkeypatch.setattr(settings, "register_require_phone", False)
    monkeypatch.setattr(settings, "register_require_email_code", False)
    monkeypatch.setattr(settings, "register_require_real_name", True)

    async def _body() -> None:
        async with open_test_session_factory(tmp_path / "missing_real_name.db") as factory:
            async with factory() as session:
                with pytest.raises(AppError) as exc_info:
                    await auth_service.register_user(
                        session,
                        RegisterRequest(
                            password="password123",
                            email="norn@example.com",
                        ),
                    )
                assert exc_info.value.code == 40017

    _run(_body())
