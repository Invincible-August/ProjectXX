"""
棋盘占位规则（M3战斗成型设计.md §3 · S1）。

纯规则层：坐标 / 三区 / 默认部署区 / 占位校验，无任何 IO。
预设一律按 **进攻方视角** 坐标存储；防守侧开战时由引擎做 x 镜像。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.board_tables import BOARD_SIZE, mirror_x


class PlacementError(Exception):
    """
    占位校验失败的领域异常。

    属性:
        code: 业务错误码（40041 非法占位 / 40042 本体问题 / 40043 未开放种类）。
        message: 面向玩家的中文提示。
    """

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class DeployZone:
    """一侧的合法部署区（进攻方视角坐标）。"""

    cells: frozenset[tuple[int, int]]

    def contains(self, x: int, y: int) -> bool:
        """判断 (x, y) 是否在部署区内。"""
        return (x, y) in self.cells


def default_deploy_cells(board_cfg: Any) -> frozenset[tuple[int, int]]:
    """
    计算无阵法时进攻方的默认可部署格集合。

    参数:
        board_cfg: ``BoardConfig``（realm_config 解析产物）。

    返回:
        frozenset: 默认矩形 (x_min..x_max) × (y_min..y_max) 的格集合。
    """
    rect = board_cfg.default_deploy
    return frozenset(
        (x, y)
        for x in range(rect.x_min, rect.x_max + 1)
        for y in range(rect.y_min, rect.y_max + 1)
    )


def mirrored_cells(cells: frozenset[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    """将进攻方视角格集合镜像为防守方实际落位（x' = 6 - x）。"""
    return frozenset((mirror_x(x), y) for x, y in cells)


def in_board(x: int, y: int) -> bool:
    """坐标是否落在 7×7 棋盘内。"""
    return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE


def validate_placement(
    units: list[dict[str, Any]],
    board_cfg: Any,
    *,
    max_units: int,
    blocked_cells: frozenset[tuple[int, int]] = frozenset(),
    deploy_zone: frozenset[tuple[int, int]] | None = None,
    require_main: bool = True,
    allow_solo_avatar: bool = False,
) -> None:
    """
    校验一份布阵（进攻方视角坐标）的占位合法性。

    校验项（对应设计 §3.4 + 阵法部署设计 §3）:
        1. 每格最多 1 棋子（重叠 → 40041）。
        2. 坐标须落在有效部署区内（区外 / 中立列 → 40041）。
        3. 上阵数 ≤ max_units（超员 → 40041）。
        4. 本体必须上阵且唯一（缺失 / 重复 → 40042）；
           若 ``allow_solo_avatar`` 且 ``require_main=False``，允许无本体但须 ≥1 avatar（否则 40093）。
        5. 棋子种类须已开放（pet/avatar 等未开放 → 40043）。
        6. 不可落在地形禁停格上（障碍 / 深渊 → 40041）。

    参数:
        units: ``[{unit_uid, unit_kind, x, y}, ...]``。
        board_cfg: ``BoardConfig``。
        max_units: 当前允许的上阵上限。
        blocked_cells: 己方阵法地形的禁停格（进攻方视角坐标）。
        deploy_zone: 有效可部署格；None 时回退默认部署区。
        require_main: 是否强制本体上阵（默认 True）。
        allow_solo_avatar: 独战模式：无本体时必须有化身。

    异常:
        PlacementError: 任一规则不满足。
    """
    if not units:
        raise PlacementError(40042, "布阵不能为空：本体必须上阵")

    if len(units) > max_units:
        raise PlacementError(40041, f"上阵数量超出上限（最多 {max_units} 个）")

    # 有效部署区：阵法 resolve 结果优先，否则默认 6 格
    zone = deploy_zone if deploy_zone is not None else default_deploy_cells(board_cfg)
    seen_cells: set[tuple[int, int]] = set()
    main_count = 0
    avatar_count = 0

    for unit in units:
        kind = str(unit.get("unit_kind", ""))
        gate = board_cfg.unit_kinds.get(kind)
        # 未知种类与未开放种类统一 40043（版本闸门只挡内容不挡模型）
        if gate is None or not gate.enabled:
            raise PlacementError(40043, f"棋子类型未开放：{kind or '未知'}")
        if kind == "main":
            main_count += 1
        elif kind == "avatar":
            avatar_count += 1

        x, y = int(unit.get("x", -1)), int(unit.get("y", -1))
        if not in_board(x, y):
            raise PlacementError(40041, f"坐标越界：({x},{y})")
        if (x, y) not in zone:
            raise PlacementError(40041, f"非法占位：({x},{y}) 不在可部署区内")
        if (x, y) in blocked_cells:
            raise PlacementError(40041, f"该格被阵法地形占用，不可停留：({x},{y})")
        if (x, y) in seen_cells:
            raise PlacementError(40041, f"同一格重复落子：({x},{y})")
        seen_cells.add((x, y))

    if main_count > 1:
        raise PlacementError(40042, "本体必须唯一，不可重复上阵")
    if main_count == 0:
        if require_main:
            raise PlacementError(40042, "缺少本体：本体必须上阵")
        if allow_solo_avatar and avatar_count < 1:
            raise PlacementError(40093, "独战编成须至少含化身")
    elif not require_main and allow_solo_avatar:
        # 有本体时仍合法（同场上阵）
        pass


def max_units_for_realm(
    board_cfg: Any,
    major_realm: str,
    *,
    deploy_cell_count: int | None = None,
    formation_max_units: int | None = None,
) -> int:
    """
    查询某大境界的上阵上限。

    规则：min(境界配置上限, 合法部署格数, 阵法 max_units)；
    未配置的境界回退到 ``default_max_units``。
    """
    from app.domain.formation_blueprint import effective_max_units

    cell_count = (
        deploy_cell_count
        if deploy_cell_count is not None
        else len(default_deploy_cells(board_cfg))
    )
    return effective_max_units(
        board_cfg,
        major_realm,
        deploy_cell_count=cell_count,
        formation_max_units=formation_max_units,
    )


def board_meta_payload(board_cfg: Any) -> dict[str, Any]:
    """
    组装 ``GET /formation/board-meta`` 的只读元数据。

    返回:
        dict: 棋盘尺寸、三区、默认部署格、镜像规则说明等（供前端画盘高亮）。
    """
    rect = board_cfg.default_deploy
    return {
        "size": board_cfg.size,
        "zones": {
            "own_x": list(board_cfg.zones.own_x),
            "neutral_x": list(board_cfg.zones.neutral_x),
            "enemy_x": list(board_cfg.zones.enemy_x),
        },
        "default_deploy": {
            "x_min": rect.x_min,
            "x_max": rect.x_max,
            "y_min": rect.y_min,
            "y_max": rect.y_max,
        },
        "default_deploy_cells": sorted(default_deploy_cells(board_cfg)),
        "default_max_units": board_cfg.default_max_units,
        "default_anchor_unit": {
            "x": board_cfg.default_anchor[0],
            "y": board_cfg.default_anchor[1],
        },
        # 防守方由引擎镜像：x' = size-1 - x，y 不变；预设一律存进攻方视角
        "mirror_rule": "defender_mirror_x",
        "unit_kinds": {
            kind: {
                "unique": gate.unique,
                "required": gate.required,
                "enabled": gate.enabled,
            }
            for kind, gate in board_cfg.unit_kinds.items()
        },
    }
