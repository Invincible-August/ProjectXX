"""
挂机环境预览纯函数（M5）：时辰/天气基础乘区 + 标签乘区 + catalog 文案。

结算侧应使用与本模块相同的乘区公式，保证 IdlePanel 展示与 settle 一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.domain.env_modifiers import combine_env_multipliers, lookup_modifier


@dataclass(frozen=True)
class EnvMultBreakdownItem:
    """Single multiplier contribution for idle env preview UI."""

    source: str  # shichen | weather | tag_shichen | tag_weather
    id: str
    label: str
    mult: float


def collect_tag_mult(
    tags: Sequence[str],
    table_by_dim: Mapping[str, Mapping[str, float]] | None,
    dim_id: str,
) -> list[tuple[str, float]]:
    """
    Collect tag multipliers that apply under a shichen/weather dimension id.

    Args:
        tags: Character spirit-root + technique env tags.
        table_by_dim: Nested map ``dim_id → tag_id → mult``
            (e.g. ``tag_modifiers.idle_cultivation.by_shichen``).
        dim_id: Current shichen_id or weather_id.

    Returns:
        list[tuple[str, float]]: ``(tag_id, mult)`` for each matching tag.
    """
    if not tags or not table_by_dim:
        return []
    dim_table = table_by_dim.get(dim_id)
    if not isinstance(dim_table, Mapping):
        return []
    result: list[tuple[str, float]] = []
    seen: set[str] = set()
    for tag in tags:
        tag_id = str(tag)
        if not tag_id or tag_id in seen:
            continue
        if tag_id not in dim_table:
            continue
        seen.add(tag_id)
        result.append((tag_id, float(dim_table[tag_id])))
    return result


def _catalog_public(
    entry: Mapping[str, Any] | None,
    *,
    entry_id: str,
    label: str,
    note_keys: Sequence[str],
) -> dict[str, Any]:
    """
    Build a catalog snippet for API / CharacterPublic.

    Args:
        entry: Raw catalog dict for this id (may be empty).
        entry_id: Shichen or weather id.
        label: Display label.
        note_keys: Catalog note field names to copy.

    Returns:
        dict: id/label plus requested note fields (missing → None / {}).
    """
    src = dict(entry or {})
    payload: dict[str, Any] = {
        "id": entry_id,
        "label": label,
    }
    for key in note_keys:
        if key == "craft_notes":
            notes = src.get("craft_notes")
            payload[key] = dict(notes) if isinstance(notes, Mapping) else {}
        else:
            value = src.get(key)
            payload[key] = str(value) if value is not None else None
    return payload


def build_idle_env_preview(
    *,
    base_per_tick: int,
    shichen_id: str,
    weather_id: str,
    shichen_mult: float,
    weather_mult: float,
    tag_mults_breakdown: Sequence[EnvMultBreakdownItem] | Sequence[tuple[str, str, str, float]],
    clamp_min: float,
    clamp_max: float,
    shichen_catalog_entry: Mapping[str, Any] | None,
    weather_catalog_entry: Mapping[str, Any] | None,
    shichen_label: str,
    weather_label: str,
    realm_major: str | None = None,
    realm_label: str | None = None,
    channel_mults_breakdown: Sequence[EnvMultBreakdownItem]
    | Sequence[tuple[str, str, str, float]]
    | None = None,
    channel_mult: float = 1.0,
) -> dict[str, Any]:
    """
    Build idle effective-rate preview with multiplier breakdown and catalogs.

    Final rate::

        env_mult = clamp(tag_product * shichen * weather)
        effective = floor(base * channel_mult * env_mult)

    Args:
        base_per_tick: Direction base gain per tick (realm table or fallback).
        shichen_id: Current shichen id.
        weather_id: Current weather id (settlement weather, not display overlay).
        shichen_mult: Calendar idle_cultivation coefficient.
        weather_mult: Weather idle_cultivation coefficient.
        tag_mults_breakdown: Tag contributions as ``EnvMultBreakdownItem`` or
            ``(source, id, label, mult)`` tuples.
        clamp_min: Lower clamp for combined env multiplier.
        clamp_max: Upper clamp for combined env multiplier.
        shichen_catalog_entry: calendar.yaml catalog entry.
        weather_catalog_entry: weather.yaml catalog entry.
        shichen_label: Display name for shichen.
        weather_label: Display name for weather.
        realm_major: Optional major_realm id for ``realm_base`` breakdown row.
        realm_label: Optional display label for realm_base row.
        channel_mults_breakdown: Internal/external channel rows (constitution…).
        channel_mult: Product of enabled bonus channels (already clamped).

    Returns:
        dict: base/effective rates, total_mult, breakdown, shichen/weather snippets.
    """
    breakdown_items: list[EnvMultBreakdownItem] = []
    for item in tag_mults_breakdown:
        if isinstance(item, EnvMultBreakdownItem):
            breakdown_items.append(item)
        else:
            source, item_id, label, mult = item
            breakdown_items.append(
                EnvMultBreakdownItem(
                    source=str(source),
                    id=str(item_id),
                    label=str(label),
                    mult=float(mult),
                ),
            )

    channel_items: list[EnvMultBreakdownItem] = []
    for item in channel_mults_breakdown or ():
        if isinstance(item, EnvMultBreakdownItem):
            channel_items.append(item)
        else:
            source, item_id, label, mult = item
            channel_items.append(
                EnvMultBreakdownItem(
                    source=str(source),
                    id=str(item_id),
                    label=str(label),
                    mult=float(mult),
                ),
            )

    # 标签乘区先乘入 base 侧，再与时辰/天气一起 clamp（与 settle 同式）
    tag_product = 1.0
    for item in breakdown_items:
        if item.source in ("tag_shichen", "tag_weather"):
            tag_product *= float(item.mult)

    env_mult = combine_env_multipliers(
        base=tag_product,
        shichen_mult=float(shichen_mult),
        weather_mult=float(weather_mult),
        clamp_min=clamp_min,
        clamp_max=clamp_max,
    )
    channel = float(channel_mult) if channel_mult else 1.0
    # total_mult 相对 base：通道 × 环境（面板展示）
    total_mult = float(channel) * float(env_mult)
    base = int(base_per_tick)
    effective = int(base * total_mult)

    full_breakdown: list[dict[str, Any]] = []
    if realm_major:
        full_breakdown.append(
            {
                "source": "realm_base",
                "id": str(realm_major),
                "label": str(realm_label or realm_major),
                "mult": 1.0,
            },
        )
    full_breakdown.extend(
        [
            {
                "source": "shichen",
                "id": shichen_id,
                "label": shichen_label,
                "mult": float(shichen_mult),
            },
            {
                "source": "weather",
                "id": weather_id,
                "label": weather_label,
                "mult": float(weather_mult),
            },
        ],
    )
    for item in breakdown_items:
        if item.source in ("tag_shichen", "tag_weather"):
            full_breakdown.append(
                {
                    "source": item.source,
                    "id": item.id,
                    "label": item.label,
                    "mult": float(item.mult),
                },
            )
    for item in channel_items:
        full_breakdown.append(
            {
                "source": item.source,
                "id": item.id,
                "label": item.label,
                "mult": float(item.mult),
            },
        )

    return {
        "base_per_tick": base,
        "effective_per_tick": effective,
        "total_mult": float(total_mult),
        "breakdown": full_breakdown,
        "shichen": _catalog_public(
            shichen_catalog_entry,
            entry_id=shichen_id,
            label=shichen_label,
            note_keys=(
                "summary",
                "idle_note",
                "spawn_bias_note",
                "craft_notes",
                "breakthrough_note",
            ),
        ),
        "weather": _catalog_public(
            weather_catalog_entry,
            entry_id=weather_id,
            label=weather_label,
            note_keys=(
                "summary",
                "idle_note",
                "spawn_bias_note",
                "craft_notes",
                "tribulation_note",
            ),
        ),
    }


def build_tag_breakdown_items(
    *,
    tags: Sequence[str],
    shichen_id: str,
    weather_id: str,
    shichen_tag_table: Mapping[str, Mapping[str, float]] | None,
    weather_tag_table: Mapping[str, Mapping[str, float]] | None,
) -> list[EnvMultBreakdownItem]:
    """
    Build tag breakdown items for current shichen + weather.

    Args:
        tags: Combined spirit-root / technique tags.
        shichen_id: Current shichen.
        weather_id: Current weather.
        shichen_tag_table: ``by_shichen`` table under idle_cultivation.
        weather_tag_table: ``by_weather`` table under idle_cultivation.

    Returns:
        list[EnvMultBreakdownItem]: Tag rows for preview / settle product.
    """
    items: list[EnvMultBreakdownItem] = []
    for tag_id, mult in collect_tag_mult(tags, shichen_tag_table, shichen_id):
        items.append(
            EnvMultBreakdownItem(
                source="tag_shichen",
                id=tag_id,
                label=tag_id,
                mult=mult,
            ),
        )
    for tag_id, mult in collect_tag_mult(tags, weather_tag_table, weather_id):
        items.append(
            EnvMultBreakdownItem(
                source="tag_weather",
                id=tag_id,
                label=tag_id,
                mult=mult,
            ),
        )
    return items


def resolve_idle_cultivation_mult_with_tags(
    *,
    shichen_id: str,
    weather_id: str,
    shichen_table: Mapping[str, float] | None,
    weather_table: Mapping[str, float] | None,
    tags: Sequence[str] = (),
    shichen_tag_table: Mapping[str, Mapping[str, float]] | None = None,
    weather_tag_table: Mapping[str, Mapping[str, float]] | None = None,
    clamp_min: float = 0.5,
    clamp_max: float = 1.5,
) -> float:
    """
    Resolve idle cultivation multiplier including tag modifiers.

    Args:
        shichen_id: Current shichen.
        weather_id: Current weather.
        shichen_table: Calendar idle_cultivation base table.
        weather_table: Weather idle_cultivation base table.
        tags: Character env tags.
        shichen_tag_table: Tag×shichen table.
        weather_tag_table: Tag×weather table.
        clamp_min: Lower clamp.
        clamp_max: Upper clamp.

    Returns:
        float: Clamped combined multiplier (same formula as preview).
    """
    shichen_mult = lookup_modifier(shichen_table, shichen_id) if shichen_table is not None else 1.0
    weather_mult = lookup_modifier(weather_table, weather_id) if weather_table is not None else 1.0
    tag_items = build_tag_breakdown_items(
        tags=tags,
        shichen_id=shichen_id,
        weather_id=weather_id,
        shichen_tag_table=shichen_tag_table,
        weather_tag_table=weather_tag_table,
    )
    tag_product = 1.0
    for item in tag_items:
        tag_product *= float(item.mult)
    return combine_env_multipliers(
        base=tag_product,
        shichen_mult=shichen_mult,
        weather_mult=weather_mult,
        clamp_min=clamp_min,
        clamp_max=clamp_max,
    )


def parse_spirit_root_tags_json(raw: str | None) -> list[str]:
    """
    Parse ``spirit_root_tags_json`` into a list of tag ids.

    Args:
        raw: JSON list string or None.

    Returns:
        list[str]: Tag ids; empty on null/invalid.
    """
    if not raw:
        return []
    import json

    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if str(x).strip()]
