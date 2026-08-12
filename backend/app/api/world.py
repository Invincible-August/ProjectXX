"""世界环境 HTTP 路由：历法 / 天气 / 聚合（M5）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.db.models import User
from app.schemas.common import success
from app.services.calendar_service import CalendarService
from app.services.env_preview_service import EnvPreviewService
from app.services.realm_config import get_game_config
from app.services.weather_service import WeatherService

router = APIRouter(prefix="/world", tags=["world"])


def _flatten_env(cal: dict[str, Any], wx: dict[str, Any]) -> dict[str, Any]:
    """
    将 calendar + weather 快照压平为前端 ``WorldEnvPublic`` 契约。

    Args:
        cal: CalendarService.get_snapshot()
        wx: WeatherService.get_snapshot()

    Returns:
        dict: 扁平时辰/天气/提示字段。
    """
    # 日历字段：后端用 shichen_id/label/next_at，前端要 shichen/shichen_label/next_shichen_at
    shichen = str(cal.get("shichen") or cal.get("shichen_id") or "noon")
    shichen_label = str(cal.get("shichen_label") or cal.get("label") or shichen)
    next_shichen_at = str(cal.get("next_shichen_at") or cal.get("next_at") or "")

    # 天气：优先展示 display（劫云），结算仍用 weather_id
    weather = str(
        wx.get("weather")
        or wx.get("display_weather_id")
        or wx.get("weather_id")
        or "clear",
    )
    weather_label = str(wx.get("weather_label") or wx.get("label") or weather)
    weather_next = wx.get("weather_next_roll_at") or wx.get("next_roll_at")

    hints = {
        "idle": "择时修炼可提升产出（清晨/深夜略优）",
        "breakthrough": "择时/择晴可略增突破成功率",
        "craft": "开工锁定天气；炼丹宜雨、忌雷暴（占位）",
        "tribulation": "雷暴抬高渡劫压力；开渡后表现劫云",
    }
    # 按当前天气给一句更具体的提示
    if weather in ("thunderstorm", "storm"):
        hints["tribulation"] = "当前雷雨：渡劫压力↑；炼丹效率↓"
        hints["craft"] = "雷暴锁定开工不利炼丹（占位）"
    elif weather == "clear":
        hints["breakthrough"] = "晴天：突破成功率略升（占位）"
        hints["idle"] = "晴天：修炼产出略升（占位）"
    elif weather == "rain":
        hints["craft"] = "雨天：炼丹效率略升（占位）"
    elif weather == "tribulation_cloud":
        hints["tribulation"] = "劫云覆盖中（结算仍按开渡前锁定天气）"

    return {
        "shichen": shichen,
        "shichen_label": shichen_label,
        "next_shichen_at": next_shichen_at,
        "weather": weather,
        "weather_label": weather_label,
        "weather_next_roll_at": weather_next,
        "hints": hints,
        "calendar_enabled": not bool(cal.get("disabled")),
        "region_id": wx.get("region_id") or "default",
        # 嵌套原文保留，便于调试；前端以扁平字段为准
        "calendar": cal,
        "weather_detail": wx,
        # 当前时辰/天气 catalog 片段 + 无角色标签的挂机预览
        "catalog": {
            "shichen": (get_game_config().calendar.catalog.get(shichen) or {}),
            "weather": (get_game_config().weather.catalog.get(weather) or {}),
        },
        "idle_preview": EnvPreviewService.for_world(),
    }


@router.get("/calendar", response_model=None)
async def get_calendar(
    _current_user: User = Depends(get_current_user),
) -> dict:
    """当前六时与下一时 ETA。"""
    data = CalendarService().get_snapshot()
    # 兼容前端字段名
    return success(
        {
            **data,
            "shichen": data.get("shichen_id"),
            "shichen_label": data.get("label"),
            "next_shichen_at": data.get("next_at"),
        },
    )


@router.get("/weather", response_model=None)
async def get_weather(
    region_id: str = "default",
    _current_user: User = Depends(get_current_user),
) -> dict:
    """默认区天气与下次滚动 ETA。"""
    data = WeatherService().get_snapshot(region_id=region_id)
    return success(
        {
            **data,
            "weather": data.get("display_weather_id") or data.get("weather_id"),
            "weather_label": data.get("label"),
            "weather_next_roll_at": data.get("next_roll_at"),
        },
    )


@router.get("/env", response_model=None)
async def get_env(
    _current_user: User = Depends(get_current_user),
) -> dict:
    """聚合 calendar + weather + 行为提示（扁平 WorldEnvPublic）。"""
    cal = CalendarService().get_snapshot()
    wx = WeatherService().get_snapshot()
    return success(_flatten_env(cal, wx))
