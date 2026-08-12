"""环境挂机预览纯函数与配置解析测试（M5 catalog / tag_modifiers）。"""

from __future__ import annotations

import pytest

from app.domain.env_preview import (
    build_idle_env_preview,
    build_tag_breakdown_items,
    collect_tag_mult,
    resolve_idle_cultivation_mult_with_tags,
)
from app.services.calendar_service import clear_calendar_overrides, set_gm_force_shichen
from app.services.env_preview_service import build_idle_env_bundle
from app.services.realm_config import clear_game_config_cache, get_game_config
from app.services.weather_service import clear_weather_state, set_gm_force_weather


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable calendar/weather and reset GM overrides around each test."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "calendar_enabled", True)
    monkeypatch.setattr(settings, "weather_enabled", True)
    clear_game_config_cache()
    clear_calendar_overrides()
    clear_weather_state()
    yield
    clear_calendar_overrides()
    clear_weather_state()
    clear_game_config_cache()


def test_config_loads_catalog_and_tag_modifiers() -> None:
    """calendar/weather/techniques YAML expose catalog, tag_modifiers, env_tags."""
    bundle = get_game_config()
    assert "dawn" in bundle.calendar.catalog
    assert bundle.calendar.catalog["dawn"].get("summary")
    assert "idle_cultivation" in bundle.calendar.tag_modifiers
    assert "thunderstorm" in bundle.weather.catalog
    assert bundle.weather.catalog["thunderstorm"].get("idle_note")
    assert "idle_cultivation" in bundle.weather.tag_modifiers
    thunder = bundle.techniques.get("thunder_breath_art")
    assert thunder is not None
    assert "thunder_art" in thunder.env_tags


def test_clear_dawn_effective_above_base() -> None:
    """Clear weather + dawn → effective per tick > base (roughly)."""
    set_gm_force_shichen("dawn")
    set_gm_force_weather("clear")
    bundle = build_idle_env_bundle(tags=())
    spirit = bundle["spirit"]
    assert spirit["base_per_tick"] > 0
    # dawn 1.05 × clear 1.05 = 1.1025 → effective > base
    assert spirit["effective_per_tick"] > spirit["base_per_tick"]
    assert spirit["total_mult"] > 1.0
    assert spirit["shichen"]["id"] == "dawn"
    assert spirit["weather"]["id"] == "clear"
    assert spirit["shichen"].get("summary")
    assert spirit["weather"].get("summary")
    assert spirit["shichen"].get("idle_note")
    assert spirit["weather"].get("idle_note")


def test_thunderstorm_tag_boosts_over_no_tag() -> None:
    """Thunderstorm + thunder_root / thunder_art → higher mult than without tag."""
    set_gm_force_shichen("noon")
    set_gm_force_weather("thunderstorm")

    without = build_idle_env_bundle(tags=())
    with_root = build_idle_env_bundle(tags=["thunder_root"])
    with_art = build_idle_env_bundle(tags=["thunder_art"])

    base_eff = without["spirit"]["effective_per_tick"]
    assert with_root["spirit"]["effective_per_tick"] > base_eff
    assert with_art["spirit"]["effective_per_tick"] > base_eff
    assert with_root["spirit"]["total_mult"] > without["spirit"]["total_mult"]

    # domain helper: thunder_root 1.15 under thunderstorm
    mult_plain = resolve_idle_cultivation_mult_with_tags(
        shichen_id="noon",
        weather_id="thunderstorm",
        shichen_table={"noon": 1.0},
        weather_table={"thunderstorm": 0.95},
        tags=(),
    )
    mult_root = resolve_idle_cultivation_mult_with_tags(
        shichen_id="noon",
        weather_id="thunderstorm",
        shichen_table={"noon": 1.0},
        weather_table={"thunderstorm": 0.95},
        tags=["thunder_root"],
        weather_tag_table={"thunderstorm": {"thunder_root": 1.15}},
    )
    assert mult_root > mult_plain


def test_catalog_fields_present_in_preview() -> None:
    """Preview embeds catalog note fields for current shichen/weather."""
    set_gm_force_shichen("night")
    set_gm_force_weather("rain")
    spirit = build_idle_env_bundle(tags=[])["spirit"]
    for key in ("summary", "idle_note", "spawn_bias_note", "craft_notes", "breakthrough_note"):
        assert key in spirit["shichen"]
    for key in ("summary", "idle_note", "spawn_bias_note", "craft_notes", "tribulation_note"):
        assert key in spirit["weather"]
    assert isinstance(spirit["shichen"]["craft_notes"], dict)
    assert isinstance(spirit["weather"]["craft_notes"], dict)
    assert spirit["shichen"]["label"]
    assert spirit["weather"]["label"]


def test_collect_tag_mult_and_breakdown() -> None:
    """collect_tag_mult / build_tag_breakdown_items wire sources correctly."""
    table = {"thunderstorm": {"thunder_root": 1.15, "thunder_art": 1.1}}
    pairs = collect_tag_mult(["thunder_root", "water_root"], table, "thunderstorm")
    assert pairs == [("thunder_root", 1.15)]

    items = build_tag_breakdown_items(
        tags=["thunder_art"],
        shichen_id="noon",
        weather_id="thunderstorm",
        shichen_tag_table=None,
        weather_tag_table=table,
    )
    assert len(items) == 1
    assert items[0].source == "tag_weather"
    assert items[0].id == "thunder_art"

    preview = build_idle_env_preview(
        base_per_tick=10,
        shichen_id="noon",
        weather_id="thunderstorm",
        shichen_mult=1.0,
        weather_mult=0.95,
        tag_mults_breakdown=items,
        clamp_min=0.5,
        clamp_max=1.5,
        shichen_catalog_entry={"summary": "s", "idle_note": "i"},
        weather_catalog_entry={"summary": "w", "tribulation_note": "t"},
        shichen_label="正午",
        weather_label="雷暴",
    )
    sources = {row["source"] for row in preview["breakdown"]}
    assert "shichen" in sources
    assert "weather" in sources
    assert "tag_weather" in sources
    assert preview["effective_per_tick"] == int(10 * 0.95 * 1.1)
