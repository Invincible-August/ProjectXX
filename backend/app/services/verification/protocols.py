"""
Verification provider Protocol definitions.

These structural interfaces decouple orchestration (``VerificationService``) from
concrete SMS / email / identity vendor implementations under ``providers/``.
"""

from __future__ import annotations

from typing import Protocol


class SmsProvider(Protocol):
    """
    SMS verification-code delivery adapter.

    Implementations must send a one-time code to the given phone number without
    persisting the plaintext code beyond the transport layer.
    """

    async def send_code(self, phone: str, code: str) -> None:
        """
        Send a verification code via SMS.

        Args:
            phone: Normalized mobile number.
            code: Plaintext verification code (must not be logged at INFO).

        Raises:
            AppError: Provider misconfiguration or delivery failure.
        """
        ...


class EmailProvider(Protocol):
    """
    Email verification-code delivery adapter.

    Implementations must send a one-time code to the given mailbox without
    persisting the plaintext code beyond the transport layer.
    """

    async def send_code(self, email: str, code: str) -> None:
        """
        Send a verification code via email.

        Args:
            email: Normalized email address.
            code: Plaintext verification code (must not be logged at INFO).

        Raises:
            AppError: Provider misconfiguration or delivery failure.
        """
        ...


class IdentityProvider(Protocol):
    """
    Real-name / ID-card verification adapter.

    Implementations perform format checks, two-factor, or real-person verification
    depending on deployment configuration.
    """

    async def verify(
        self,
        *,
        real_name: str,
        id_card: str,
        face_token: str | None = None,
    ) -> None:
        """
        Verify identity materials against the configured backend.

        Args:
            real_name: User's legal name (required for B/C modes).
            id_card: 18-digit ID card number (not persisted by the provider).
            face_token: Optional face-verification token (C mode).

        Raises:
            AppError: Verification failed or provider unavailable.
        """
        ...
