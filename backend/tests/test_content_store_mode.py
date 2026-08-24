"""CONTENT_STORE_MODE：YAML / DB overlay 切换单测。"""

from __future__ import annotations

import pytest

from app.config_source.overlay_store import OverlayStore
from app.constants.content_store import ContentStoreMode
from app.game.content_store import ContentStore
from app.services.realm_config import clear_game_config_cache


@pytest.fixture(autouse=True)
def _clean_overlays() -> None:
    OverlayStore.clear()
    clear_game_config_cache()
    yield
    OverlayStore.clear()
    clear_game_config_cache()


def test_yaml_authority_ignores_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONTENT_STORE_MODE=yaml_authority 时不吃 DB overlay。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "content_store_mode", ContentStoreMode.YAML_AUTHORITY)
    OverlayStore.set("realms", {"major_realms": {"__test_only__": {}}}, version=9)

    raw = ContentStore.load("realms")
    majors = raw.get("major_realms") or {}
    assert "__test_only__" not in majors
    assert ContentStore.mode() == ContentStoreMode.YAML_AUTHORITY


def test_yaml_base_db_overlay_merges(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认模式合并已发布 overlay。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "content_store_mode",
        ContentStoreMode.YAML_BASE_DB_OVERLAY,
    )
    OverlayStore.set(
        "pets",
        {"species": {"__overlay_probe__": {"label_zh": "探测"}}},
        version=1,
    )
    raw = ContentStore.load("pets")
    species = raw.get("species") or {}
    assert "__overlay_probe__" in species
    assert species["__overlay_probe__"]["label_zh"] == "探测"


def test_db_authority_uses_published_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """db_authority：有发布层则合并进结果；无发布则 YAML 种子。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "content_store_mode", ContentStoreMode.DB_AUTHORITY)
    OverlayStore.set(
        "pets",
        {"species": {"__db_probe__": {"label_zh": "库权威"}}},
        version=2,
    )
    raw = ContentStore.load("pets")
    assert "__db_probe__" in (raw.get("species") or {})


def test_realm_config_respects_yaml_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_game_config 经 _load_yaml → ContentStore，yaml_authority 忽略 overlay。"""
    from app.core.config import get_settings
    from app.services.realm_config import get_game_config

    settings = get_settings()
    monkeypatch.setattr(settings, "content_store_mode", ContentStoreMode.YAML_AUTHORITY)
    OverlayStore.set(
        "items",
        {"items": {"__should_not_appear__": {"name": "x", "item_type": "material"}}},
        version=1,
    )
    clear_game_config_cache()
    cfg = get_game_config()
    assert "__should_not_appear__" not in cfg.inventory.items


def test_invalid_mode_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """非法 CONTENT_STORE_MODE 回退 overlay 合并。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "content_store_mode", "not_a_real_mode")
    assert ContentStore.mode() == ContentStoreMode.YAML_BASE_DB_OVERLAY
