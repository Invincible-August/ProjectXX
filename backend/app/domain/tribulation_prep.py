"""
渡劫准备格校验纯函数（M5 §6.5）。

M5 允许空准备格提交以便冒烟；非法超额 / 未知类型仍拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

# 允许放入准备格的占位类型
ALLOWED_PREP_KINDS: frozenset[str] = frozenset(
    {
        "pill",
        "guard_artifact",
        "artifact",
        "veil",
        "formation_ref",
        "empty",
    },
)


@dataclass(frozen=True)
class PrepSlot:
    """Single prep slot entry."""

    kind: str
    item_id: str | None = None
    mitigation: float = 0.0
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        payload: dict[str, Any] = {"kind": self.kind}
        if self.item_id is not None:
            payload["item_id"] = self.item_id
        if self.mitigation:
            payload["mitigation"] = self.mitigation
        if self.meta:
            payload["meta"] = self.meta
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PrepSlot":
        """Parse one slot; missing → empty."""
        if not raw:
            return cls(kind="empty")
        return cls(
            kind=str(raw.get("kind", "empty")),
            item_id=str(raw["item_id"]) if raw.get("item_id") else None,
            mitigation=float(raw.get("mitigation", 0.0)),
            meta=dict(raw["meta"]) if raw.get("meta") else None,
        )


def normalize_prep_slots(
    slots: Sequence[dict[str, Any] | None] | None,
    *,
    slot_count: int,
) -> list[PrepSlot]:
    """
    Normalize client prep payload to fixed-length PrepSlot list.

    Args:
        slots: Client-provided slots (may be shorter).
        slot_count: Required slot count from config.

    Returns:
        list[PrepSlot]: Length ``slot_count``, padded with empty.
    """
    raw_list = list(slots or [])
    normalized: list[PrepSlot] = []
    for index in range(slot_count):
        if index < len(raw_list):
            item = raw_list[index]
            normalized.append(
                PrepSlot.from_dict(item if isinstance(item, dict) else None),
            )
        else:
            normalized.append(PrepSlot(kind="empty"))
    return normalized


def validate_prep_slots(
    slots: Sequence[PrepSlot],
    *,
    max_slots: int,
    max_veil: int = 1,
) -> None:
    """
    Validate prep slots; raise ``ValueError`` with message for AppError mapping.

    Args:
        slots: Normalized slots.
        max_slots: Configured maximum.
        max_veil: Max veil items allowed (default 1).

    Raises:
        ValueError: Illegal kind, over-capacity, or too many veil items.
    """
    if len(slots) > max_slots:
        raise ValueError(f"准备格超过上限（{max_slots}）")
    veil_count = 0
    for slot in slots:
        if slot.kind not in ALLOWED_PREP_KINDS:
            raise ValueError(f"准备格类型非法：{slot.kind}")
        if slot.kind == "veil":
            veil_count += 1
    if veil_count > max_veil:
        raise ValueError("遮天道具至多一件")


def next_consumable_mitigation(
    slots: Sequence[PrepSlot],
    next_index: int,
) -> tuple[float, int]:
    """
    Peek next non-empty prep mitigation and advance index.

    Args:
        slots: Ordered prep slots.
        next_index: Current consume cursor.

    Returns:
        tuple: ``(mitigation_fraction, new_index)``. Empty slots skipped.
    """
    index = next_index
    while index < len(slots):
        slot = slots[index]
        index += 1
        if slot.kind in ("empty", "formation_ref"):
            continue
        # 普通法宝 mitigation 差；护劫类用配置/字段
        if slot.kind == "artifact":
            return max(0.0, float(slot.mitigation) * 0.2), index
        if slot.kind == "veil":
            # 遮天不在受击时消耗减伤，由 veil-check 处理
            continue
        return max(0.0, float(slot.mitigation or 0.5)), index
    return 0.0, index


def prep_exhausted(slots: Sequence[PrepSlot], next_index: int) -> bool:
    """
    Return whether remaining slots have no further consumable mitigation.

    Args:
        slots: Prep slots.
        next_index: Consume cursor.

    Returns:
        bool: True when no more pill/artifact/guard_artifact remain.
    """
    for slot in slots[next_index:]:
        if slot.kind in ("pill", "guard_artifact", "artifact"):
            return False
    return True
