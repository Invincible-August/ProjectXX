"""
防守快照规范化与内容哈希（M3战斗成型设计.md §6.1）。

哈希用于快照版本比对：同一份内容（键序无关）必然得到同一哈希。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# 参与哈希的字段白名单（时间戳等易变字段不入哈希）
_HASH_FIELDS = (
    "schema_version",
    "character_id",
    "dao_name",
    "realm",
    "breakthrough_grade",
    "formation_id",
    "units",
)


def compute_content_hash(payload: dict[str, Any]) -> str:
    """
    计算快照内容哈希。

    规范化规则：仅取白名单字段 → JSON 序列化（键排序、紧凑分隔、禁 ASCII 转义）
    → SHA-256。

    参数:
        payload: 快照 payload dict。

    返回:
        str: ``sha256:<hex>``。
    """
    canonical = {key: payload.get(key) for key in _HASH_FIELDS}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
