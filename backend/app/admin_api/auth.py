"""后台鉴权路由：``/admin/auth/*``。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.admin_api.deps import get_admin_auth_service, get_current_admin
from app.db.models import AdminUser
from app.schemas.admin import AdminLoginRequest
from app.schemas.common import success
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_rbac import parse_roles

router = APIRouter(prefix="/auth", tags=["admin-auth"])


@router.post("/login", response_model=None)
async def admin_login(
    payload: AdminLoginRequest,
    auth: AdminAuthService = Depends(get_admin_auth_service),
) -> dict:
    """
    后台登录（独立账号体系，非玩家 JWT）。

    Returns:
        dict: access_token + user。
    """
    data = await auth.login(username=payload.username, password=payload.password)
    return success(data)


@router.get("/me", response_model=None)
async def admin_me(admin: AdminUser = Depends(get_current_admin)) -> dict:
    """当前后台用户。"""
    return success(
        {
            "id": admin.id,
            "username": admin.username,
            "display_name": admin.display_name or admin.username,
            "roles": parse_roles(admin.roles),
        },
    )
