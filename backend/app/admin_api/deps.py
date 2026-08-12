"""
后台管理系统 HTTP 依赖（独立于玩家 ``get_current_user``）。
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_admin_token
from app.db.models import AdminUser
from app.db.session import get_db
from app.schemas.common import AppError
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_config_service import AdminConfigService

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_admin_auth_service(
    session: AsyncSession = Depends(get_db),
) -> AdminAuthService:
    """注入后台鉴权服务。"""
    return AdminAuthService(session)


async def get_admin_config_service(
    session: AsyncSession = Depends(get_db),
) -> AdminConfigService:
    """注入后台配置服务。"""
    return AdminConfigService(session)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminUser:
    """
    解析 ``Authorization: Bearer`` 后台 JWT。

    Raises:
        AppError: 40100 未认证。
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(code=40100, message="后台未认证", http_status=401)
    try:
        claims = decode_admin_token(credentials.credentials)
        admin_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        logger.warning("admin token rejected reason=%s", type(exc).__name__)
        raise AppError(code=40100, message="后台未认证或令牌无效", http_status=401) from exc
    return await auth.get_by_id(admin_id)
