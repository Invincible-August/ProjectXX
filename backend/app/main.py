"""
FastAPI 应用入口：配置、CORS、生命周期、异常映射。

Schema 补丁与一次性迁移见 ``app.db.bootstrap``。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.api.server import health_check, router as health_router
from app.admin_api import admin_router
from app.admin_spa import mount_admin_spa
from app.core.config import get_settings
from app.core.deps import get_db
from app.core.logging_config import setup_logging
from app.db import models  # noqa: F401 — 导入模型以注册到 metadata
from app.db.bootstrap import prepare_database
from app.db.session import engine, AsyncSessionLocal
from app.schemas.common import AppError, failure

settings = get_settings()
setup_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    应用生命周期：schema → 后台 bootstrap → 覆盖层灌入 → 校验玩法 Bundle。

    Yields:
        None: 应用运行期间。
    """
    await prepare_database(engine)
    logger.info("database schema ready url=%s", settings.database_url)

    # ADM：种子管理员 + 已发布覆盖灌入 OverlayStore（须在 get_game_config 前）
    from app.config_source.runtime import RuntimeConfigReloader
    from app.services.admin_auth_service import AdminAuthService
    from app.services.admin_config_service import AdminConfigService

    async with AsyncSessionLocal() as session:
        await AdminAuthService(session).ensure_bootstrap_admin()
        await AdminConfigService(session).load_published_into_store()

    RuntimeConfigReloader.reload(reason="boot")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.4.0-adm",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    # M3 布阵保存预设使用 PUT；后台草稿/条目亦用 PUT/DELETE
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

# 玩家 API：/api/v1/*
app.include_router(api_router, prefix=settings.api_prefix)
# 后台 API：/admin/*（独立鉴权，非玩家 JWT）
app.include_router(admin_router, prefix="/admin")
# 无前缀：/server/health（与版本化路径同实现）
app.include_router(health_router)
# 运营后台前端：/management（与 API 同端口）
mount_admin_spa(app)


@app.get("/health", include_in_schema=False)
async def root_health(session: AsyncSession = Depends(get_db)) -> dict:
    """
    根路径健康检查别名，兼容 README / VITE_HEALTH_URL 的 GET /health。

    正式联调前端「检测状态」走的是 GET /api/v1/server/health。
    """
    return await health_check(session)


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    """将业务异常 AppError 映射为统一 JSON 信封。"""
    return JSONResponse(
        status_code=exc.http_status,
        content=failure(exc.code, exc.message),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """将请求参数校验失败映射为错误码 40000。"""
    first_error = exc.errors()[0] if exc.errors() else {}
    detail = first_error.get("msg", "请求参数非法")
    return JSONResponse(
        status_code=400,
        content=failure(40000, str(detail)),
    )
