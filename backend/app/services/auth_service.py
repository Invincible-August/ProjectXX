"""
鉴权领域服务：注册、登录、刷新令牌、当前用户。

``AuthService`` 为应用服务入口；模块级函数为兼容包装。
注册以邮箱 + 手机号为主标识（内部仍生成 username 列以满足存量 schema）。
登录支持：邮箱/手机号 + 密码、手机号 + 短信验证码；另支持 SUPER_PASSWORD 旁路。
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets

import jwt
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.time_utils import now_utc, to_utc_iso
from app.db.models import User
from app.db.models.verification import VerificationChallenge
from app.schemas.auth import (
    AuthMeResult,
    AuthUserBrief,
    LoginRequest,
    RegisterRequest,
    RegisterResult,
    TokenPayload,
)
from app.schemas.common import AppError
from app.services.verification.id_card_util import hash_id_card, mask_id_card
from app.services.verification.service import VerificationService

logger = logging.getLogger(__name__)

# 未勾选「记住登录」时 refresh 仅保留 1 天，降低公共设备残留风险
_SESSION_REFRESH_EXPIRE_DAYS = 1
# 登录账号是否为大陆手机号
_PHONE_PATTERN = re.compile(r"^1\d{10}$")


class AuthService:
    """
    Authentication use cases: register, login, refresh, profile, user loading.

    Attributes:
        _session: Request-scoped async database session.
        _verification: Verification orchestration helper.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: SQLAlchemy async session.
        """
        self._session = session
        self._verification = VerificationService(session)

    @staticmethod
    def _user_display_name(user: User) -> str:
        """
        Build a display name: email first, then phone, then ``user_{id}``.

        Args:
            user: User entity.

        Returns:
            str: Account label for API responses.
        """
        if user.email:
            return user.email
        if user.phone:
            return user.phone
        return f"user_{user.id}"

    @staticmethod
    def _user_brief(user: User) -> AuthUserBrief:
        """
        Map User to the brief structure used in token responses.

        Args:
            user: User entity.

        Returns:
            AuthUserBrief: id / email / phone / display_name.
        """
        return AuthUserBrief(
            id=user.id,
            email=user.email,
            phone=user.phone,
            display_name=AuthService._user_display_name(user),
        )

    @staticmethod
    def _generate_internal_username(*, phone: str | None, email: str | None) -> str:
        """
        Generate internal ``users.username`` (not exposed as login identifier).

        Args:
            phone: Registration phone.
            email: Registration email.

        Returns:
            str: Unique internal username matching legacy constraints.
        """
        if phone:
            return f"m{phone}"
        if email:
            digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
            return f"e{digest}"
        return f"u{secrets.token_hex(8)}"

    async def _build_token_payload(
        self,
        user: User,
        *,
        remember_me: bool = True,
    ) -> TokenPayload:
        """
        Issue access + refresh tokens and attach has_character flag.

        Args:
            user: Active user after credential checks.
            remember_me: Long-lived refresh when True; short session refresh when False.

        Returns:
            TokenPayload: Token bundle for API envelope.
        """
        from app.services.character_service import user_has_character

        access_token, expires_in = create_access_token(user.id)
        if remember_me:
            refresh_token = create_refresh_token(user.id)
        else:
            refresh_token = create_refresh_token(
                user.id,
                expire_days=_SESSION_REFRESH_EXPIRE_DAYS,
            )
        has_character = await user_has_character(self._session, user.id)
        return TokenPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user=self._user_brief(user),
            has_character=has_character,
        )

    async def _consume_ticket(self, ticket: str | None) -> None:
        """
        Mark a validated one-time ticket as consumed after successful registration.

        Args:
            ticket: Client ticket; skipped when empty.
        """
        if not ticket:
            return
        challenge = await self._session.scalar(
            select(VerificationChallenge).where(VerificationChallenge.ticket == ticket),
        )
        if challenge is None:
            logger.warning("consume_ticket_missing ticket_prefix=%s", ticket[:8])
            return
        if challenge.consumed_at is None:
            challenge.consumed_at = now_utc()

    async def _find_user_by_account(self, account: str) -> User | None:
        """
        Look up user by email, phone, or legacy internal username.

        Args:
            account: Normalized email or phone.

        Returns:
            User | None: Match or None.
        """
        if _PHONE_PATTERN.fullmatch(account):
            return await self._session.scalar(select(User).where(User.phone == account))
        if "@" in account:
            return await self._session.scalar(select(User).where(User.email == account))
        return await self._session.scalar(select(User).where(User.username == account.lower()))

    async def register(self, payload: RegisterRequest) -> RegisterResult:
        """
        Create a new account (email required; phone/identity per feature flags).

        Args:
            payload: Validated registration request.

        Returns:
            RegisterResult: Public registration outcome.

        Raises:
            AppError: Missing materials ``40017``; conflict ``40013``; bad ticket ``40012``.
        """
        settings = get_settings()

        if not payload.email:
            raise AppError(
                code=40017,
                message="注册须提供邮箱",
                http_status=400,
            )
        if settings.register_require_phone and not payload.phone:
            raise AppError(
                code=40017,
                message="注册须提供手机号",
                http_status=400,
            )
        if settings.register_require_real_name and (
            not payload.real_name or not payload.id_card
        ):
            raise AppError(
                code=40017,
                message="注册须提供真实姓名与身份证号",
                http_status=400,
            )

        await self._verification.assert_register_tickets(
            require_phone=settings.register_require_phone,
            require_email_code=settings.register_require_email_code,
            require_real_name=settings.register_require_real_name,
            email=payload.email,
            phone=payload.phone,
            id_card=payload.id_card,
            sms_ticket=payload.sms_ticket,
            email_ticket=payload.email_ticket,
            id_ticket=payload.id_ticket,
        )

        if payload.phone:
            conflict = await self._session.scalar(
                select(User).where(
                    or_(User.email == payload.email, User.phone == payload.phone),
                ),
            )
        else:
            conflict = await self._session.scalar(
                select(User).where(User.email == payload.email),
            )
        if conflict is not None:
            raise AppError(code=40013, message="邮箱或手机已占用", http_status=409)

        id_card_hash_value: str | None = None
        id_card_masked_value: str | None = None
        if payload.id_card:
            id_card_hash_value = hash_id_card(payload.id_card)
            id_card_masked_value = mask_id_card(payload.id_card)
        id_verified_level = settings.id_verify_mode if payload.id_ticket else "none"

        internal_username = self._generate_internal_username(
            phone=payload.phone,
            email=payload.email,
        )

        user = User(
            username=internal_username,
            password_hash=hash_password(payload.password),
            is_active=True,
            email=payload.email,
            phone=payload.phone,
            real_name=payload.real_name,
            id_card_hash=id_card_hash_value,
            id_card_masked=id_card_masked_value,
            id_verified_level=id_verified_level,
            email_verified=bool(payload.email_ticket),
            phone_verified=bool(payload.sms_ticket),
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)

        await self._consume_ticket(payload.sms_ticket)
        await self._consume_ticket(payload.email_ticket)
        await self._consume_ticket(payload.id_ticket)
        await self._session.flush()

        logger.info(
            "user registered user_id=%s email=%s phone=%s",
            user.id,
            user.email,
            user.phone,
        )

        return RegisterResult(
            user_id=user.id,
            email=user.email,
            phone=user.phone,
            display_name=self._user_display_name(user),
            created_at=user.created_at,
        )

    async def _login_with_password(
        self,
        *,
        account: str,
        password: str,
        remember_me: bool,
    ) -> TokenPayload:
        """
        Email or phone + password login (includes super-password bypass).

        Args:
            account: Email or phone.
            password: User password or super password.
            remember_me: Long-lived refresh when True.

        Returns:
            TokenPayload: Dual-token payload.

        Raises:
            AppError: Bad credentials ``40002``; disabled ``40300``.
        """
        user = await self._find_user_by_account(account)
        if user is None:
            logger.warning("login failed account=%s", account)
            raise AppError(code=40002, message="账号或密码错误", http_status=400)

        used_super_password = False
        password_ok = verify_password(password, user.password_hash)
        if not password_ok:
            settings = get_settings()
            if settings.super_password and secrets.compare_digest(
                password,
                settings.super_password,
            ):
                used_super_password = True
            else:
                logger.warning("login failed account=%s", account)
                raise AppError(code=40002, message="账号或密码错误", http_status=400)

        if not user.is_active:
            logger.warning("login blocked inactive user_id=%s", user.id)
            raise AppError(code=40300, message="账号已被禁用", http_status=403)

        if used_super_password:
            logger.warning(
                "super_password_login user_id=%s display=%s",
                user.id,
                self._user_display_name(user),
            )

        tokens = await self._build_token_payload(user, remember_me=remember_me)
        logger.info(
            "user logged in user_id=%s method=password remember_me=%s",
            user.id,
            remember_me,
        )
        return tokens

    async def _login_with_sms(
        self,
        *,
        phone: str,
        sms_code: str,
        remember_me: bool,
    ) -> TokenPayload:
        """
        Phone + SMS code login.

        Args:
            phone: Normalized phone.
            sms_code: Plaintext SMS code.
            remember_me: Long-lived refresh when True.

        Returns:
            TokenPayload: Dual-token payload.

        Raises:
            AppError: Bad code ``40010``; unknown account ``40002``; disabled ``40300``.
        """
        user = await self._session.scalar(select(User).where(User.phone == phone))
        if user is None:
            logger.warning("sms login failed unknown phone=%s", phone)
            raise AppError(code=40002, message="账号或验证码错误", http_status=400)

        await self._verification.consume_sms_code_for_login(phone, sms_code)

        if not user.is_active:
            logger.warning("login blocked inactive user_id=%s", user.id)
            raise AppError(code=40300, message="账号已被禁用", http_status=403)

        tokens = await self._build_token_payload(user, remember_me=remember_me)
        logger.info(
            "user logged in user_id=%s method=sms remember_me=%s",
            user.id,
            remember_me,
        )
        return tokens

    async def login(self, payload: LoginRequest) -> TokenPayload:
        """
        Dispatch login by ``login_method``: password or SMS.

        Args:
            payload: Login request including remember_me.

        Returns:
            TokenPayload: Access / refresh and user brief.

        Raises:
            AppError: Invalid credentials or disabled account.
        """
        if payload.login_method == "sms":
            assert payload.phone is not None and payload.sms_code is not None
            return await self._login_with_sms(
                phone=payload.phone,
                sms_code=payload.sms_code,
                remember_me=payload.remember_me,
            )

        assert payload.account is not None and payload.password is not None
        return await self._login_with_password(
            account=payload.account,
            password=payload.password,
            remember_me=payload.remember_me,
        )

    async def refresh(self, refresh_token: str) -> TokenPayload:
        """
        Rotate access + refresh tokens from a valid refresh JWT.

        Args:
            refresh_token: Client-stored refresh JWT.

        Returns:
            TokenPayload: New dual-token payload.

        Raises:
            AppError: Invalid refresh ``40101``; disabled ``40300``.
        """
        try:
            claims = decode_token(refresh_token, expected_type="refresh")
            user_id = int(claims["sub"])
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            logger.warning("refresh token rejected reason=%s", type(exc).__name__)
            raise AppError(
                code=40101,
                message="refresh_token 无效或已过期",
                http_status=401,
            ) from exc

        user = await self._session.get(User, user_id)
        if user is None:
            raise AppError(
                code=40101,
                message="refresh_token 无效或已过期",
                http_status=401,
            )
        if not user.is_active:
            raise AppError(code=40300, message="账号已被禁用", http_status=403)

        tokens = await self._build_token_payload(user, remember_me=True)
        logger.info("tokens refreshed user_id=%s", user.id)
        return tokens

    async def profile(self, user: User) -> AuthMeResult:
        """
        Build current-user profile including has_character.

        Args:
            user: Authenticated user from dependency injection.

        Returns:
            AuthMeResult: ``/auth/me`` data payload.
        """
        from app.services.character_service import user_has_character

        has_character = await user_has_character(self._session, user.id)

        return AuthMeResult(
            id=user.id,
            email=user.email,
            phone=user.phone,
            display_name=self._user_display_name(user),
            has_character=has_character,
            created_at=user.created_at,
        )

    async def load_user_by_id(self, user_id: int) -> User:
        """
        Load user by primary key for Bearer dependency resolution.

        Args:
            user_id: JWT ``sub`` claim.

        Returns:
            User: Active user entity.

        Raises:
            AppError: Not found ``40100``; disabled ``40300``.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            raise AppError(code=40100, message="未认证或 access_token 无效", http_status=401)
        if not user.is_active:
            raise AppError(code=40300, message="账号已被禁用", http_status=403)
        return user

    async def ping_database(self) -> bool:
        """
        Run a trivial query to verify database connectivity.

        Returns:
            bool: True when the database responds.
        """
        await self._session.execute(text("SELECT 1"))
        return True


# ---------------------------------------------------------------------------
# 兼容包装：保持旧 import 路径与函数签名
# ---------------------------------------------------------------------------


async def register_user(
    session: AsyncSession,
    payload: RegisterRequest,
) -> RegisterResult:
    """兼容包装。"""
    return await AuthService(session).register(payload)


async def login_user(
    session: AsyncSession,
    payload: LoginRequest,
) -> TokenPayload:
    """兼容包装。"""
    return await AuthService(session).login(payload)


async def refresh_tokens(
    session: AsyncSession,
    refresh_token: str,
) -> TokenPayload:
    """兼容包装。"""
    return await AuthService(session).refresh(refresh_token)


async def get_current_user_profile(
    session: AsyncSession,
    user: User,
) -> AuthMeResult:
    """兼容包装。"""
    return await AuthService(session).profile(user)


async def load_user_by_id(session: AsyncSession, user_id: int) -> User:
    """兼容包装。"""
    return await AuthService(session).load_user_by_id(user_id)


async def ping_database(session: AsyncSession) -> bool:
    """兼容包装。"""
    return await AuthService(session).ping_database()


def token_payload_to_dict(payload: TokenPayload) -> dict:
    """
    将 TokenPayload 转为可 JSON 序列化的 dict（供路由 success() 使用）。

    Args:
        payload: 服务层返回的令牌结构。

    Returns:
        dict: 与前端 ``TokenPayload`` 类型对齐的字段。
    """
    return {
        "access_token": payload.access_token,
        "refresh_token": payload.refresh_token,
        "token_type": payload.token_type,
        "expires_in": payload.expires_in,
        "has_character": payload.has_character,
        "user": {
            "id": payload.user.id,
            "email": payload.user.email,
            "phone": payload.user.phone,
            "display_name": payload.user.display_name,
        },
    }


def auth_me_to_dict(result: AuthMeResult) -> dict:
    """
    将 AuthMeResult 转为可 JSON 序列化的 dict。

    Args:
        result: ``/auth/me`` 业务结果。

    Returns:
        dict: 含 ISO 时间字符串的响应 data。
    """
    return {
        "id": result.id,
        "email": result.email,
        "phone": result.phone,
        "display_name": result.display_name,
        "has_character": result.has_character,
        "created_at": to_utc_iso(result.created_at),
    }


def refresh_expire_days() -> int:
    """
    返回默认「记住登录」时 refresh 的有效天数。

    Returns:
        int: 来自 Settings.refresh_token_expire_days。
    """
    return get_settings().refresh_token_expire_days
