"""世界环境 API Schema（M5）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CalendarPublic(BaseModel):
    """``GET /world/calendar`` 响应体。"""

    shichen_id: str = Field(description="当前时辰键：dawn/noon/afternoon/dusk/night/late_night")
    slot: int = Field(description="时辰槽位 0～5")
    label: str | None = Field(default=None, description="时辰中文名（清晨/正午/…）")
    next_at: str = Field(description="下一时辰边界 UTC ISO")
    server_now: str = Field(description="服务器当前 UTC ISO")
    slot_seconds: int = Field(default=60, description="一时辰对应现实秒数")
    forced: bool = Field(default=False, description="是否被 GM 强制时辰")
    disabled: bool = Field(default=False, description="历法总开关关闭时为 True")
    order: list[str] = Field(default_factory=list, description="六时循环顺序")
    labels: dict[str, str] = Field(default_factory=dict, description="时辰键→中文名表")


class WeatherPublic(BaseModel):
    """``GET /world/weather`` 响应体。"""

    region_id: str = Field(default="default", description="区域 id；M5 仅 default")
    weather_id: str = Field(description="权威天气键：clear/cloudy/rain/hurricane/storm/thunder")
    display_weather_id: str | None = Field(
        default=None,
        description="展示用天气（劫云覆盖时可为 tribulation_cloud）",
    )
    label: str | None = Field(default=None, description="天气中文名")
    next_roll_at: str = Field(description="下次天气池滚动 UTC ISO")
    server_now: str = Field(description="服务器当前 UTC ISO")
    forced: bool = Field(default=False, description="是否被 GM 强制天气")
    in_cloud: bool = Field(default=False, description="本区是否处于劫云覆盖")
    disabled: bool = Field(default=False, description="天气总开关关闭时为 True")


class WorldEnvPublic(BaseModel):
    """``GET /world/env`` 聚合（扁平字段为主；嵌套保留调试）。"""

    calendar: dict = Field(description="历法摘要（与 CalendarPublic 对齐的 dict）")
    weather: dict = Field(description="天气摘要（与 WeatherPublic 对齐的 dict）")
    hints: dict = Field(default_factory=dict, description="对当前行为的环境提示文案")
    catalog: dict | None = Field(default=None, description="时辰/天气说明 catalog（显性设计）")
    idle_preview: dict | None = Field(default=None, description="挂机有效速率预览")
