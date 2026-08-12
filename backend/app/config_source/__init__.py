"""
玩法配置源抽象（M2-D01）。

YAML 底表 + 进程内已发布覆盖层；业务只经 ``realm_config.get_game_config()`` 读 Bundle。
"""

from __future__ import annotations

from app.config_source.merge import deep_merge
from app.config_source.overlay_store import OverlayStore
from app.config_source.registry import (
    DOMAIN_REGISTRY,
    DomainMeta,
    filename_for_domain,
    get_domain_meta,
    list_domains,
)
from app.config_source.runtime import RuntimeConfigReloader
from app.config_source.yaml_source import (
    YamlConfigSource,
    get_shared_yaml_source,
)

__all__ = [
    "DOMAIN_REGISTRY",
    "DomainMeta",
    "OverlayStore",
    "RuntimeConfigReloader",
    "YamlConfigSource",
    "deep_merge",
    "filename_for_domain",
    "get_domain_meta",
    "get_shared_yaml_source",
    "list_domains",
]
