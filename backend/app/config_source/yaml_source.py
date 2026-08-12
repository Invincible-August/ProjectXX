"""
YAML 底表 ConfigSource（带 mtime 内存缓存，降低重复读盘）。

``get_game_config`` / 后台预览会频繁读同一批文件；缓存后发布热更主要成本回到解析与合并。
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config_data"


class ConfigSource(Protocol):
    """
    可插拔配置源协议（M2-D01）。

    实现须返回可被 ``realm_config`` 解析器消费的 raw dict。
    """

    def load_raw(self, filename: str, *, copy: bool = True) -> dict[str, Any]:
        """加载单个 YAML 文件名为根 mapping。"""
        ...


class YamlConfigSource:
    """
    从 ``config_data/*.yaml`` 读取底表。

    按文件 ``st_mtime_ns`` 缓存解析结果；磁盘未变则跳过 IO 与 YAML 解析。
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        *,
        enable_cache: bool = True,
    ) -> None:
        """
        Args:
            config_dir: 覆盖默认配置目录（测试注入）。
            enable_cache: False 时每次读盘（测试可关）。
        """
        self._config_dir = config_dir or _DEFAULT_CONFIG_DIR
        self._enable_cache = enable_cache
        self._lock = RLock()
        # filename → (mtime_ns, raw_dict)
        self._cache: dict[str, tuple[int, dict[str, Any]]] = {}

    @property
    def config_dir(self) -> Path:
        """配置根目录。"""
        return self._config_dir

    def clear_cache(self) -> None:
        """清空 YAML 解析缓存（测试或强制重载）。"""
        with self._lock:
            self._cache.clear()

    def load_raw(self, filename: str, *, copy: bool = True) -> dict[str, Any]:
        """
        读取 YAML 文件。

        Args:
            filename: 相对文件名，如 ``pets.yaml``。
            copy: True 返回深拷贝（对外安全）；False 返回缓存引用
                （仅当调用方保证不原地修改，如随后 ``deep_merge`` 会先拷贝 base）。

        Returns:
            dict[str, Any]: 根对象。

        Raises:
            FileNotFoundError: 文件不存在。
            ValueError: 根不是 mapping。
        """
        path = self._config_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"config file missing: {path}")

        mtime_ns = path.stat().st_mtime_ns
        if self._enable_cache:
            with self._lock:
                hit = self._cache.get(filename)
                if hit is not None and hit[0] == mtime_ns:
                    raw = hit[1]
                    return deepcopy(raw) if copy else raw

        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"config root must be mapping: {filename}")

        if self._enable_cache:
            with self._lock:
                self._cache[filename] = (mtime_ns, loaded)
            logger.debug("yaml cache store file=%s mtime_ns=%s", filename, mtime_ns)

        return deepcopy(loaded) if copy else loaded


_shared_yaml_source: YamlConfigSource | None = None
_shared_lock = RLock()


def get_shared_yaml_source() -> YamlConfigSource:
    """
    进程内共享 YAML 源（带缓存）。

    ``realm_config`` 与 ``AdminConfigService`` 共用，避免重复读盘与重复缓存。
    """
    global _shared_yaml_source
    with _shared_lock:
        if _shared_yaml_source is None:
            _shared_yaml_source = YamlConfigSource()
        return _shared_yaml_source


def reset_shared_yaml_source_for_tests() -> None:
    """测试用：重置共享单例。"""
    global _shared_yaml_source
    with _shared_lock:
        if _shared_yaml_source is not None:
            _shared_yaml_source.clear_cache()
        _shared_yaml_source = None
