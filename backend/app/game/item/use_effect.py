"""Consumable use_effect whitelist and multi-track duration schema (M8 R0)."""

from __future__ import annotations

from typing import Any

from app.constants.inventory import DurationClock, INSTANT_USE_KINDS, UseEffectKind

_CLOCK_AMOUNT_KEYS: dict[str, str] = {
    DurationClock.WALL: "seconds",
    DurationClock.BATTLE: "count",
    DurationClock.ROUND: "count",
}


class UseEffectError(ValueError):
    """Raised when use_effect kind or duration schema is illegal."""


def _as_effect_list(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [dict(x) for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [dict(raw)]
    raise UseEffectError("use_effect 须为对象或列表")


def _parse_tracks(duration: Any) -> list[dict[str, Any]]:
    if duration is None:
        return []
    if isinstance(duration, (int, float, str)):
        raise UseEffectError("禁止裸 duration 整数；须声明 clock")
    if not isinstance(duration, dict):
        raise UseEffectError("duration 须为对象")
    expire = str(duration.get("expire") or "any")
    if expire != "any":
        raise UseEffectError("duration.expire 只承认 any")
    tracks_raw = duration.get("tracks")
    if tracks_raw is None:
        tracks_raw = [duration]
    if not isinstance(tracks_raw, list) or not tracks_raw:
        raise UseEffectError("duration.tracks 不可为空")
    parsed: list[dict[str, Any]] = []
    for track in tracks_raw:
        if not isinstance(track, dict):
            raise UseEffectError("duration.tracks 每项须为对象")
        clock = str(track.get("clock") or "")
        if clock not in {c.value for c in DurationClock}:
            raise UseEffectError(f"未知时钟: {clock}")
        amount_key = _CLOCK_AMOUNT_KEYS[clock]
        if amount_key not in track:
            raise UseEffectError(f"时钟 {clock} 缺少 {amount_key}")
        amount = int(track[amount_key])
        if amount <= 0:
            raise UseEffectError(f"时钟 {clock} 的 {amount_key} 须为正整数")
        parsed.append({"clock": clock, amount_key: amount})
    return parsed


def validate_use_effect(raw: Any) -> list[dict[str, Any]]:
    """
    Validate whitelist kinds and multi-track clocks.

    Returns:
        list[dict]: normalized effects with ``instant`` / ``tracks``.

    Raises:
        UseEffectError: unknown kind or illegal duration.
    """
    allowed = {k.value for k in UseEffectKind}
    out: list[dict[str, Any]] = []
    for effect in _as_effect_list(raw):
        kind = str(effect.get("kind") or "")
        if kind not in allowed:
            raise UseEffectError(f"未知 use_effect.kind: {kind}")
        tracks = _parse_tracks(effect.get("duration"))
        instant = kind in INSTANT_USE_KINDS and not tracks
        if kind == UseEffectKind.ATTR_MOD and not tracks:
            raise UseEffectError("attr_mod 必须带 duration 时钟")
        row = dict(effect)
        row["kind"] = kind
        row["instant"] = instant
        row["tracks"] = tracks
        out.append(row)
    return out
