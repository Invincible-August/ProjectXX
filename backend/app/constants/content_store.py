"""ContentStore 存储模式常量。"""

from __future__ import annotations

from enum import StrEnum


class ContentStoreMode(StrEnum):
    """配置读取模式（环境变量 CONTENT_STORE_MODE）。"""

    YAML_AUTHORITY = "yaml_authority"  # 测试：只读 YAML 底表
    YAML_BASE_DB_OVERLAY = "yaml_base_db_overlay"  # 现行：YAML ∪ DB 覆盖
    DB_AUTHORITY = "db_authority"  # 正式目标：DB 整域权威


CONTENT_STORE_MODE_YAML_AUTHORITY: str = ContentStoreMode.YAML_AUTHORITY  # 测试 YAML 权威
CONTENT_STORE_MODE_YAML_BASE_DB_OVERLAY: str = ContentStoreMode.YAML_BASE_DB_OVERLAY  # 现行合并
CONTENT_STORE_MODE_DB_AUTHORITY: str = ContentStoreMode.DB_AUTHORITY  # DB 权威

# 合法模式集合（校验用）
CONTENT_STORE_MODES: frozenset[str] = frozenset(m.value for m in ContentStoreMode)
