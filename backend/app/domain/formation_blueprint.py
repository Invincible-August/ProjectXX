"""
阵法蓝图：部署区解析 / 强制移位 / 定稿校验。

对齐 ``阵法部署与自研设计.md`` §3～§5（M3-D08 Phase A）。

封装要点：
- 部署解析一次产出 ``FormationDeploySnapshot``（禁停 + 有效格）；
- 地形格统一经 ``iter_terrain_cells`` 迭代，避免 dict/对象双路径散落；
- 开战移位只依赖 ``ShiftBoardState`` Protocol，不绑引擎具体类。

纯度纪律：不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Literal, Protocol, runtime_checkable

from app.domain.board import default_deploy_cells, in_board
from app.domain.board_tables import BOARD_SIZE, cell_of, mirror_x, x_of, y_of
from app.domain.terrain import TERRAIN_OBSTACLE, TERRAIN_RAVINE, TERRAIN_SEAL

# 部署模式枚举（与 YAML deploy.mode 对齐）
DeployMode = Literal["default", "fixed", "free_own", "mask"]
TerrainLayoutMode = Literal["none", "fixed", "brush"]

# 合法部署 / 地形布局模式（解析时校验）
_VALID_DEPLOY_MODES: frozenset[str] = frozenset({"default", "fixed", "free_own", "mask"})
_VALID_TERRAIN_LAYOUT_MODES: frozenset[str] = frozenset({"none", "fixed", "brush"})

# 地形禁停类型：部署不可落子；移位目标亦不可落（与 terrain.py 常量同源）
BLOCKING_TERRAIN_TYPES: frozenset[str] = frozenset(
    {TERRAIN_OBSTACLE, TERRAIN_RAVINE, TERRAIN_SEAL},
)


@dataclass(frozen=True)
class DeployConfig:
    """
    阵法部署契约（定稿时写死）。

    Attributes:
        mode: 部署模式。
        max_units: 阵法额外上阵上限；None 表示不额外收紧。
        cells: fixed/mask 的显式格表。
        add_cells: default/fixed 追加格。
        exclude_cells: 从计算结果中扣除的格。
        allow_neutral: 是否允许中立列。
    """

    mode: DeployMode
    max_units: int | None = None
    cells: tuple[tuple[int, int], ...] = ()
    add_cells: tuple[tuple[int, int], ...] = ()
    exclude_cells: tuple[tuple[int, int], ...] = ()
    allow_neutral: bool = False


@dataclass(frozen=True)
class TerrainLayoutConfig:
    """
    地形布局元数据（出战不再改地形；brush 约束供定稿/后台校验）。

    Attributes:
        mode: none / fixed / brush。
        max_obstacles: brush 预算（障碍）。
        max_ravines: brush 预算（深渊）。
        allowed_types: brush 允许的地形类型。
        paint_zone: own_half | mask。
        paint_cells: paint_zone=mask 时的可刷区。
    """

    mode: TerrainLayoutMode = "fixed"
    max_obstacles: int | None = None
    max_ravines: int | None = None
    allowed_types: tuple[str, ...] = (TERRAIN_OBSTACLE, TERRAIN_RAVINE, TERRAIN_SEAL)
    paint_zone: str = "own_half"
    paint_cells: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class ForceShiftRule:
    """
    单条开战强制移位（进攻方视角坐标）。

    Attributes:
        from_xy: 源格。
        to_xy: 目标格。
        only_kinds: 可选种类过滤；空=任意对方棋子。
    """

    from_xy: tuple[int, int]
    to_xy: tuple[int, int]
    only_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormationDeploySnapshot:
    """
    一次解析得到的部署运行时视图（禁停 + 有效格）。

    供校验、API 高亮、上阵上限共用，避免重复 resolve。
    """

    blocked_cells: frozenset[tuple[int, int]]
    deploy_cells: frozenset[tuple[int, int]]

    def max_units_for(
        self,
        board_cfg: Any,
        major_realm: str,
        *,
        formation_max_units: int | None,
    ) -> int:
        """境界 ∩ 合法格数 ∩ 阵法上限。"""
        return effective_max_units(
            board_cfg,
            major_realm,
            deploy_cell_count=len(self.deploy_cells),
            formation_max_units=formation_max_units,
        )


@runtime_checkable
class ShiftBoardState(Protocol):
    """开战强制移位所需的最小战斗态接口（就地改 cell）。"""

    count: int
    uid: list[str]
    kind: list[str]
    side: list[int]
    cell: list[int]
    alive: list[bool]

    def slot_at(self, cell: int) -> int:
        """查某格存活单位槽位；无则 -1。"""
        ...


def default_deploy_config() -> DeployConfig:
    """缺省部署契约：与旧表兼容的 default 模式。"""
    return DeployConfig(mode="default")


def default_terrain_layout(*, has_terrain: bool) -> TerrainLayoutConfig:
    """有 terrain[] → fixed；无 → none。"""
    return TerrainLayoutConfig(mode="fixed" if has_terrain else "none")


def iter_terrain_cells(terrain: Any) -> Iterator[tuple[int, int, str]]:
    """
    统一迭代地形格为 ``(x, y, type)``。

    兼容 ``FormationTerrainCell``、dict、以及带 ``type`` 属性的对象。
    """
    for cell in terrain or ():
        if isinstance(cell, dict):
            yield int(cell["x"]), int(cell["y"]), str(cell.get("type", ""))
            continue
        terrain_type = getattr(cell, "terrain_type", None)
        if terrain_type is None:
            terrain_type = getattr(cell, "type", "")
        yield int(cell.x), int(cell.y), str(terrain_type)


def parse_cell_list(raw: Any, *, field_name: str) -> tuple[tuple[int, int], ...]:
    """
    解析 ``[[x,y], ...]`` 或 ``[{x,y}, ...]`` 为坐标元组。

    Raises:
        ValueError: 格式非法。
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} 须为列表")
    cells: list[tuple[int, int]] = []
    for index, item in enumerate(raw):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            cells.append((int(item[0]), int(item[1])))
        elif isinstance(item, dict) and "x" in item and "y" in item:
            cells.append((int(item["x"]), int(item["y"])))
        else:
            raise ValueError(f"{field_name}[{index}] 须为 [x,y] 或 {{x,y}}")
    return tuple(cells)


def parse_deploy_config(raw: Any) -> DeployConfig:
    """
    解析 YAML ``deploy`` 块；缺省 → default 模式。

    Raises:
        ValueError: mode / 字段语义非法。
    """
    if not raw:
        return default_deploy_config()
    if not isinstance(raw, dict):
        raise ValueError("deploy 须为 mapping")
    mode = str(raw.get("mode", "default"))
    if mode not in _VALID_DEPLOY_MODES:
        raise ValueError(f"deploy.mode 非法：{mode}")
    max_units_raw = raw.get("max_units")
    max_units = int(max_units_raw) if max_units_raw is not None else None
    cells = parse_cell_list(raw.get("cells"), field_name="deploy.cells")
    add_cells = parse_cell_list(raw.get("add_cells"), field_name="deploy.add_cells")
    exclude_cells = parse_cell_list(raw.get("exclude_cells"), field_name="deploy.exclude_cells")
    allow_neutral = bool(raw.get("allow_neutral", False))

    # free_own 禁止 add_cells（语义冲突）
    if mode == "free_own" and add_cells:
        raise ValueError("deploy.mode=free_own 时禁止 add_cells")
    if mode in ("fixed", "mask") and not cells:
        raise ValueError(f"deploy.mode={mode} 时 cells 不可为空")
    if max_units is not None and max_units < 1:
        raise ValueError("deploy.max_units 须 ≥ 1")

    return DeployConfig(
        mode=mode,  # type: ignore[arg-type]
        max_units=max_units,
        cells=cells,
        add_cells=add_cells,
        exclude_cells=exclude_cells,
        allow_neutral=allow_neutral,
    )


def parse_terrain_layout(raw: Any, *, has_terrain: bool) -> TerrainLayoutConfig:
    """解析 ``terrain_layout``；缺省按是否有 terrain 推断。"""
    if not raw:
        return default_terrain_layout(has_terrain=has_terrain)
    if not isinstance(raw, dict):
        raise ValueError("terrain_layout 须为 mapping")
    mode = str(raw.get("mode", "fixed" if has_terrain else "none"))
    if mode not in _VALID_TERRAIN_LAYOUT_MODES:
        raise ValueError(f"terrain_layout.mode 非法：{mode}")
    brush = raw.get("brush") or {}
    if brush and not isinstance(brush, dict):
        raise ValueError("terrain_layout.brush 须为 mapping")
    allowed = brush.get("allowed_types") or [TERRAIN_OBSTACLE, TERRAIN_RAVINE, TERRAIN_SEAL]
    paint_cells = parse_cell_list(brush.get("paint_cells"), field_name="brush.paint_cells")
    paint_zone = str(brush.get("paint_zone", "own_half"))
    if paint_zone == "mask" and not paint_cells:
        raise ValueError("terrain_layout.brush.paint_zone=mask 时 paint_cells 不可为空")
    return TerrainLayoutConfig(
        mode=mode,  # type: ignore[arg-type]
        max_obstacles=(
            int(brush["max_obstacles"]) if brush.get("max_obstacles") is not None else None
        ),
        max_ravines=(
            int(brush["max_ravines"]) if brush.get("max_ravines") is not None else None
        ),
        allowed_types=tuple(str(t) for t in allowed),
        paint_zone=paint_zone,
        paint_cells=paint_cells,
    )


def parse_force_shifts(raw: Any) -> tuple[ForceShiftRule, ...]:
    """解析 ``force_shifts`` 列表。"""
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError("force_shifts 须为列表")
    rules: list[ForceShiftRule] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"force_shifts[{index}] 须为 mapping")
        from_raw = item.get("from")
        to_raw = item.get("to")
        if not (isinstance(from_raw, (list, tuple)) and len(from_raw) >= 2):
            raise ValueError(f"force_shifts[{index}].from 须为 [x,y]")
        if not (isinstance(to_raw, (list, tuple)) and len(to_raw) >= 2):
            raise ValueError(f"force_shifts[{index}].to 须为 [x,y]")
        kinds_raw = item.get("only_kinds") or []
        rules.append(
            ForceShiftRule(
                from_xy=(int(from_raw[0]), int(from_raw[1])),
                to_xy=(int(to_raw[0]), int(to_raw[1])),
                only_kinds=tuple(str(k) for k in kinds_raw),
            ),
        )
    return tuple(rules)


def terrain_blocked_cells_from_terrain(terrain: Any) -> frozenset[tuple[int, int]]:
    """从地形序列提取禁停坐标（进攻方视角）。"""
    return frozenset(
        (x, y)
        for x, y, terrain_type in iter_terrain_cells(terrain)
        if terrain_type in BLOCKING_TERRAIN_TYPES
    )


def resolve_deploy_cells(
    board_cfg: Any,
    deploy: DeployConfig,
    *,
    blocked_cells: frozenset[tuple[int, int]] = frozenset(),
) -> frozenset[tuple[int, int]]:
    """
    计算有效可部署格（进攻方视角）。

    规则：按 mode 取基集 → 减 exclude / 禁停 → 可选剔中立列 → 裁切半区。
    """
    own_x = {int(x) for x in board_cfg.zones.own_x}
    neutral_x = {int(x) for x in board_cfg.zones.neutral_x}
    size = int(getattr(board_cfg, "size", BOARD_SIZE))

    if deploy.mode == "default":
        cells = set(default_deploy_cells(board_cfg))
        cells.update(deploy.add_cells)
    elif deploy.mode == "fixed":
        cells = set(deploy.cells)
        cells.update(deploy.add_cells)
    elif deploy.mode == "free_own":
        cells = {(x, y) for x in own_x for y in range(size)}
    elif deploy.mode == "mask":
        cells = set(deploy.cells)
    else:
        raise ValueError(f"未知 deploy.mode：{deploy.mode}")

    cells.difference_update(deploy.exclude_cells)
    cells.difference_update(blocked_cells)

    if not deploy.allow_neutral:
        cells = {(x, y) for x, y in cells if x not in neutral_x}

    allowed_x = set(own_x)
    if deploy.allow_neutral:
        allowed_x |= neutral_x
    return frozenset(
        (x, y) for x, y in cells if x in allowed_x and in_board(x, y)
    )


def resolve_formation_deploy(
    board_cfg: Any,
    deploy: DeployConfig,
    terrain: Any,
) -> FormationDeploySnapshot:
    """
    一次解析：地形禁停 + 有效部署格。

    这是布阵校验 / API 高亮 / 上限计算的统一入口。
    """
    blocked = terrain_blocked_cells_from_terrain(terrain)
    cells = resolve_deploy_cells(board_cfg, deploy, blocked_cells=blocked)
    return FormationDeploySnapshot(blocked_cells=blocked, deploy_cells=cells)


def effective_max_units(
    board_cfg: Any,
    major_realm: str,
    *,
    deploy_cell_count: int,
    formation_max_units: int | None,
) -> int:
    """上阵上限 = min(境界配置, 合法格数, 阵法 max_units)。"""
    configured = board_cfg.max_units_by_major_realm.get(
        major_realm,
        board_cfg.default_max_units,
    )
    cap = min(int(configured), int(deploy_cell_count))
    if formation_max_units is not None:
        cap = min(cap, int(formation_max_units))
    return max(0, cap)


def validate_blueprint(
    board_cfg: Any,
    *,
    formation_id: str,
    deploy: DeployConfig,
    terrain_layout: TerrainLayoutConfig,
    terrain: Any,
    force_shifts: tuple[ForceShiftRule, ...],
) -> None:
    """
    定稿 / 发布 / 启动时的蓝图硬校验。

    Raises:
        ValueError: 任一规则不满足（message 含 formation_id）。
    """
    prefix = f"formations.{formation_id}"
    own_x = {int(x) for x in board_cfg.zones.own_x}
    enemy_x = {int(x) for x in board_cfg.zones.enemy_x}
    neutral_x = {int(x) for x in board_cfg.zones.neutral_x}
    hard_cap = int(board_cfg.default_max_units)

    if deploy.max_units is not None and deploy.max_units > hard_cap:
        raise ValueError(f"{prefix}.deploy.max_units 超过 board.default_max_units={hard_cap}")

    def _check_own_side_cells(
        cells: tuple[tuple[int, int], ...],
        field: str,
        *,
        allow_neutral: bool,
    ) -> None:
        """校验坐标落在己方（+可选中立），不得进敌区。"""
        for x, y in cells:
            if not in_board(x, y):
                raise ValueError(f"{prefix}.{field} 越界：({x},{y})")
            if x in enemy_x:
                raise ValueError(f"{prefix}.{field} 不可落在敌方半区：({x},{y})")
            if x in neutral_x and not allow_neutral:
                raise ValueError(f"{prefix}.{field} 含中立列但 allow_neutral=false：({x},{y})")
            if x not in own_x and not (allow_neutral and x in neutral_x):
                raise ValueError(f"{prefix}.{field} 须在己方半区：({x},{y})")

    _check_own_side_cells(deploy.cells, "deploy.cells", allow_neutral=deploy.allow_neutral)
    _check_own_side_cells(deploy.add_cells, "deploy.add_cells", allow_neutral=deploy.allow_neutral)
    for x, y in deploy.exclude_cells:
        if not in_board(x, y):
            raise ValueError(f"{prefix}.deploy.exclude_cells 越界：({x},{y})")

    blocked = terrain_blocked_cells_from_terrain(terrain)
    for x, y in blocked:
        if not in_board(x, y):
            raise ValueError(f"{prefix}.terrain 越界：({x},{y})")
        if x not in own_x:
            raise ValueError(f"{prefix}.terrain 须在己方半区：({x},{y})")

    # 部署声明格不得与地形禁停冲突
    conflict = (set(deploy.cells) | set(deploy.add_cells)) & blocked
    if conflict:
        raise ValueError(f"{prefix}: 部署格与地形禁停冲突 {sorted(conflict)}")

    if terrain_layout.mode == "brush":
        type_counts = {TERRAIN_OBSTACLE: 0, TERRAIN_RAVINE: 0}
        for _x, _y, terrain_type in iter_terrain_cells(terrain):
            if terrain_type in type_counts:
                type_counts[terrain_type] += 1
        if (
            terrain_layout.max_obstacles is not None
            and type_counts[TERRAIN_OBSTACLE] > terrain_layout.max_obstacles
        ):
            raise ValueError(f"{prefix}: 障碍数超过 brush 预算")
        if (
            terrain_layout.max_ravines is not None
            and type_counts[TERRAIN_RAVINE] > terrain_layout.max_ravines
        ):
            raise ValueError(f"{prefix}: 深渊数超过 brush 预算")

    for index, rule in enumerate(force_shifts):
        for label, x, y in (("from", *rule.from_xy), ("to", *rule.to_xy)):
            if not in_board(x, y):
                raise ValueError(f"{prefix}.force_shifts[{index}].{label} 越界")
            if x in own_x:
                raise ValueError(
                    f"{prefix}.force_shifts[{index}].{label} 禁止指向己方半区：({x},{y})",
                )
            if x in neutral_x:
                raise ValueError(
                    f"{prefix}.force_shifts[{index}].{label} 暂禁止中立列：({x},{y})",
                )
            if x not in enemy_x:
                raise ValueError(
                    f"{prefix}.force_shifts[{index}].{label} 须在敌对半区：({x},{y})",
                )

    cells = resolve_deploy_cells(board_cfg, deploy, blocked_cells=blocked)
    if not cells:
        raise ValueError(f"{prefix}: 有效部署格为空")


def validate_formation_def(board_cfg: Any, formation: Any) -> None:
    """
    对已解析的 ``FormationDef``（或同结构对象）做蓝图硬校验。

    启动加载与 ADM 发布共用此入口，避免逐字段拆包散落。
    """
    validate_blueprint(
        board_cfg,
        formation_id=str(formation.formation_id),
        deploy=formation.deploy,
        terrain_layout=formation.terrain_layout,
        terrain=formation.terrain,
        force_shifts=formation.force_shifts,
    )


def deploy_config_to_dict(deploy: DeployConfig) -> dict[str, Any]:
    """DeployConfig → API/plain dict。"""
    payload: dict[str, Any] = {
        "mode": deploy.mode,
        "cells": [list(c) for c in deploy.cells],
        "add_cells": [list(c) for c in deploy.add_cells],
        "exclude_cells": [list(c) for c in deploy.exclude_cells],
        "allow_neutral": deploy.allow_neutral,
    }
    if deploy.max_units is not None:
        payload["max_units"] = deploy.max_units
    return payload


def force_shifts_to_dict(rules: tuple[ForceShiftRule, ...]) -> list[dict[str, Any]]:
    """ForceShiftRule 序列 → plain list。"""
    out: list[dict[str, Any]] = []
    for rule in rules:
        item: dict[str, Any] = {
            "from": [rule.from_xy[0], rule.from_xy[1]],
            "to": [rule.to_xy[0], rule.to_xy[1]],
        }
        if rule.only_kinds:
            item["only_kinds"] = list(rule.only_kinds)
        out.append(item)
    return out


def blocking_terrain_flat_cells(terrain_items: list[dict[str, Any]]) -> frozenset[int]:
    """
    开战地形扁平列表 → 禁停格扁平索引集合。

    参数:
        terrain_items: ``_build_terrain_cells`` 产物（含 cell / type）。
    """
    return frozenset(
        int(item["cell"])
        for item in terrain_items
        if str(item.get("type")) in BLOCKING_TERRAIN_TYPES
    )


def apply_force_shifts_to_state(
    state: ShiftBoardState,
    *,
    attacker_shifts: list[dict[str, Any]] | None,
    defender_shifts: list[dict[str, Any]] | None,
    blocked_cells: frozenset[int] | None = None,
) -> list[dict[str, Any]]:
    """
    在战斗运行态上套用双方 force_shifts（顺序：攻方 → 守方）。

    坐标：蓝图存进攻方视角；守方规则 from/to 先 mirror_x。
    仅移动对方棋子。源空 noop；目标占 cancel；目标禁停 cancel。
    """
    events: list[dict[str, Any]] = []
    blocked = blocked_cells or frozenset()

    def _run_one(
        rule: dict[str, Any],
        *,
        owner_side: int,
        mirrored: bool,
        index: int,
    ) -> None:
        """执行单条移位。"""
        fx, fy = int(rule["from"][0]), int(rule["from"][1])
        tx, ty = int(rule["to"][0]), int(rule["to"][1])
        if mirrored:
            fx, tx = mirror_x(fx), mirror_x(tx)
        from_cell = cell_of(fx, fy)
        to_cell = cell_of(tx, ty)
        target_side = 1 - owner_side
        kinds = {str(k) for k in (rule.get("only_kinds") or [])}

        base = {
            "type": "force_shift",
            "owner_side": owner_side,
            "index": index,
            "from": {"x": fx, "y": fy},
            "to": {"x": tx, "y": ty},
        }

        src_slot = -1
        for slot in range(state.count):
            if (
                state.alive[slot]
                and state.side[slot] == target_side
                and state.cell[slot] == from_cell
            ):
                if kinds and state.kind[slot] not in kinds:
                    continue
                src_slot = slot
                break

        if src_slot < 0:
            events.append({**base, "result": "shift_noop"})
            return

        if to_cell in blocked:
            events.append({**base, "result": "shift_cancel_illegal", "reason": "blocked"})
            return
        occ = state.slot_at(to_cell)
        if occ >= 0:
            events.append({**base, "result": "shift_cancel_occupied", "uid": state.uid[occ]})
            return

        old = state.cell[src_slot]
        state.cell[src_slot] = to_cell
        events.append(
            {
                **base,
                "result": "shift_applied",
                "uid": state.uid[src_slot],
                "from_cell": {"x": x_of(old), "y": y_of(old)},
                "to_cell": {"x": tx, "y": ty},
            },
        )

    for index, rule in enumerate(attacker_shifts or []):
        _run_one(rule, owner_side=0, mirrored=False, index=index)
    for index, rule in enumerate(defender_shifts or []):
        _run_one(rule, owner_side=1, mirrored=True, index=index)
    return events
