"""化身境界双封顶：相对本体 + 禁道主/轮回境。"""

from __future__ import annotations

from typing import Any

from app.constants.avatar import (
    AVATAR_DEFAULT_LEAD_MAJORS,
    AVATAR_DEFAULT_MAX_MAJOR_REALM,
    AVATAR_FORBIDDEN_IDENTITY_REALMS,
    ERR_AVATAR_REALM_CAP,
)
from app.domain.avatar_rules import major_realm_order


def is_forbidden_identity_realm(major_id: str) -> bool:
    """道主境 / 轮回境不是常规修为台阶，化身永远不可进入。"""
    return str(major_id or "").strip() in AVATAR_FORBIDDEN_IDENTITY_REALMS


def avatar_max_major_id(avatar_cfg: Any) -> str:
    """读取配置硬顶；缺省为当前表末境 true_immortal。"""
    raw = str(getattr(avatar_cfg, "max_major_realm", "") or "").strip()
    return raw or AVATAR_DEFAULT_MAX_MAJOR_REALM


def avatar_lead_majors(avatar_cfg: Any) -> int:
    """化身可比本体高几个大境界（默认 0）。"""
    try:
        return max(0, int(getattr(avatar_cfg, "avatar_lead_majors", AVATAR_DEFAULT_LEAD_MAJORS) or 0))
    except (TypeError, ValueError):
        return AVATAR_DEFAULT_LEAD_MAJORS


def can_avatar_hold_major(
    *,
    avatar_major: str,
    host_major: str,
    avatar_cfg: Any,
    realms: dict[str, Any],
) -> tuple[bool, int | None, str]:
    """
    化身当前（或目标）大境界是否合法。

    Returns:
        (ok, err_code, message)
    """
    target = str(avatar_major or "").strip()
    if is_forbidden_identity_realm(target):
        return False, ERR_AVATAR_REALM_CAP, "化身不可进入道主境或轮回境"
    order = major_realm_order(realms)
    cap = avatar_max_major_id(avatar_cfg)
    if target not in order:
        return False, ERR_AVATAR_REALM_CAP, "化身境界不在常规修为链上"
    if cap in order and order.index(target) > order.index(cap):
        return False, ERR_AVATAR_REALM_CAP, "化身已达常规修为硬顶"
    host = str(host_major or "").strip()
    if host not in order or target not in order:
        return True, None, ""
    lead = avatar_lead_majors(avatar_cfg)
    if order.index(target) > order.index(host) + lead:
        return False, ERR_AVATAR_REALM_CAP, "化身大境界不可高于本体"
    return True, None, ""


def can_avatar_advance_to(
    *,
    next_major: str,
    next_is_major_cross: bool,
    host_major: str,
    avatar_cfg: Any,
    realms: dict[str, Any],
) -> tuple[bool, int | None, str]:
    """
    化身是否允许进到下一档（小境超前允许；跨境走双封顶；永不渡劫由调用方保证）。
    """
    if not next_is_major_cross:
        return True, None, ""
    return can_avatar_hold_major(
        avatar_major=next_major,
        host_major=host_major,
        avatar_cfg=avatar_cfg,
        realms=realms,
    )
