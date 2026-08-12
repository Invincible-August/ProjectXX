"""
核验编排服务：发码、确认、签发 ticket、注册前校验。

``VerificationService`` 为应用服务入口；模块级函数为兼容包装。
Provider 发送与身份核验通过注入的 Protocol 实例或工厂解析完成。
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models.verification import VerificationChallenge
from app.schemas.common import AppError
from app.schemas.verification import ModesData
from app.services.verification import (
    get_email_provider,
    get_identity_provider,
    get_sms_provider,
)
from app.services.verification.id_card_util import hash_id_card, normalize_id_card
from app.services.verification.protocols import EmailProvider, IdentityProvider, SmsProvider

logger = logging.getLogger(__name__)

# 渠道常量：与设计规格 §7 ``verification_challenges.channel`` 对齐
CHANNEL_SMS = "sms"
CHANNEL_EMAIL = "email"
CHANNEL_ID = "id"


class VerificationService:
    """
    Verification orchestration: send codes, confirm, issue tickets, register checks.

    Attributes:
        _session: Request-scoped async database session.
        _sms: SMS delivery adapter.
        _email: Email delivery adapter.
        _identity: Identity verification adapter.
    """

    def __init__(
        self,
        session: AsyncSession,
        sms: SmsProvider | None = None,
        email: EmailProvider | None = None,
        identity: IdentityProvider | None = None,
    ) -> None:
        """
        Args:
            session: SQLAlchemy async session.
            sms: Optional SMS provider; resolved from settings when omitted.
            email: Optional email provider; resolved from settings when omitted.
            identity: Optional identity provider; resolved from settings when omitted.
        """
        self._session = session
        self._sms = sms if sms is not None else get_sms_provider()
        self._email = email if email is not None else get_email_provider()
        self._identity = identity if identity is not None else get_identity_provider()

    @staticmethod
    def _generate_plain_code() -> str:
        """
        Generate a plaintext verification code.

        DEBUG mode uses ``debug_verify_code``; production uses a secure 6-digit value.

        Returns:
            str: Plaintext code (must not be logged at INFO).
        """
        settings = get_settings()
        if settings.debug:
            return settings.debug_verify_code
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _issue_ticket_token() -> str:
        """
        Issue a one-time ticket string.

        Returns:
            str: URL-safe token (~43 chars, fits ``ticket`` String(64)).
        """
        return secrets.token_urlsafe(32)

    async def _get_latest_challenge(
        self,
        *,
        channel: str,
        target: str,
    ) -> VerificationChallenge | None:
        """
        Fetch the most recent challenge for ``channel + target``.

        Args:
            channel: Channel (sms / email / id).
            target: Normalized phone, email, or ID hash.

        Returns:
            VerificationChallenge | None: Latest row or None.
        """
        statement = (
            select(VerificationChallenge)
            .where(
                VerificationChallenge.channel == channel,
                VerificationChallenge.target == target,
            )
            .order_by(VerificationChallenge.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def _assert_send_interval(
        self,
        *,
        channel: str,
        target: str,
    ) -> None:
        """
        Enforce send-rate limit per channel+target (error ``40011`` when too fast).

        Args:
            channel: Channel identifier.
            target: Normalized target.

        Raises:
            AppError: When interval not elapsed.
        """
        settings = get_settings()
        latest = await self._get_latest_challenge(channel=channel, target=target)
        if latest is None:
            return
        created_at = ensure_aware_utc(latest.created_at)
        elapsed = (now_utc() - created_at).total_seconds()
        if elapsed < settings.verify_send_interval_seconds:
            raise AppError(40011, "发送过于频繁，请稍后再试", http_status=400)

    async def _create_code_challenge(
        self,
        *,
        channel: str,
        target: str,
        plain_code: str,
    ) -> VerificationChallenge:
        """
        Persist a code challenge row (ticket not yet issued).

        Args:
            channel: ``sms`` or ``email``.
            target: Phone or email.
            plain_code: Plaintext code (hashed, not stored raw).

        Returns:
            VerificationChallenge: Flushed new row.
        """
        settings = get_settings()
        challenge = VerificationChallenge(
            channel=channel,
            target=target,
            code_hash=hash_password(plain_code),
            ticket=None,
            payload_json=None,
            expires_at=now_utc() + timedelta(seconds=settings.verify_code_ttl_seconds),
            consumed_at=None,
        )
        self._session.add(challenge)
        await self._session.flush()
        return challenge

    async def _confirm_code_challenge(
        self,
        *,
        channel: str,
        target: str,
        code: str,
    ) -> str:
        """
        Validate a code and issue a ticket on the same challenge row.

        Args:
            channel: ``sms`` or ``email``.
            target: Phone or email.
            code: User-submitted plaintext code.

        Returns:
            str: Newly issued one-time ticket.

        Raises:
            AppError: Invalid or expired code (``40010``).
        """
        settings = get_settings()
        latest = await self._get_latest_challenge(channel=channel, target=target)
        if latest is None or latest.code_hash is None:
            raise AppError(40010, "验证码错误或过期", http_status=400)
        if latest.consumed_at is not None:
            raise AppError(40010, "验证码错误或过期", http_status=400)

        expires_at = ensure_aware_utc(latest.expires_at)
        if expires_at <= now_utc():
            raise AppError(40010, "验证码错误或过期", http_status=400)

        code_ok = verify_password(code, latest.code_hash)
        if not code_ok and settings.debug and secrets.compare_digest(code, settings.debug_verify_code):
            code_ok = True
        if not code_ok:
            raise AppError(40010, "验证码错误或过期", http_status=400)

        ticket = self._issue_ticket_token()
        latest.ticket = ticket
        latest.expires_at = now_utc() + timedelta(seconds=settings.verify_ticket_ttl_seconds)
        await self._session.flush()
        logger.info(
            "verification_ticket_issued channel=%s target=%s challenge_id=%s",
            channel,
            target,
            latest.id,
        )
        return ticket

    async def send_sms(self, phone: str) -> None:
        """
        Send an SMS verification code (persist challenge + call SMS provider).

        Args:
            phone: Normalized mobile number.

        Raises:
            AppError: Rate limit ``40011``; provider ``50100``.
        """
        phone = phone.strip()
        await self._assert_send_interval(channel=CHANNEL_SMS, target=phone)
        plain_code = self._generate_plain_code()
        await self._create_code_challenge(
            channel=CHANNEL_SMS,
            target=phone,
            plain_code=plain_code,
        )
        await self._sms.send_code(phone, plain_code)
        logger.info("sms_code_sent target=%s", phone)

    async def consume_sms_code_for_login(self, phone: str, code: str) -> None:
        """
        Validate SMS code and consume immediately (SMS login, no ticket).

        Args:
            phone: Normalized mobile number.
            code: Plaintext verification code.

        Raises:
            AppError: Invalid or expired code (``40010``).
        """
        settings = get_settings()
        phone = phone.strip()
        latest = await self._get_latest_challenge(channel=CHANNEL_SMS, target=phone)
        if latest is None or latest.code_hash is None:
            raise AppError(40010, "验证码错误或过期", http_status=400)
        if latest.consumed_at is not None:
            raise AppError(40010, "验证码错误或过期", http_status=400)

        expires_at = ensure_aware_utc(latest.expires_at)
        if expires_at <= now_utc():
            raise AppError(40010, "验证码错误或过期", http_status=400)

        code_ok = verify_password(code, latest.code_hash)
        if not code_ok and settings.debug and secrets.compare_digest(code, settings.debug_verify_code):
            code_ok = True
        if not code_ok:
            raise AppError(40010, "验证码错误或过期", http_status=400)

        latest.consumed_at = now_utc()
        await self._session.flush()
        logger.info("sms_login_code_consumed target=%s challenge_id=%s", phone, latest.id)

    async def confirm_sms(self, phone: str, code: str) -> str:
        """
        Confirm SMS code and return ``sms_ticket``.

        Args:
            phone: Mobile number.
            code: Plaintext code.

        Returns:
            str: One-time sms_ticket.

        Raises:
            AppError: Invalid/expired code (``40010``).
        """
        return await self._confirm_code_challenge(
            channel=CHANNEL_SMS,
            target=phone.strip(),
            code=code.strip(),
        )

    async def send_email(self, email: str) -> None:
        """
        Send an email verification code (persist challenge + call email provider).

        Args:
            email: Normalized email (lowercase recommended).

        Raises:
            AppError: Rate limit ``40011``; provider ``50100``.
        """
        email = email.strip().lower()
        await self._assert_send_interval(channel=CHANNEL_EMAIL, target=email)
        plain_code = self._generate_plain_code()
        await self._create_code_challenge(
            channel=CHANNEL_EMAIL,
            target=email,
            plain_code=plain_code,
        )
        await self._email.send_code(email, plain_code)
        logger.info("email_code_sent target=%s", email)

    async def confirm_email(self, email: str, code: str) -> str:
        """
        Confirm email code and return ``email_ticket``.

        Args:
            email: Email address.
            code: Plaintext code.

        Returns:
            str: One-time email_ticket.

        Raises:
            AppError: Invalid/expired code (``40010``).
        """
        return await self._confirm_code_challenge(
            channel=CHANNEL_EMAIL,
            target=email.strip().lower(),
            code=code.strip(),
        )

    async def submit_id(
        self,
        real_name: str,
        id_card: str,
        face_token: str | None = None,
    ) -> str:
        """
        Run identity verification and issue ``id_ticket``.

        DEBUG skips vendor call; production uses injected identity provider.

        Args:
            real_name: Legal name.
            id_card: ID card number (not stored raw).
            face_token: Face token for real-person mode.

        Returns:
            str: One-time id_ticket.

        Raises:
            AppError: Verification failure in production mode.
        """
        settings = get_settings()
        id_card = normalize_id_card(id_card)
        real_name = (real_name or "").strip()
        target_hash = hash_id_card(id_card)

        if settings.debug:
            try:
                from app.services.verification.providers import id_format

                id_format.validate_id_card_format(id_card)
            except AppError as exc:
                logger.info(
                    "debug_id_submit_format_skip code=%s message=%s",
                    exc.code,
                    exc.message,
                )
            mode_for_payload = "debug_skip"
        else:
            await self._identity.verify(
                real_name=real_name,
                id_card=id_card,
                face_token=face_token,
            )
            mode_for_payload = settings.id_verify_mode

        ticket = self._issue_ticket_token()
        payload = {
            "mode": mode_for_payload,
            "id_verify_mode": settings.id_verify_mode,
        }
        challenge = VerificationChallenge(
            channel=CHANNEL_ID,
            target=target_hash,
            code_hash=None,
            ticket=ticket,
            payload_json=json.dumps(payload, ensure_ascii=False),
            expires_at=now_utc() + timedelta(seconds=settings.verify_ticket_ttl_seconds),
            consumed_at=None,
        )
        self._session.add(challenge)
        await self._session.flush()
        logger.info(
            "id_ticket_issued challenge_id=%s mode=%s",
            challenge.id,
            mode_for_payload,
        )
        return ticket

    async def _load_valid_ticket(
        self,
        *,
        ticket: str,
        expected_channel: str,
        expected_target: str,
    ) -> VerificationChallenge:
        """
        Load and validate a ticket against channel, target, expiry, and consumption.

        Args:
            ticket: Client-submitted one-time ticket.
            expected_channel: Expected channel.
            expected_target: Expected target (phone / email / ID hash).

        Returns:
            VerificationChallenge: Valid row.

        Raises:
            AppError: Any mismatch (``40012``).
        """
        statement = select(VerificationChallenge).where(VerificationChallenge.ticket == ticket)
        result = await self._session.execute(statement)
        challenge = result.scalar_one_or_none()
        if challenge is None:
            raise AppError(40012, "ticket 无效或已过期", http_status=400)
        if challenge.channel != expected_channel:
            raise AppError(40012, "ticket 与核验渠道不匹配", http_status=400)
        if challenge.target != expected_target:
            raise AppError(40012, "ticket 与注册目标不匹配", http_status=400)
        if challenge.consumed_at is not None:
            raise AppError(40012, "ticket 已被使用", http_status=400)
        if ensure_aware_utc(challenge.expires_at) <= now_utc():
            raise AppError(40012, "ticket 无效或已过期", http_status=400)
        return challenge

    async def assert_register_tickets(
        self,
        *,
        require_phone: bool,
        require_email_code: bool,
        require_real_name: bool,
        email: str | None,
        phone: str | None,
        id_card: str | None,
        sms_ticket: str | None,
        email_ticket: str | None,
        id_ticket: str | None,
    ) -> None:
        """
        Validate registration tickets per feature flags (does not consume tickets).

        Args:
            require_phone: Require phone + sms_ticket.
            require_email_code: Require email + email_ticket.
            require_real_name: Require ID card + id_ticket.
            email / phone / id_card: Registration materials.
            sms_ticket / email_ticket / id_ticket: One-time tickets.

        Raises:
            AppError: Missing materials ``40017``; invalid ticket ``40012``.
        """
        missing_parts: list[str] = []
        if require_phone and (not phone or not sms_ticket):
            missing_parts.append("手机核验")
        if require_email_code and (not email or not email_ticket):
            missing_parts.append("邮箱核验")
        if require_real_name and (not id_card or not id_ticket):
            missing_parts.append("身份核验")
        if missing_parts:
            raise AppError(
                40017,
                f"缺少核验材料：{'、'.join(missing_parts)}",
                http_status=400,
            )

        if sms_ticket:
            if not phone:
                raise AppError(40012, "sms_ticket 缺少对应手机号", http_status=400)
            await self._load_valid_ticket(
                ticket=sms_ticket,
                expected_channel=CHANNEL_SMS,
                expected_target=phone.strip(),
            )
        if email_ticket:
            if not email:
                raise AppError(40012, "email_ticket 缺少对应邮箱", http_status=400)
            await self._load_valid_ticket(
                ticket=email_ticket,
                expected_channel=CHANNEL_EMAIL,
                expected_target=email.strip().lower(),
            )
        if id_ticket:
            if not id_card:
                raise AppError(40012, "id_ticket 缺少对应身份证号", http_status=400)
            normalized_id_card = normalize_id_card(id_card)
            await self._load_valid_ticket(
                ticket=id_ticket,
                expected_channel=CHANNEL_ID,
                expected_target=hash_id_card(normalized_id_card),
            )

    @staticmethod
    def get_modes() -> dict:
        """
        Return current verification modes and provider settings.

        Returns:
            dict: Serializable as ``ModesData``.
        """
        settings = get_settings()
        data = ModesData(
            debug=settings.debug,
            id_verify_mode=settings.id_verify_mode,
            sms_provider=settings.sms_provider,
            email_provider=settings.email_provider,
            id_two_factor_provider=settings.id_two_factor_provider,
            id_real_person_provider=settings.id_real_person_provider,
            register_require_phone=settings.register_require_phone,
            register_require_real_name=settings.register_require_real_name,
            register_require_email_code=settings.register_require_email_code,
        )
        return data.model_dump()


# ---------------------------------------------------------------------------
# 兼容包装：保持旧 import 路径与函数签名
# ---------------------------------------------------------------------------


async def send_sms(session: AsyncSession, phone: str) -> None:
    """兼容包装。"""
    await VerificationService(session).send_sms(phone)


async def consume_sms_code_for_login(
    session: AsyncSession,
    phone: str,
    code: str,
) -> None:
    """兼容包装。"""
    await VerificationService(session).consume_sms_code_for_login(phone, code)


async def confirm_sms(session: AsyncSession, phone: str, code: str) -> str:
    """兼容包装。"""
    return await VerificationService(session).confirm_sms(phone, code)


async def send_email(session: AsyncSession, email: str) -> None:
    """兼容包装。"""
    await VerificationService(session).send_email(email)


async def confirm_email(session: AsyncSession, email: str, code: str) -> str:
    """兼容包装。"""
    return await VerificationService(session).confirm_email(email, code)


async def submit_id(
    session: AsyncSession,
    real_name: str,
    id_card: str,
    face_token: str | None = None,
) -> str:
    """兼容包装。"""
    return await VerificationService(session).submit_id(real_name, id_card, face_token)


async def assert_register_tickets(
    session: AsyncSession,
    *,
    require_phone: bool,
    require_email_code: bool,
    require_real_name: bool,
    email: str | None,
    phone: str | None,
    id_card: str | None,
    sms_ticket: str | None,
    email_ticket: str | None,
    id_ticket: str | None,
) -> None:
    """兼容包装。"""
    await VerificationService(session).assert_register_tickets(
        require_phone=require_phone,
        require_email_code=require_email_code,
        require_real_name=require_real_name,
        email=email,
        phone=phone,
        id_card=id_card,
        sms_ticket=sms_ticket,
        email_ticket=email_ticket,
        id_ticket=id_ticket,
    )


def get_modes() -> dict:
    """兼容包装。"""
    return VerificationService.get_modes()
