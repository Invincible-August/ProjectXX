"""
Talisman battle helpers (M8 R4): inject item_trigger without touching the engine.
"""

from __future__ import annotations

from typing import Any

from app.constants.battle import EVENT_TYPE_ITEM_TRIGGER


def inject_item_triggers(
    events: list[dict[str, Any]],
    talismans: list[dict[str, Any]],
    *,
    enabled: bool,
    attacker_uids: set[str],
) -> list[dict[str, Any]]:
    """
    Insert Chinese item_trigger rows after the first hit on an attacker unit.

    If nobody on the attacker side is hit, insert before battle_end so a
    preloaded talisman still appears in the report (R4 minimum).
    """
    if not enabled or not talismans:
        return list(events)
    insert_at: int | None = None
    for index, event in enumerate(events):
        if event.get("type") == "damage" and str(event.get("target") or "") in attacker_uids:
            insert_at = index + 1
            break
    if insert_at is None:
        for index, event in enumerate(events):
            if event.get("type") == "battle_end":
                insert_at = index
                break
        if insert_at is None:
            insert_at = len(events)
    out = list(events)
    for talisman in talismans:
        label = str(talisman.get("label_zh") or "符箓")
        out.insert(
            insert_at,
            {
                "type": EVENT_TYPE_ITEM_TRIGGER,
                "item_type": "talisman",
                "label_zh": label,
                "source_label_zh": str(talisman.get("source_label_zh") or "自研"),
                "effect_id": talisman.get("effect_id"),
                "trigger": str(talisman.get("trigger") or "first_hit"),
            },
        )
        insert_at += 1
    return out
