"""
对外账号号（public_uid）分配：前缀 M/P/T/G + 7 位数字。

数据库主键 ``users.id`` 仍由库自增；本模块只生成玩家可见的 ``user_id`` 字符串。
"""

from __future__ import annotations

import logging
import secrets
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.account import (
    PUBLIC_UID_DIGIT_LEN,
    USER_ID_PREFIX_EMAIL,
    USER_ID_PREFIX_GM,
    USER_ID_PREFIX_PHONE,
    USER_ID_PREFIX_TEST,
)
from app.core.config import get_settings
from app.db.models import User
from app.schemas.common import AppError

logger = logging.getLogger(__name__)

# 冲突重试次数
_ALLOC_ATTEMPTS = 48

RegisterChannel = Literal["email", "phone"]


def is_test_runtime() -> bool:
    """
    是否测试/开发运行时（对外账号统一 ``T`` 前缀）。

    Returns:
        bool: ``app_env`` 为 development/test/local，或 ``debug=True``。
    """
    settings = get_settings()
    env = (settings.app_env or "").strip().lower()
    if env in {"development", "test", "local", "dev"}:
        return True
    return bool(settings.debug)


def resolve_public_uid_prefix(
    *,
    phone: str | None,
    email: str | None,
    is_gm: bool = False,
) -> str:
    """
    按规则解析 public_uid 前缀。

    优先级：GM → 测试环境 → 手机注册 → 邮箱注册。

    Args:
        phone: 注册/绑定手机（有则视为手机注册通道）。
        email: 注册邮箱。
        is_gm: 是否 GM 账号。

    Returns:
        str: 单字符前缀。
    """
    if is_gm:
        return USER_ID_PREFIX_GM
    if is_test_runtime():
        return USER_ID_PREFIX_TEST
    if phone:
        return USER_ID_PREFIX_PHONE
    if email:
        return USER_ID_PREFIX_EMAIL
    # 兜底：邮箱通道（注册强制邮箱时基本不会走到）
    return USER_ID_PREFIX_EMAIL


def _random_digits() -> str:
    """生成 7 位数字串（可含前导 0）。"""
    return f"{secrets.randbelow(10**PUBLIC_UID_DIGIT_LEN):0{PUBLIC_UID_DIGIT_LEN}d}"


async def allocate_public_uid(
    session: AsyncSession,
    *,
    phone: str | None,
    email: str | None,
    is_gm: bool = False,
) -> str:
    """
    分配全局唯一的 public_uid。

    Args:
        session: 异步会话。
        phone: 手机号（决定 P 前缀，测试环境除外）。
        email: 邮箱（决定 M 前缀）。
        is_gm: GM 则用 G 前缀。

    Returns:
        str: 8 字符账号号。

    Raises:
        AppError: 多次冲突仍无法分配。
    """
    prefix = resolve_public_uid_prefix(phone=phone, email=email, is_gm=is_gm)
    for _ in range(_ALLOC_ATTEMPTS):
        candidate = f"{prefix}{_random_digits()}"
        exists = await session.scalar(
            select(User.id).where(User.public_uid == candidate).limit(1),
        )
        if exists is None:
            return candidate
    raise AppError(
        code=50000,
        message="无法分配唯一账号号，请稍后重试",
        http_status=500,
    )


async def rewrite_public_uid_for_gm(
    session: AsyncSession,
    user: User,
    *,
    is_gm: bool,
) -> str:
    """
    设置/取消 GM 时重写 public_uid 前缀（尽量保留后 7 位）。

    Args:
        session: 异步会话。
        user: 目标账号。
        is_gm: 目标 GM 状态。

    Returns:
        str: 新的 public_uid。
    """
    digits: str | None = None
    if user.public_uid and len(user.public_uid) == 1 + PUBLIC_UID_DIGIT_LEN:
        digits = user.public_uid[1:]
    if not digits or not digits.isdigit():
        digits = _random_digits()

    prefix = resolve_public_uid_prefix(
        phone=user.phone,
        email=user.email,
        is_gm=is_gm,
    )
    for _ in range(_ALLOC_ATTEMPTS):
        candidate = f"{prefix}{digits}"
        exists = await session.scalar(
            select(User.id).where(
                User.public_uid == candidate,
                User.id != user.id,
            ).limit(1),
        )
        if exists is None:
            user.public_uid = candidate
            return candidate
        digits = _random_digits()
    raise AppError(
        code=50000,
        message="无法重写 GM 账号号，请稍后重试",
        http_status=500,
    )


def backfill_missing_public_uids(connection: Connection) -> int:
    """
    启动补丁：为缺少 ``public_uid`` 的存量账号回填。

    同步连接版（供 ``prepare_database`` 的 ``run_sync`` 调用）。测试环境用 ``T``。

    Args:
        connection: SQLAlchemy 同步连接。

    Returns:
        int: 回填条数。
    """
    # 列可能尚未存在（极端顺序）；缺列则跳过
    cols = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(users)")).fetchall()
    }
    if "public_uid" not in cols:
        return 0

    has_gm = "is_gm" in cols
    select_sql = (
        "SELECT id, email, phone, COALESCE(is_gm, 0), public_uid FROM users"
        if has_gm
        else "SELECT id, email, phone, 0, public_uid FROM users"
    )
    rows = connection.execute(text(select_sql)).fetchall()
    # 已占用集合
    used: set[str] = {
        str(r[4]) for r in rows if r[4] is not None and str(r[4]).strip()
    }
    updated = 0
    test_env = is_test_runtime()

    for user_id, email, phone, is_gm_raw, public_uid in rows:
        if public_uid is not None and str(public_uid).strip():
            continue
        is_gm = bool(is_gm_raw)
        if is_gm:
            prefix = USER_ID_PREFIX_GM
        elif test_env:
            prefix = USER_ID_PREFIX_TEST
        elif phone:
            prefix = USER_ID_PREFIX_PHONE
        else:
            prefix = USER_ID_PREFIX_EMAIL

        candidate: str | None = None
        for _ in range(_ALLOC_ATTEMPTS):
            trial = f"{prefix}{_random_digits()}"
            if trial not in used:
                candidate = trial
                break
        if candidate is None:
            logger.error("public_uid backfill failed user_id=%s", user_id)
            continue
        connection.execute(
            text("UPDATE users SET public_uid = :uid WHERE id = :id"),
            {"uid": candidate, "id": int(user_id)},
        )
        used.add(candidate)
        updated += 1

    if updated:
        logger.info("backfilled public_uid for %s users", updated)

    # 唯一索引（允许多个 NULL 在 SQLite 里通常不冲突；回填后应无 NULL）
    try:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_users_public_uid ON users (public_uid)",
            ),
        )
    except Exception:  # noqa: BLE001 — 存量脏数据时仅记日志
        logger.warning("create unique index ix_users_public_uid skipped", exc_info=True)

    return updated
