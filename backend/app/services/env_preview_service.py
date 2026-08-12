"""
挂机环境预览应用服务：聚合历法/天气快照、角色标签与 idle 基础速率。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import Character
from app.db.models.technique import CharacterTechnique
from app.domain.env_modifiers import lookup_modifier
from app.domain.env_preview import (
    EnvMultBreakdownItem,
    build_idle_env_preview,
    build_tag_breakdown_items,
    parse_spirit_root_tags_json,
)
from app.services.calendar_service import CalendarService
from app.services.realm_config import clamp_idle_channel_mult, get_game_config
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)

# bonus_channels id → idle_env.breakdown.source
_CHANNEL_SOURCE_MAP: dict[str, str] = {
    "constitution_idle": "constitution",
    "equipment_idle": "equipment",
    "buff_pill": "buff_pill",
    "buff_talisman": "buff_talisman",
    "spirit_eye": "spirit_eye",
    "cave": "cave",
}

_CHANNEL_LABELS: dict[str, str] = {
    "constitution": "体质",
    "equipment": "装备",
    "buff_pill": "丹药buff",
    "buff_talisman": "符箓buff",
    "spirit_eye": "灵眼",
    "cave": "洞府",
}


def get_idle_tag_tables() -> tuple[
    dict[str, dict[str, float]] | None,
    dict[str, dict[str, float]] | None,
]:
    """
    Extract idle_cultivation tag tables from calendar/weather config.

    Returns:
        tuple: (by_shichen table, by_weather table); None when feature off.
    """
    settings = get_settings()
    bundle = get_game_config()
    shichen_tag: dict[str, dict[str, float]] | None = None
    weather_tag: dict[str, dict[str, float]] | None = None
    if settings.calendar_enabled:
        cal_idle = (bundle.calendar.tag_modifiers.get("idle_cultivation") or {})
        raw = cal_idle.get("by_shichen") or {}
        if isinstance(raw, dict):
            shichen_tag = {
                str(dim): {str(t): float(m) for t, m in (table or {}).items()}
                for dim, table in raw.items()
                if isinstance(table, dict)
            }
    if settings.weather_enabled:
        wx_idle = (bundle.weather.tag_modifiers.get("idle_cultivation") or {})
        raw = wx_idle.get("by_weather") or {}
        if isinstance(raw, dict):
            weather_tag = {
                str(dim): {str(t): float(m) for t, m in (table or {}).items()}
                for dim, table in raw.items()
                if isinstance(table, dict)
            }
    return shichen_tag, weather_tag


def _env_ids_and_mults(
    *,
    now: datetime | None = None,
) -> tuple[str, str, str, str, float, float, float, float]:
    """
    Resolve current shichen/weather ids, labels, base mults, and clamp bounds.

    Returns:
        tuple: shichen_id, weather_id, shichen_label, weather_label,
        shichen_mult, weather_mult, clamp_min, clamp_max.
    """
    settings = get_settings()
    bundle = get_game_config()
    current = now_utc(now)
    cal = CalendarService().get_snapshot(now=current)
    weather = WeatherService().get_snapshot(now=current)

    shichen_id = str(cal.get("shichen_id") or "noon")
    weather_id = str(weather.get("weather_id") or "clear")
    shichen_label = str(cal.get("label") or bundle.calendar.labels.get(shichen_id, shichen_id))
    weather_label = str(
        weather.get("label") or bundle.weather.labels.get(weather_id, weather_id),
    )

    shichen_table = bundle.calendar.modifiers.get("idle_cultivation") or {}
    weather_table = bundle.weather.modifiers.get("idle_cultivation") or {}
    shichen_mult = (
        lookup_modifier(shichen_table, shichen_id)
        if settings.calendar_enabled
        else 1.0
    )
    weather_mult = (
        lookup_modifier(weather_table, weather_id)
        if settings.weather_enabled
        else 1.0
    )
    clamp_min = min(bundle.calendar.clamp_min, bundle.weather.clamp_min)
    clamp_max = max(bundle.calendar.clamp_max, bundle.weather.clamp_max)
    return (
        shichen_id,
        weather_id,
        shichen_label,
        weather_label,
        shichen_mult,
        weather_mult,
        clamp_min,
        clamp_max,
    )


def technique_env_tags_for_ids(technique_ids: Sequence[str]) -> list[str]:
    """
    Map unlocked technique ids to env_tags from game config.

    Args:
        technique_ids: Character technique ids.

    Returns:
        list[str]: Deduped env tag ids.
    """
    techniques = get_game_config().techniques
    tags: list[str] = []
    seen: set[str] = set()
    for tech_id in technique_ids:
        cfg = techniques.get(str(tech_id))
        if cfg is None:
            continue
        for tag in cfg.env_tags:
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


async def load_character_env_tags(
    session: AsyncSession,
    character: Character,
) -> list[str]:
    """
    Load spirit-root + technique env tags for a character.

    Args:
        session: Async DB session.
        character: Character ORM row.

    Returns:
        list[str]: Deduped tag ids.
    """
    spirit_tags = parse_spirit_root_tags_json(
        getattr(character, "spirit_root_tags_json", None),
    )
    result = await session.execute(
        select(CharacterTechnique.technique_id).where(
            CharacterTechnique.character_id == character.id,
        ),
    )
    technique_ids = [str(row[0]) for row in result.all()]
    tech_tags = technique_env_tags_for_ids(technique_ids)
    merged: list[str] = []
    seen: set[str] = set()
    for tag in [*spirit_tags, *tech_tags]:
        if tag not in seen:
            seen.add(tag)
            merged.append(tag)
    return merged


def build_idle_env_bundle(
    *,
    tags: Sequence[str] = (),
    now: datetime | None = None,
    major_realm: str | None = None,
    channel_mult: float = 1.0,
    channel_breakdown: Sequence[EnvMultBreakdownItem] | None = None,
) -> dict[str, Any]:
    """
    Build idle_env payload for spirit/body/crafting base rates.

    Args:
        tags: Env tags (empty for world-level base-only preview).
        now: Optional frozen UTC time.
        major_realm: Character major for realm base table; None → fallback rates.
        channel_mult: Clamped product of enabled bonus channels.
        channel_breakdown: Channel rows for UI (enabled only).

    Returns:
        dict: ``spirit`` / ``body`` / ``crafting`` previews + ``tags_applied``.
    """
    bundle = get_game_config()
    idle = bundle.idle
    (
        shichen_id,
        weather_id,
        shichen_label,
        weather_label,
        shichen_mult,
        weather_mult,
        clamp_min,
        clamp_max,
    ) = _env_ids_and_mults(now=now)
    shichen_tag_table, weather_tag_table = get_idle_tag_tables()
    tag_items = build_tag_breakdown_items(
        tags=tags,
        shichen_id=shichen_id,
        weather_id=weather_id,
        shichen_tag_table=shichen_tag_table,
        weather_tag_table=weather_tag_table,
    )
    shichen_catalog = bundle.calendar.catalog.get(shichen_id) or {}
    weather_catalog = bundle.weather.catalog.get(weather_id) or {}

    major = str(major_realm) if major_realm else None
    realm_label = None
    if major:
        major_cfg = bundle.realms.get(major)
        realm_label = major_cfg.name if major_cfg is not None else major

    def _preview(direction: str) -> dict[str, Any]:
        rates = idle.direction_rates(direction)
        if rates is None:
            base = 0
        elif major:
            base = idle.gain_per_tick_for_major(direction, major)
        else:
            base = rates.gain_per_tick
        return build_idle_env_preview(
            base_per_tick=base,
            shichen_id=shichen_id,
            weather_id=weather_id,
            shichen_mult=shichen_mult,
            weather_mult=weather_mult,
            tag_mults_breakdown=tag_items,
            clamp_min=clamp_min,
            clamp_max=clamp_max,
            shichen_catalog_entry=shichen_catalog,
            weather_catalog_entry=weather_catalog,
            shichen_label=shichen_label,
            weather_label=weather_label,
            realm_major=major,
            realm_label=realm_label,
            channel_mults_breakdown=channel_breakdown,
            channel_mult=channel_mult,
        )

    return {
        "spirit": _preview("spirit"),
        "body": _preview("body"),
        "crafting": _preview("crafting"),
        # 采矿：基础取 sects.mine_yield.personal_stones_per_tick，套用同套时辰/天气/通道
        "sect_mining": build_idle_env_preview(
            base_per_tick=int(
                (bundle.sects.mine_yield or {}).get("personal_stones_per_tick") or 5,
            ),
            shichen_id=shichen_id,
            weather_id=weather_id,
            shichen_mult=shichen_mult,
            weather_mult=weather_mult,
            tag_mults_breakdown=tag_items,
            clamp_min=clamp_min,
            clamp_max=clamp_max,
            shichen_catalog_entry=shichen_catalog,
            weather_catalog_entry=weather_catalog,
            shichen_label=shichen_label,
            weather_label=weather_label,
            realm_major=major,
            realm_label=realm_label,
            channel_mults_breakdown=channel_breakdown,
            channel_mult=channel_mult,
        ),
        "tags_applied": list(tags),
    }


def build_world_idle_preview(*, now: datetime | None = None) -> dict[str, Any]:
    """
    World-level idle preview without character tags (base shichen×weather only).

    Args:
        now: Optional frozen UTC time.

    Returns:
        dict: Same shape as character idle_env but ``tags_applied`` empty.
    """
    return build_idle_env_bundle(tags=(), now=now)


async def resolve_idle_bonus_channels(
    session: AsyncSession,
    character: Character,
) -> tuple[float, list[EnvMultBreakdownItem]]:
    """
    Resolve enabled bonus_channels product + breakdown for a character.

    Constitution hook: product of equipped items' ``effects.idle_mult`` when present;
    otherwise channel ``default_mult``. Disabled channels are omitted (implicit ×1).

    Args:
        session: Async DB session.
        character: Character row.

    Returns:
        tuple: ``(clamped_channel_mult, breakdown_items)``.
    """
    from app.services.constitution_service import ConstitutionService

    idle = get_game_config().idle
    constitution_items = get_game_config().constitution.items
    product = 1.0
    items: list[EnvMultBreakdownItem] = []

    for channel_id, channel in idle.bonus_channels.items():
        if not channel.enabled:
            continue
        source = _CHANNEL_SOURCE_MAP.get(channel_id, channel_id)
        label = _CHANNEL_LABELS.get(source, source)
        mult = float(channel.default_mult)

        if channel_id == "constitution_idle":
            # 已装备体质/词条：乘入各 idle_mult（有则覆盖 default 的「空槽」语义）
            state = await ConstitutionService(session).get_constitution_state(character)
            found_any = False
            equipped_product = 1.0
            for eq in state.get("equipped_summary") or []:
                def_id = str(eq.get("def_id") or "")
                item_def = constitution_items.get(def_id)
                if item_def is None:
                    continue
                raw_mult = item_def.effects.get("idle_mult")
                if raw_mult is None:
                    continue
                found_any = True
                piece = float(raw_mult)
                equipped_product *= piece
                items.append(
                    EnvMultBreakdownItem(
                        source=source,
                        id=def_id,
                        label=item_def.name,
                        mult=piece,
                    ),
                )
            mult = equipped_product if found_any else float(channel.default_mult)
            if not found_any:
                items.append(
                    EnvMultBreakdownItem(
                        source=source,
                        id=channel_id,
                        label=label,
                        mult=mult,
                    ),
                )
        else:
            # 延后通道：enabled 时显性列出 default_mult（无实例系统则恒为此值）
            items.append(
                EnvMultBreakdownItem(
                    source=source,
                    id=channel_id,
                    label=label,
                    mult=mult,
                ),
            )

        product *= mult

    return clamp_idle_channel_mult(product), items


async def build_character_idle_env(
    session: AsyncSession,
    character: Character,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Character-specific idle env preview (spirit-root + technique tags + realm base).

    Args:
        session: Async DB session.
        character: Character row.
        now: Optional frozen UTC time.

    Returns:
        dict: idle_env payload for CharacterPublic.
    """
    tags = await load_character_env_tags(session, character)
    channel_mult, channel_items = await resolve_idle_bonus_channels(session, character)
    logger.debug(
        "idle_env character_id=%s tags=%s channel_mult=%s",
        character.id,
        tags,
        channel_mult,
    )
    return build_idle_env_bundle(
        tags=tags,
        now=now,
        major_realm=str(character.major_realm),
        channel_mult=channel_mult,
        channel_breakdown=channel_items,
    )


class EnvPreviewService:
    """Thin service wrapper for character / world idle env previews."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Request-scoped async session.
        """
        self._session = session

    async def for_character(
        self,
        character: Character,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Build CharacterPublic.idle_env."""
        return await build_character_idle_env(self._session, character, now=now)

    @staticmethod
    def for_world(*, now: datetime | None = None) -> dict[str, Any]:
        """Build /world/env idle_preview (no character tags)."""
        return build_world_idle_preview(now=now)
