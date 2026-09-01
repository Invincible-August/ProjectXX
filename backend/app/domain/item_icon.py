"""Item / content icon keys (§0.0.4).

Catalog may omit ``icon``; callers always get a stable key so the UI can
try asset lookup and fall back to the Chinese name when the file is missing.
"""

from __future__ import annotations


def resolve_item_icon(explicit: str | None, def_id: str) -> str:
    """
    Resolve a player-facing icon / ui key for an item or equippable content.

    Args:
        explicit: Optional YAML ``icon`` / ``ui_key``.
        def_id: Catalog id used as default key.

    Returns:
        Non-empty icon key (never empty string).
    """
    raw = str(explicit or "").strip()
    if raw:
        return raw
    return str(def_id or "").strip() or "unknown"
