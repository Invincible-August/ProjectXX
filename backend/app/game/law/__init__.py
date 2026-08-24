"""Law 域包：大道/道主相关门面。"""

from __future__ import annotations

from app.game.law.privilege import (
    has_privilege,
    normalize_privileges_payload,
    privilege_grant_sources,
)

__all__ = [
    "normalize_privileges_payload",
    "privilege_grant_sources",
    "has_privilege",
]
