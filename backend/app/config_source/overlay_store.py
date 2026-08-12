"""
进程内已发布覆盖层缓存。

因 ``get_game_config`` 为同步 ``lru_cache``，发布后写本 Store 再 ``clear_game_config_cache``，
避免在 Bundle 加载路径上做异步 DB IO。
"""

from __future__ import annotations

import logging
import threading
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


class OverlayStore:
    """
    线程安全的域覆盖层内存表。

    键为 domain_id（如 ``pets``），值为可 deep_merge 到 YAML 的 partial dict。
    对外 ``get`` 返回深拷贝；内部热路径可用 ``get_ref`` / ``has`` 避免多余拷贝。
    """

    _lock = threading.RLock()
    _overlays: dict[str, dict[str, Any]] = {}
    _versions: dict[str, int] = {}

    @classmethod
    def has(cls, domain_id: str) -> bool:
        """是否存在已发布覆盖（不拷贝）。"""
        with cls._lock:
            return domain_id in cls._overlays

    @classmethod
    def domain_ids(cls) -> list[str]:
        """已发布覆盖的域 ID 列表（不拷贝正文）。"""
        with cls._lock:
            return list(cls._overlays.keys())

    @classmethod
    def versions_map(cls) -> dict[str, int]:
        """domain_id → version（浅拷贝版本表）。"""
        with cls._lock:
            return dict(cls._versions)

    @classmethod
    def get(cls, domain_id: str) -> dict[str, Any] | None:
        """
        读取某域已发布覆盖层副本。

        Args:
            domain_id: 内容域 ID。

        Returns:
            dict | None: 无发布记录时 None。
        """
        with cls._lock:
            raw = cls._overlays.get(domain_id)
            return deepcopy(raw) if raw is not None else None

    @classmethod
    def get_ref(cls, domain_id: str) -> dict[str, Any] | None:
        """
        返回内部引用（只读约定：调用方禁止原地修改）。

        供 ``deep_merge`` 等会先拷贝 base/overlay 的路径使用，减少一次 deepcopy。
        """
        with cls._lock:
            return cls._overlays.get(domain_id)

    @classmethod
    def get_version(cls, domain_id: str) -> int:
        """已发布版本号；无记录为 0。"""
        with cls._lock:
            return int(cls._versions.get(domain_id, 0))

    @classmethod
    def set(cls, domain_id: str, overlay: dict[str, Any], *, version: int) -> None:
        """
        写入或替换某域覆盖层（发布成功后调用）。

        Args:
            domain_id: 内容域 ID。
            overlay: 覆盖层正文。
            version: 发布版本号。
        """
        with cls._lock:
            cls._overlays[domain_id] = deepcopy(overlay)
            cls._versions[domain_id] = int(version)
        logger.info("overlay store set domain=%s version=%s", domain_id, version)

    @classmethod
    def remove(cls, domain_id: str) -> None:
        """清除某域覆盖（回滚到纯 YAML）。"""
        with cls._lock:
            cls._overlays.pop(domain_id, None)
            cls._versions.pop(domain_id, None)
        logger.info("overlay store remove domain=%s", domain_id)

    @classmethod
    def replace_all(
        cls,
        overlays: dict[str, dict[str, Any]],
        versions: dict[str, int] | None = None,
    ) -> None:
        """
        启动时从 DB 灌入全部已发布覆盖。

        Args:
            overlays: domain_id → overlay。
            versions: 可选版本表。
        """
        with cls._lock:
            cls._overlays = {key: deepcopy(value) for key, value in overlays.items()}
            cls._versions = {
                key: int((versions or {}).get(key, 1)) for key in overlays
            }
        logger.info("overlay store loaded domains=%s", list(overlays.keys()))

    @classmethod
    def snapshot(cls) -> dict[str, dict[str, Any]]:
        """调试用：全部覆盖层深拷贝（开销大，摘要请用 domain_ids/versions_map）。"""
        with cls._lock:
            return {key: deepcopy(value) for key, value in cls._overlays.items()}
