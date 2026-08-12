"""后台 API 包：独立鉴权前缀 ``/admin/*``。"""

from __future__ import annotations

from fastapi import APIRouter

from app.admin_api.auth import router as auth_router
from app.admin_api.config_routes import router as config_router
from app.admin_api.ops_routes import router as ops_router

admin_router = APIRouter()
admin_router.include_router(auth_router)
admin_router.include_router(config_router)
admin_router.include_router(ops_router)

__all__ = ["admin_router"]
