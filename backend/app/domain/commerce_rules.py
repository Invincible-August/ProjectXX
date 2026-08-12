"""
商业化纯规则（M7 L8）：会员档 / 禁售本命道 / 有效档位。

无 IO。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


MEMBERSHIP_TIERS = frozenset({"free", "tier1", "tier2"})
NON_TRANSFERABLE = frozenset(
    {
        "tiandao_point",
        "sect_contrib",
        "alliance_contrib",
        "honor",
        "reincarnation_point",
    },
)


def is_forbidden_shop_kind(kind: str, forbidden: list[str] | tuple[str, ...]) -> bool:
    """是否命中禁售类型（指定本命道等）。"""
    return str(kind or "").strip().lower() in {str(x).lower() for x in forbidden}


def effective_membership_tier(
    *,
    tier: str | None,
    expires_at: datetime | None,
    now: datetime,
) -> str:
    """
    计算当前有效会员档；过期视为 free。

    Args:
        tier: 存档档位。
        expires_at: 过期时刻；free/无期限可为 None。
        now: 当前 UTC。

    Returns:
        free|tier1|tier2。
    """
    raw = str(tier or "free").strip().lower()
    if raw not in MEMBERSHIP_TIERS:
        return "free"
    if raw == "free":
        return "free"
    if expires_at is not None and expires_at <= now:
        return "free"
    return raw


def apply_membership_expiry_inplace(character: Any, *, now: datetime | None = None) -> str:
    """
    同步惰性过期：改写 ORM 字段（不 flush）。

    Args:
        character: 角色 ORM（须有 membership_tier / membership_expires_at）。
        now: 当前 UTC。

    Returns:
        有效档位。
    """
    from app.core.time_utils import ensure_aware_utc, now_utc

    current = now or now_utc()
    expires = (
        ensure_aware_utc(character.membership_expires_at)
        if getattr(character, "membership_expires_at", None) is not None
        else None
    )
    effective = effective_membership_tier(
        tier=getattr(character, "membership_tier", None),
        expires_at=expires,
        now=current,
    )
    stored = str(getattr(character, "membership_tier", None) or "free")
    if effective == "free" and stored in ("tier1", "tier2"):
        character.membership_tier = "free"
        character.membership_expires_at = None
        if hasattr(character, "updated_at"):
            character.updated_at = current
    return effective


def membership_public(
    *,
    tier: str,
    expires_at: datetime | None,
    idle_cap_hours: float,
    label_zh: str,
) -> dict[str, Any]:
    """会员摘要 dict（进 CharacterPublic / commerce me）。"""
    return {
        "tier": tier,
        "label_zh": label_zh,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "idle_cap_hours": float(idle_cap_hours),
    }
