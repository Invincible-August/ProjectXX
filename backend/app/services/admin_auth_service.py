"""后台鉴权应用服务：登录、bootstrap、当前用户。"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_admin_access_token,
    hash_password,
    verify_password,
)
from app.db.models import AdminUser
from app.schemas.common import AppError
from app.services.admin_rbac import (
    ROLE_ADMIN,
    ROLE_EDITOR_BALANCE,
    ROLE_EDITOR_CONTENT,
    ROLE_PUBLISHER,
    ROLE_VIEWER,
    parse_roles,
    roles_to_storage,
)

logger = logging.getLogger(__name__)


class AdminAuthService:
    """后台账号用例。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 DB 会话。
        """
        self._session = session

    async def ensure_bootstrap_admin(self) -> None:
        """
        若库中无任何管理员且开关开启，创建默认超管。

        默认角色含 viewer/editor_*/publisher/admin，便于本地一次登录验收全流程。
        """
        settings = get_settings()
        if not settings.admin_bootstrap_enabled:
            return
        existing = await self._session.scalar(select(AdminUser.id).limit(1))
        if existing is not None:
            return
        username = settings.admin_bootstrap_username.strip() or "admin"
        password = settings.admin_bootstrap_password
        if not password:
            logger.warning("ADMIN_BOOTSTRAP_ENABLED but empty password; skip seed")
            return
        admin = AdminUser(
            username=username,
            password_hash=hash_password(password),
            display_name="Bootstrap Admin",
            roles=roles_to_storage(
                [
                    ROLE_VIEWER,
                    ROLE_EDITOR_CONTENT,
                    ROLE_EDITOR_BALANCE,
                    ROLE_PUBLISHER,
                    ROLE_ADMIN,
                ],
            ),
            is_active=True,
        )
        self._session.add(admin)
        await self._session.commit()
        logger.info("admin bootstrap user created username=%s", username)

    async def login(self, *, username: str, password: str) -> dict:
        """
        校验账号密码并签发后台 access_token。

        Args:
            username: 登录名。
            password: 明文密码。

        Returns:
            dict: token 与用户摘要。

        Raises:
            AppError: 40110 凭据错误；40310 禁用。
        """
        row = await self._session.scalar(
            select(AdminUser).where(AdminUser.username == username.strip()),
        )
        if row is None or not verify_password(password, row.password_hash):
            raise AppError(code=40110, message="后台账号或密码错误", http_status=401)
        if not row.is_active:
            raise AppError(code=40310, message="后台账号已禁用", http_status=403)
        roles = parse_roles(row.roles)
        token, expires_in = create_admin_access_token(row.id, roles=roles)
        logger.info("admin login ok user_id=%s roles=%s", row.id, roles)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "user": self._public_user(row, roles),
        }

    async def get_by_id(self, admin_user_id: int) -> AdminUser:
        """
        按主键加载活跃管理员。

        Raises:
            AppError: 40100 不存在或禁用。
        """
        row = await self._session.get(AdminUser, admin_user_id)
        if row is None or not row.is_active:
            raise AppError(code=40100, message="后台未认证或账号无效", http_status=401)
        return row

    @staticmethod
    def _public_user(row: AdminUser, roles: list[str] | None = None) -> dict:
        """对外用户摘要。"""
        return {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name or row.username,
            "roles": roles if roles is not None else parse_roles(row.roles),
        }
