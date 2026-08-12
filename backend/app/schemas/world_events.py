"""世界事件骨架 Schema。"""

from __future__ import annotations

from pydantic import BaseModel


class WorldEventRegisterRequest(BaseModel):
    """报名占位（路径已含 id，可空体）。"""

    pass
