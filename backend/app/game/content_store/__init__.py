"""
ContentStore：配置读取唯一门面（ARCH-R02）。

由环境变量 ``CONTENT_STORE_MODE``（见 ``backend/.env``）切换：

- ``yaml_authority``：只读 YAML，**忽略** DB OverlayStore（本地/单测推荐）
- ``yaml_base_db_overlay``：YAML ∪ 已发布 overlay（现行默认）
- ``db_authority``：以已发布 DB 文档为权威；无发布记录时回退 YAML 种子；
  当前发布体仍为 overlay 形态时，与「YAML∪overlay」合并结果一致并打日志
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from app.config_source.merge import merge_domain_overlay
from app.config_source.overlay_store import OverlayStore
from app.config_source.registry import DOMAIN_REGISTRY, domain_id_for_filename
from app.config_source.yaml_source import get_shared_yaml_source
from app.constants.content_store import CONTENT_STORE_MODES, ContentStoreMode

logger = logging.getLogger(__name__)


def _settings_mode() -> str:
    """自 Settings 读取模式；非法值回退现行合并。"""
    try:
        from app.core.config import get_settings

        raw = str(getattr(get_settings(), "content_store_mode", "") or "").strip()
    except Exception:  # noqa: BLE001 — 配置未就绪时回退
        raw = ""
    if not raw:
        return ContentStoreMode.YAML_BASE_DB_OVERLAY
    if raw not in CONTENT_STORE_MODES:
        logger.warning(
            "invalid CONTENT_STORE_MODE=%s; fallback %s",
            raw,
            ContentStoreMode.YAML_BASE_DB_OVERLAY,
        )
        return ContentStoreMode.YAML_BASE_DB_OVERLAY
    return raw


class ContentStore:
    """
    域配置加载门面。

    玩法 Bundle（``realm_config``）与 ``game.*`` 工厂应经本类读配置，
    禁止业务代码直接 ``open(yaml)`` 或绕过模式读 OverlayStore。
    """

    @classmethod
    def mode(cls) -> str:
        """当前存储模式（已校验）。"""
        return _settings_mode()

    @classmethod
    def list_domains(cls) -> list[str]:
        """已登记 admin domain_id 列表。"""
        return sorted(DOMAIN_REGISTRY.keys())

    @classmethod
    def filename_for(cls, domain_id: str) -> str:
        """
        domain_id → YAML 文件名。

        Raises:
            KeyError: 未登记域。
        """
        meta = DOMAIN_REGISTRY.get(domain_id)
        if meta is None:
            raise KeyError(f"unknown content domain_id: {domain_id}")
        return meta.filename

    @classmethod
    def load(cls, domain_id: str, *, copy: bool = True) -> dict[str, Any]:
        """
        按当前 ``CONTENT_STORE_MODE`` 加载某域 raw dict。

        Args:
            domain_id: 注册表域 ID。
            copy: 是否保证返回可原地修改的副本。

        Returns:
            dict[str, Any]: 域根对象。
        """
        return cls.load_filename(cls.filename_for(domain_id), copy=copy)

    @classmethod
    def load_filename(cls, filename: str, *, copy: bool = True) -> dict[str, Any]:
        """
        按文件名加载（供 ``realm_config._load_yaml``）。

        未登记域：始终纯 YAML（无 overlay 概念）。
        已登记域：行为随 ``CONTENT_STORE_MODE``。

        Args:
            filename: 如 ``pets.yaml``。
            copy: 是否深拷贝。

        Returns:
            dict[str, Any]: 合并或底表结果。

        Raises:
            FileNotFoundError: YAML 缺失。
            ValueError: 根节点非 mapping。
        """
        try:
            base = get_shared_yaml_source().load_raw(filename, copy=False)
        except FileNotFoundError:
            raise
        except ValueError:
            raise

        domain_id = domain_id_for_filename(filename)
        mode = cls.mode()

        # 未进后台注册表：无 DB 覆盖概念
        if domain_id is None:
            return deepcopy(base) if copy else base

        if mode == ContentStoreMode.YAML_AUTHORITY:
            logger.debug("content_store yaml_authority skip overlay domain=%s", domain_id)
            return deepcopy(base) if copy else base

        overlay = OverlayStore.get_ref(domain_id)
        if not overlay:
            if mode == ContentStoreMode.DB_AUTHORITY:
                logger.debug(
                    "content_store db_authority no published domain=%s; use yaml seed",
                    domain_id,
                )
            return deepcopy(base) if copy else base

        if mode == ContentStoreMode.DB_AUTHORITY:
            # 正式目标：整域 DB 权威。现行 published 仍是 overlay 补丁形态，
            # 故仍与 YAML 做域感知合并（等价于 seed∪published）；整域迁库后可改为直接用 overlay。
            logger.debug(
                "content_store db_authority merge published overlay domain=%s version=%s",
                domain_id,
                OverlayStore.get_version(domain_id),
            )
        else:
            logger.debug(
                "content_store yaml_base_db_overlay domain=%s version=%s",
                domain_id,
                OverlayStore.get_version(domain_id),
            )

        merged = merge_domain_overlay(domain_id, base, overlay)
        # merge_domain_overlay 已返回新 dict；copy=False 时仍安全（不共享 YAML 缓存）
        return merged if copy else merged


def load_domain(domain_id: str, *, copy: bool = True) -> dict[str, Any]:
    """``ContentStore.load`` 快捷入口。"""
    return ContentStore.load(domain_id, copy=copy)
