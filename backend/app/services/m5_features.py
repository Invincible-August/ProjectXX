"""
M5 功能开关守卫：历法 / 天气 / 渡劫。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.schemas.common import AppError


def require_calendar_enabled() -> None:
    """历法关闭时抛出 ``40043``（与 M4 门禁码对齐便于前端统一处理）。"""
    if not get_settings().calendar_enabled:
        raise AppError(code=40043, message="六时历法未开放", http_status=403)


def require_weather_enabled() -> None:
    """天气系统未开放时抛出 ``40043``。"""
    if not get_settings().weather_enabled:
        raise AppError(code=40043, message="天气系统未开放", http_status=403)


def require_tribulation_enabled() -> None:
    """雷劫未开放时抛出 ``40043``。"""
    if not get_settings().tribulation_enabled:
        raise AppError(code=40043, message="渡劫系统未开放", http_status=403)


def is_tribulation_enabled() -> bool:
    """Return whether tribulation feature flag is on."""
    return bool(get_settings().tribulation_enabled)
