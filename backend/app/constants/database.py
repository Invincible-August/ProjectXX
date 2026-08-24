"""
运行时数据库 URL 解析（开发计划 §0.6.3）。

账号/角色等 **运行时实体** 一律走 ``DATABASE_URL``（测试 SQLite / 正式 PostgreSQL）。
玩法设定走 ContentStore（测试 YAML / 正式 DB 发布层），与实体库分离。
"""

from __future__ import annotations

# 默认 SQLite 文件名（相对 backend/）
DEFAULT_SQLITE_FILENAME = "xiuxian.db"

# 异步 SQLite 驱动前缀
SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite:///"

# 同步 SQLite 前缀（发现/探测用）
SQLITE_SYNC_PREFIX = "sqlite:///"
