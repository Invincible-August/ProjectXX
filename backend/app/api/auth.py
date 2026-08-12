"""鉴权相关 HTTP 路由（注册 / 登录 / 刷新 / 当前用户）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import get_auth_service, get_current_user
from app.core.time_utils import to_utc_iso
from app.db.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResult,
)
from app.schemas.common import success
from app.services.auth_service import AuthService, auth_me_to_dict, token_payload_to_dict

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
async def register(
    payload: RegisterRequest,
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """
    注册新账号（本接口不发放令牌；需再调登录）。

    Body 可含手机/实名与核验 ticket；是否强制由 ``REGISTER_REQUIRE_*`` 配置控制。
    三者皆关时仅需邮箱 + 密码。

    Args:
        payload: 密码、邮箱及可选核验字段。
        auth: 鉴权应用服务。

    Returns:
        dict: 包含注册结果的统一响应信封。
    """
    result: RegisterResult = await auth.register(payload)
    return success(
        {
            "user_id": result.user_id,
            "email": result.email,
            "phone": result.phone,
            "display_name": result.display_name,
            "created_at": to_utc_iso(result.created_at),
        },
    )


@router.post("/login", response_model=None)
async def login(
    payload: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """
    登录并签发 access + refresh。

    支持三种方式（``login_method``）：
    - ``password``：``account``（邮箱或手机号）+ ``password``
    - ``sms``：``phone`` + ``sms_code``（须先 ``POST /verification/sms/send``）

    ``remember_me=true``（默认）签发长效 refresh；``false`` 则短效 refresh。

    Args:
        payload: 登录方式与对应凭证、是否记住登录。
        auth: 鉴权应用服务。

    Returns:
        dict: 含双令牌与用户摘要的统一信封。
    """
    tokens = await auth.login(payload)
    return success(token_payload_to_dict(tokens))


@router.post("/refresh", response_model=None)
async def refresh(
    payload: RefreshRequest,
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    """
    使用 refresh_token 换取新的双令牌（页面刷新后恢复会话的关键步骤）。

    Args:
        payload: 仅含 refresh_token。
        auth: 鉴权应用服务。

    Returns:
        dict: 与登录相同结构的令牌信封。
    """
    tokens = await auth.refresh(payload.refresh_token)
    return success(token_payload_to_dict(tokens))


@router.get("/me", response_model=None)
async def me(
    auth: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    返回当前 Bearer 用户资料（刷新页面后前端用此接口恢复用户态）。

    Args:
        auth: 鉴权应用服务。
        current_user: 由依赖注入解析出的当前用户。

    Returns:
        dict: 含 id / email / phone / display_name / has_character / created_at 的信封。
    """
    profile = await auth.profile(current_user)
    return success(auth_me_to_dict(profile))


@router.post("/change-password", response_model=None)
async def change_password(
    payload: ChangePasswordRequest,
    auth: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """校验原密码后更新为新密码。"""
    data = await auth.change_password(
        current_user,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
    return success(data)
