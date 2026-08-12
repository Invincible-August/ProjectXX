"""
异步 SQLAlchemy 引擎与会话工厂。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event

from app.core.config import get_settings

settings = get_settings()

# 创建异步引擎；DEBUG 开启时打印 SQL，便于开发排查
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
    """SQLite 默认关闭外键；开启后 ON DELETE CASCADE 才会删掉 heritage_claims。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# 仅 SQLite 注册（Postgres 等本身强制 FK）
if "sqlite" in str(settings.database_url):
    event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    提供请求级异步数据库会话，结束时提交或回滚。

    Yields:
        AsyncSession: SQLAlchemy 异步会话。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
