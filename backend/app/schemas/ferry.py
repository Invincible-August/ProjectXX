"""待引渡 API Schema（M5）。"""

from __future__ import annotations

from pydantic import BaseModel


class FerrySelfRescueRequest(BaseModel):
    """``POST /ferry/self-rescue`` 空体占位（可扩展确认令牌）。"""

    confirm: bool = True
