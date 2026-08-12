"""
测试用异步 SQLite 会话工厂。

在 ``asyncio.run`` 结束前 ``dispose`` 引擎，避免 aiosqlite 工作线程
在事件循环已关闭后回调触发 ``PytestUnhandledThreadExceptionWarning``。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base

_T = TypeVar("_T")


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """在同步 pytest 用例中跑异步协程。"""
    return asyncio.run(coro)


@asynccontextmanager
async def open_test_session_factory(
    db_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """
    创建临时库、``create_all``，退出时释放引擎。

    Args:
        db_path: SQLite 文件路径（通常落在 ``tmp_path``）。

    Yields:
        绑定该引擎的 ``async_sessionmaker``。
    """
    engine: AsyncEngine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        future=True,
    )
    try:
        # 与生产会话一致：开启 SQLite 外键，CASCADE 才生效
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    finally:
        await engine.dispose()
