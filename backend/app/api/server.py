"""健康检查路由（M0 §5.1）。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db
from app.schemas.common import success
from app.services.auth_service import ping_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/server", tags=["server"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)) -> dict:
    """
    返回服务健康状态，并探测数据库。

    Args:
        session: 注入的异步数据库会话。

    Returns:
        dict: 含 status / app / env / db / time 的统一信封。
    """
    settings = get_settings()
    db_status = "ok"
    try:
        await ping_database(session)
    except Exception:
        logger.exception("database health check failed")
        db_status = "error"

    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    from app.db.runtime_url import is_postgres_url, is_sqlite_url, sqlite_file_from_url

    database_url = settings.database_url
    if is_sqlite_url(database_url):
        dialect = "sqlite"
        db_file = sqlite_file_from_url(database_url)
        database_target = str(db_file) if db_file is not None else database_url
    elif is_postgres_url(database_url):
        dialect = "postgresql"
        # 不回显密码：只报驱动与库名占位
        database_target = "postgresql+asyncpg://***"
    else:
        dialect = "other"
        database_target = "***"

    return success(
        {
            "status": "ok" if db_status == "ok" else "degraded",
            "app": settings.app_name,
            "env": settings.app_env,
            "db": db_status,
            "database_dialect": dialect,
            "database_target": database_target,
            "content_store_mode": settings.content_store_mode,
            "time": utc_now,
        },
    )
