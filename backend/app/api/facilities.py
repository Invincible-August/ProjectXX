"""设施 / 区域 / 活动只读预览（读 GameConfigBundle；可由后台热更）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.db.models import User
from app.schemas.common import success
from app.services.realm_config import get_game_config

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=None)
async def list_facilities(_user: User = Depends(get_current_user)) -> dict:
    """
    全站设施开关与活动摘要。

    数据来自 ``sects.yaml`` / ``activity.yaml``（经 ADM 发布覆盖）。
    """
    cfg = get_game_config()
    facilities = [
        {
            "facility_id": facility_id,
            "enabled": bool(body.get("enabled")),
            "note": str(body.get("note", "")),
        }
        for facility_id, body in cfg.sects.facilities.items()
    ]
    activities = [
        {
            "activity_id": activity_id,
            "enabled": bool(body.get("enabled")),
            "title": str(body.get("title", activity_id)),
            "note": str(body.get("note", "")),
        }
        for activity_id, body in cfg.activity.activities.items()
    ]
    return success({"facilities": facilities, "activities": activities})


@router.get("/map/regions", response_model=None)
async def list_map_regions(_user: User = Depends(get_current_user)) -> dict:
    """地图区域占位列表（M9 前供遭遇 region_id 校验）。"""
    cfg = get_game_config()
    regions = [
        {
            "region_id": region_id,
            "name": str(body.get("name", region_id)),
            "weather_region": str(body.get("weather_region", region_id)),
            "summary": str(body.get("summary", "")),
            "connections": list(body.get("connections") or []),
        }
        for region_id, body in cfg.map.regions.items()
    ]
    return success({"regions": regions})
