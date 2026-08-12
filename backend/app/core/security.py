"""
密码哈希与 JWT 编解码工具（M0 鉴权）。

密码只存 bcrypt 哈希；access / refresh 均为 HS256 JWT，claims 见 M0 §5.3。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# 通过 passlib 使用 bcrypt；明文密码禁止入库
_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(plain_password: str) -> str:
    """
    对明文密码做哈希，用于落库。

    Args:
        plain_password: 用户提交的明文密码。

    Returns:
        str: 不可逆的密码哈希。
    """
    return _password_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验明文密码是否与库中哈希匹配。

    Args:
        plain_password: 登录表单中的候选密码。
        password_hash: 此前写入数据库的哈希。

    Returns:
        bool: 匹配则为 True。
    """
    return _password_context.verify(plain_password, password_hash)


def create_token(
    *,
    user_id: int,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    """
    签发 JWT（access 或 refresh）。

    Args:
        user_id: 用户主键，写入 claim ``sub``（字符串）。
        token_type: ``\"access\"`` 或 ``\"refresh\"``，写入 claim ``type``。
        expires_delta: 相对当前 UTC 的有效期。

    Returns:
        str: 已签名的 JWT 字符串。
    """
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    # sub 必须是字符串，便于与 JWT 规范及多数库保持一致
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now_utc,
        "exp": now_utc + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user_id: int) -> tuple[str, int]:
    """
    签发短效 access_token。

    Args:
        user_id: 用户主键。

    Returns:
        tuple[str, int]: (JWT 字符串, expires_in 秒数)。
    """
    settings = get_settings()
    expire_minutes = settings.access_token_expire_minutes
    expires_delta = timedelta(minutes=expire_minutes)
    token = create_token(
        user_id=user_id,
        token_type="access",
        expires_delta=expires_delta,
    )
    # 返回剩余秒数，供前端展示或安排刷新时机
    return token, int(expires_delta.total_seconds())


def create_refresh_token(user_id: int, *, expire_days: int | None = None) -> str:
    """
    签发长效 refresh_token（用于「保存登录状态」跨页面刷新恢复会话）。

    Args:
        user_id: 用户主键。
        expire_days: 覆盖默认 ``REFRESH_TOKEN_EXPIRE_DAYS``；勾选「记住登录」时用默认长周期，
            未勾选时可传入较短天数。

    Returns:
        str: JWT 字符串。
    """
    settings = get_settings()
    days = expire_days if expire_days is not None else settings.refresh_token_expire_days
    return create_token(
        user_id=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=days),
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """
    校验并解码 JWT，并确认 ``type`` 与预期一致。

    Args:
        token: 客户端提交的 JWT。
        expected_type: 期望的令牌类型（access / refresh）。

    Returns:
        dict[str, Any]: 解码后的 claims。

    Raises:
        jwt.PyJWTError: 签名错误、过期或格式非法时由调用方捕获并映射业务码。
        ValueError: type 不匹配或缺少 sub 时抛出。
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != expected_type:
        raise ValueError(f"token type must be {expected_type}")
    if not payload.get("sub"):
        raise ValueError("token missing sub")
    # 拒绝后台令牌混入玩家鉴权（aud=admin）
    if payload.get("aud") == "admin":
        raise ValueError("admin token not allowed for player auth")
    return payload


def create_admin_access_token(admin_user_id: int, *, roles: list[str]) -> tuple[str, int]:
    """
    签发后台管理系统 access_token（独立密钥与 ``aud=admin``）。

    Args:
        admin_user_id: ``admin_users.id``。
        roles: 角色列表，写入 claim ``roles``。

    Returns:
        tuple[str, int]: (JWT, expires_in 秒)。
    """
    settings = get_settings()
    expire_minutes = settings.admin_access_token_expire_minutes
    expires_delta = timedelta(minutes=expire_minutes)
    now_utc = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(admin_user_id),
        "type": "access",
        "aud": "admin",
        "roles": list(roles),
        "iat": now_utc,
        "exp": now_utc + expires_delta,
    }
    token = jwt.encode(
        payload,
        settings.resolved_admin_jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, int(expires_delta.total_seconds())


def decode_admin_token(token: str) -> dict[str, Any]:
    """
    校验并解码后台 JWT（必须 ``aud=admin`` 且 type=access）。

    Args:
        token: Authorization Bearer 字符串。

    Returns:
        dict[str, Any]: claims。

    Raises:
        jwt.PyJWTError / ValueError: 无效令牌。
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.resolved_admin_jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience="admin",
    )
    if payload.get("type") != "access":
        raise ValueError("admin token type must be access")
    if not payload.get("sub"):
        raise ValueError("admin token missing sub")
    return payload
