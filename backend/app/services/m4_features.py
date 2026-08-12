"""
M4 功能开关守卫：化身 / 工坊 / 灵宠。

统一抛出 ``40043``，避免各 Service 复制门禁逻辑。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.schemas.common import AppError


def require_avatar_enabled() -> None:
    """化身系统未开放时抛出 ``40043``。"""
    if not get_settings().avatar_enabled:
        raise AppError(code=40043, message="化身系统未开放", http_status=403)


def require_craft_enabled() -> None:
    """工坊未开放时抛出 ``40043``。"""
    if not get_settings().craft_enabled:
        raise AppError(code=40043, message="工坊未开放", http_status=403)


def require_pets_enabled() -> None:
    """灵宠系统未开放时抛出 ``40043``。"""
    if not get_settings().pets_enabled:
        raise AppError(code=40043, message="灵宠系统未开放", http_status=403)
