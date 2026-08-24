"""
运行时数据库 URL：SQLite 相对路径锚定 + 多份 xiuxian.db 自动选用有账号的库。

正式环境 ``postgresql+asyncpg://...`` 原样返回，不做文件发现。
业务层只依赖 SQLAlchemy 会话，不感知 SQLite / PostgreSQL。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.constants.database import (
    DEFAULT_SQLITE_FILENAME,
    SQLITE_ASYNC_PREFIX,
    SQLITE_SYNC_PREFIX,
)

logger = logging.getLogger(__name__)


def is_sqlite_url(database_url: str) -> bool:
    """是否为 SQLite 连接串。"""
    raw = (database_url or "").lower()
    return raw.startswith("sqlite")


def is_postgres_url(database_url: str) -> bool:
    """是否为 PostgreSQL 连接串。"""
    raw = (database_url or "").lower()
    return raw.startswith("postgresql") or raw.startswith("postgres")


def sqlite_file_from_url(database_url: str) -> Path | None:
    """
    从 SQLite URL 取出文件路径。

    Args:
        database_url: SQLAlchemy URL。

    Returns:
        Path | None: 文件路径；非 SQLite 则 None。
    """
    for scheme in (SQLITE_ASYNC_PREFIX, SQLITE_SYNC_PREFIX):
        if not database_url.startswith(scheme):
            continue
        raw_path = database_url[len(scheme) :]
        if not raw_path or raw_path == ":memory:":
            return None
        return Path(raw_path)
    return None


def url_from_sqlite_file(path: Path, *, async_driver: bool = True) -> str:
    """文件路径 → SQLAlchemy SQLite URL。"""
    prefix = SQLITE_ASYNC_PREFIX if async_driver else SQLITE_SYNC_PREFIX
    return f"{prefix}{path.resolve().as_posix()}"


def _count_sqlite_users(path: Path) -> int:
    """读取 SQLite 中 users 行数；文件或表不存在则 0。"""
    if not path.is_file():
        return 0
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'",
            ).fetchone()
            if not row or int(row[0]) < 1:
                return 0
            count_row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
            return int(count_row[0] if count_row else 0)
        finally:
            connection.close()
    except sqlite3.Error:
        logger.debug("sqlite inspect failed path=%s", path, exc_info=True)
        return 0


def resolve_sqlite_database_url(database_url: str, *, backend_root: Path) -> str:
    """
    相对路径锚定到 ``backend/``，并在多份 ``xiuxian.db`` 中选用账号最多的一份。

    仓库根目录历史上会因 cwd 漂移再生成一份空/旧库；测试账号在 ``backend/xiuxian.db``。
    PostgreSQL URL 原样返回。

    Args:
        database_url: 原始 DATABASE_URL。
        backend_root: backend 目录绝对路径。

    Returns:
        str: 最终连接串。
    """
    if not is_sqlite_url(database_url):
        return database_url

    anchored = _anchor_relative_sqlite(database_url, backend_root=backend_root)
    configured = sqlite_file_from_url(anchored)
    # 单测/自定义文件名（非产品默认 xiuxian.db）必须原样使用，禁止扫仓库里的旧库
    if configured is not None and configured.name != DEFAULT_SQLITE_FILENAME:
        return anchored

    repo_root = backend_root.parent
    canonical = (backend_root / DEFAULT_SQLITE_FILENAME).resolve()
    candidates: list[Path] = []
    for path in (configured, canonical, repo_root / DEFAULT_SQLITE_FILENAME):
        if path is None:
            continue
        resolved = path.resolve()
        if resolved not in candidates:
            candidates.append(resolved)

    scored: list[tuple[int, Path]] = []
    for path in candidates:
        n_users = _count_sqlite_users(path)
        scored.append((n_users, path))
        logger.info("sqlite candidate path=%s users=%s exists=%s", path, n_users, path.is_file())

    if not scored:
        return anchored

    def _rank(item: tuple[int, Path]) -> tuple[int, int]:
        n_users, path = item
        # 账号多者优先；并列时优先 backend/xiuxian.db
        return (n_users, 1 if path == canonical else 0)

    best_users, best_path = max(scored, key=_rank)
    chosen = best_path if best_users > 0 else (configured.resolve() if configured is not None else best_path)
    if configured is not None and chosen != configured.resolve():
        logger.warning(
            "sqlite auto-select path=%s users=%s (configured=%s); "
            "账号/角色运行时数据以该文件为准，玩法设定仍走 YAML/ContentStore",
            chosen,
            best_users,
            configured.resolve(),
        )
    return url_from_sqlite_file(
        chosen,
        async_driver="aiosqlite" in database_url,
    )


def _anchor_relative_sqlite(database_url: str, *, backend_root: Path) -> str:
    """将相对 SQLite 路径锚定到 backend/。"""
    for scheme in (SQLITE_ASYNC_PREFIX, SQLITE_SYNC_PREFIX):
        if not database_url.startswith(scheme):
            continue
        raw_path = database_url[len(scheme) :]
        if raw_path.startswith("/") or (len(raw_path) >= 3 and raw_path[1] == ":"):
            return database_url
        if raw_path in ("", ":memory:"):
            return database_url
        absolute = (backend_root / raw_path).resolve()
        return f"{scheme}{absolute.as_posix()}"
    return database_url
