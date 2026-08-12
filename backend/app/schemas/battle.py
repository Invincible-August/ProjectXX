"""战斗 API Schema（M1 数值对撞 → M3 棋盘化）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PveBattleRequest(BaseModel):
    """``POST /battle/pve`` 请求体（M3：走棋盘引擎）。"""

    monster_id: str = Field(
        default="tutorial_slime",
        description="怪物配置键",
    )
    preset_slot: int | None = Field(
        default=None,
        ge=0,
        le=2,
        description="进攻预设槽位；缺省取 role=attack 预设（无布阵回退本体锚点）",
    )
    use_dao: bool = Field(default=False, description="是否运用本命道（M6）")


class PvpAttackRequest(BaseModel):
    """``POST /battle/pvp/attack`` 请求体（攻打对方防守快照）。"""

    target_character_id: int = Field(ge=1, description="目标角色 id")
    preset_slot: int | None = Field(
        default=None,
        ge=0,
        le=2,
        description="进攻预设槽位；缺省取 role=attack 预设",
    )
    use_dao: bool = Field(default=False, description="是否运用本命道（M6）")
