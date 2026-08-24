"""运行时 DATABASE_URL：SQLite 多文件选用 + PostgreSQL 透传。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.runtime_url import (
    is_postgres_url,
    is_sqlite_url,
    resolve_sqlite_database_url,
    url_from_sqlite_file,
)


def _make_users_db(path: Path, n_users: int) -> None:
    """建最小 users 表并插入 n 行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL"
            ")",
        )
        for index in range(n_users):
            connection.execute(
                "INSERT INTO users (username) VALUES (?)",
                (f"u{index}",),
            )
        connection.commit()
    finally:
        connection.close()


def test_postgres_url_passthrough(tmp_path: Path) -> None:
    """PostgreSQL URL 不做文件发现。"""
    url = "postgresql+asyncpg://user:pass@localhost:5432/xiuxian"
    assert is_postgres_url(url)
    assert not is_sqlite_url(url)
    assert resolve_sqlite_database_url(url, backend_root=tmp_path) == url


def test_relative_sqlite_anchors_to_backend(tmp_path: Path) -> None:
    """相对路径锚定到 backend；有账号时尊重该文件。"""
    backend = tmp_path / "backend"
    backend.mkdir()
    db_path = backend / "xiuxian.db"
    _make_users_db(db_path, 3)
    resolved = resolve_sqlite_database_url(
        "sqlite+aiosqlite:///./xiuxian.db",
        backend_root=backend,
    )
    assert resolved == url_from_sqlite_file(db_path)
    assert "xiuxian.db" in resolved


def test_auto_select_backend_when_configured_empty(tmp_path: Path) -> None:
    """配置库无账号、backend 有账号时自动切到有数据的库。"""
    repo = tmp_path
    backend = repo / "backend"
    backend.mkdir()
    # 模拟 cwd 漂移：仓库根有空壳、backend 有真实账号
    empty_root = repo / "xiuxian.db"
    _make_users_db(empty_root, 0)
    # 0 用户仍建表；再造 backend 有 5 人
    rich = backend / "xiuxian.db"
    _make_users_db(rich, 5)
    # 故意配置成根目录绝对路径（无账号）
    configured = url_from_sqlite_file(empty_root)
    resolved = resolve_sqlite_database_url(configured, backend_root=backend)
    assert Path(resolved.split("sqlite+aiosqlite:///")[-1]) == rich.resolve()
