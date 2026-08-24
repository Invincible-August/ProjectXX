"""Content / Law / Environment / Org 包占位（S1-1：导出 ABC 钩子）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from app.game.ability.grant import GrantSource


class ContentEntity(ABC):
    """内容进度/定义基类（功法、配方、秘境定义等）。"""

    @abstractmethod
    def get_content_kind(self) -> str:
        ...

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return ()


class LawEntity(ABC):
    """大道/道主/克制基类。"""

    @abstractmethod
    def get_law_kind(self) -> str:
        ...

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return ()


class EnvironmentEntity(ABC):
    """天气/时辰/地形/阵法层。"""

    @abstractmethod
    def get_env_kind(self) -> str:
        ...

    def as_side_mod(self) -> dict[str, Any]:
        """战场/挂机侧修；默认空。"""
        return {}


class OrganizationEntity(ABC):
    """宗门等组织。"""

    @abstractmethod
    def get_org_kind(self) -> str:
        ...

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return ()
