"""
最小视线 / LOS（M3 轴对齐+对角 · M3-D02 完整 LOS 前）。

统一障碍 + 禁制遮挡判定，供决策层（combat_ai）与执行层（autochess）共用，
避免两处各写一套 mask / block_source。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.board_tables import RAY_BETWEEN


class _TerrainLosView(Protocol):
    """地形 LOS 所需最小接口（TerrainState duck-type）。"""

    def obstacle_mask(self) -> int:
        """存活障碍掩码。"""
        ...

    def seal_los_mask(self, attack_kind: str) -> int:
        """对该攻击类别生效的禁制掩码。"""
        ...


def los_block_mask(terrain: _TerrainLosView, attack_kind: str) -> int:
    """
    远程最小 LOS 遮挡掩码：障碍一律挡 + 对该 ``attack_kind`` 生效的禁制。

    参数:
        terrain: 战斗地形态。
        attack_kind: 攻击方 ``attack_kind``（决定禁制子类是否生效）。

    返回:
        中间格若与此掩码相交则视线被挡。
    """
    return int(terrain.obstacle_mask()) | int(terrain.seal_los_mask(attack_kind))


def ranged_line_blocked(
    attacker_cell: int,
    target_cell: int,
    block_mask: int,
) -> bool:
    """
    直线中间格是否与遮挡掩码相交。

    仅共行 / 共列 / 共对角有中间格；其它角度按设计简化为不遮挡（M3-D02）。
    """
    return bool(RAY_BETWEEN[attacker_cell][target_cell] & block_mask)


def los_block_source(
    terrain: _TerrainLosView,
    attacker_cell: int,
    target_cell: int,
    attack_kind: str,
) -> str | None:
    """
    判定远程 LOS 被谁挡住（战报 ``block_source``）。

    优先级：禁制（seal）先于障碍（obstacle），与「专类挡远程」叙事一致。

    参数:
        terrain: 战斗地形态。
        attacker_cell / target_cell: 扁平格索引。
        attack_kind: 攻击类别。

    返回:
        ``\"seal\"`` / ``\"obstacle\"`` / ``None``（未挡）。
    """
    mid = RAY_BETWEEN[attacker_cell][target_cell]
    if not mid:
        return None
    if mid & int(terrain.seal_los_mask(attack_kind)):
        return "seal"
    if mid & int(terrain.obstacle_mask()):
        return "obstacle"
    return None


def los_block_mask_for_unit(state: Any, slot: int) -> int:
    """
    从战斗态取某单位的 LOS 遮挡掩码（决策层便捷入口）。

    参数:
        state: ``BattleState``（须有 ``terrain`` / ``attack_kind``）。
        slot: 单位槽位。
    """
    return los_block_mask(state.terrain, str(state.attack_kind[slot]))
