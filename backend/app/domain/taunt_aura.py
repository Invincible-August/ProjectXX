"""
嘲讽光环纯函数（嘲讽光环设计.md · M3-D06 Phase A）。

- 形状 → 覆盖格位掩码；
- 按侧聚合 ``taunt_aura_mask`` + 确定性 ``aura_owner``；
- 进入格触发 / 死亡清除。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

from typing import Any

from app.domain.board_tables import (
    BOARD_SIZE,
    CELL_COUNT,
    CHEBYSHEV_ROW,
    ORTHO_MASK,
    RANGE_MASK_EX,
    cell_of,
    x_of,
    y_of,
)

# 合法形状枚举（与 YAML / ADM 对齐）
SHAPE_ORTHO = "ortho_adjacent"
SHAPE_CHEBYSHEV = "chebyshev"
SHAPE_OFFSETS = "offsets"
VALID_SHAPES = frozenset({SHAPE_ORTHO, SHAPE_CHEBYSHEV, SHAPE_OFFSETS})


def validate_aura_def(aura_id: str, body: dict[str, Any]) -> None:
    """
    校验单条光环定义字段合法性（加载 / ADM probe 共用）。

    参数:
        aura_id: 光环 ID。
        body: 原始定义 mapping。

    抛出:
        ValueError: shape / radius / cells 非法时。
    """
    shape = str(body.get("shape", "")).strip()
    if shape not in VALID_SHAPES:
        raise ValueError(
            f"taunt_auras.{aura_id}.shape={shape!r} 非法；"
            f"须为 {sorted(VALID_SHAPES)}",
        )
    if shape == SHAPE_CHEBYSHEV:
        radius = int(body.get("radius", 0) or 0)
        if radius < 1:
            raise ValueError(f"taunt_auras.{aura_id}: chebyshev 须 radius≥1")
        if radius >= len(RANGE_MASK_EX):
            raise ValueError(
                f"taunt_auras.{aura_id}: radius={radius} 超出表上限 "
                f"{len(RANGE_MASK_EX) - 1}",
            )
    if shape == SHAPE_OFFSETS:
        cells = body.get("cells") or []
        if not isinstance(cells, list) or not cells:
            raise ValueError(f"taunt_auras.{aura_id}: offsets 须非空 cells[]")
        for item in cells:
            if not isinstance(item, dict):
                raise ValueError(f"taunt_auras.{aura_id}: cells 项须为 {{dx,dy}}")
            int(item.get("dx", 0))
            int(item.get("dy", 0))


def aura_snapshot_from_def(aura_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """
    将注册表条目压成引擎可吃的快照（无 IO）。

    参数:
        aura_id: 光环 ID。
        body: 已校验的定义（dataclass 也可先转 dict）。

    返回:
        可 JSON 序列化的快照 dict。
    """
    validate_aura_def(aura_id, body)
    shape = str(body["shape"])
    cells_raw = body.get("cells") or []
    cells: list[dict[str, int]] = []
    if shape == SHAPE_OFFSETS:
        for item in cells_raw:
            cells.append({"dx": int(item["dx"]), "dy": int(item["dy"])})
    duration = body.get("duration_rounds", None)
    return {
        "aura_id": aura_id,
        "label_zh": str(body.get("label_zh", aura_id)),
        "summary": str(body.get("summary", "")),
        "shape": shape,
        "radius": int(body["radius"]) if shape == SHAPE_CHEBYSHEV else None,
        "cells": cells,
        "include_self_cell": bool(body.get("include_self_cell", False)),
        "duration_rounds": int(duration) if duration is not None else None,
    }


def coverage_mask(center: int, aura: dict[str, Any] | None) -> int:
    """
    计算嘲讽者站在 ``center`` 时的覆盖格掩码。

    参数:
        center: 嘲讽者当前扁平格。
        aura: 单位上的光环快照；None / 空 → 0。

    返回:
        位掩码；越界偏移自动丢弃。
    """
    if not aura:
        return 0
    shape = str(aura.get("shape", ""))
    include_self = bool(aura.get("include_self_cell", False))
    mask = 0
    if shape == SHAPE_ORTHO:
        mask = int(ORTHO_MASK[center])
    elif shape == SHAPE_CHEBYSHEV:
        radius = int(aura.get("radius") or 1)
        radius = min(radius, len(RANGE_MASK_EX) - 1)
        mask = int(RANGE_MASK_EX[radius][center])
    elif shape == SHAPE_OFFSETS:
        cx, cy = x_of(center), y_of(center)
        for item in aura.get("cells") or []:
            nx = cx + int(item["dx"])
            ny = cy + int(item["dy"])
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                mask |= 1 << cell_of(nx, ny)
    else:
        return 0
    if include_self:
        mask |= 1 << center
    else:
        mask &= ~(1 << center)
    return mask


def _owner_key(cell: int, taunter_cell: int, taunter_uid: str) -> tuple[int, str]:
    """多光环重叠时的确定性归属键（切比雪夫升序，再 uid）。"""
    return (int(CHEBYSHEV_ROW[cell][taunter_cell]), taunter_uid)


def rebuild_taunt_auras(state: Any) -> None:
    """
    全量重建 ``taunt_aura_mask`` 与 ``aura_owner``。

    仅统计存活且挂载光环快照的单位；按嘲讽者所在侧写入掩码
    （对方踏入该掩码时被嘲讽）。

    参数:
        state: ``BattleState``。
    """
    state.taunt_aura_mask = [0, 0]
    state.aura_owner = [-1] * CELL_COUNT
    # 冲突时保留更优归属：先记下当前胜者键
    best_keys: list[tuple[int, str] | None] = [None] * CELL_COUNT

    for slot in range(state.count):
        if not state.alive[slot]:
            continue
        aura = state.taunt_aura[slot]
        if not aura:
            continue
        side = int(state.side[slot])
        center = int(state.cell[slot])
        cover = coverage_mask(center, aura)
        state.taunt_aura_mask[side] |= cover
        uid = str(state.uid[slot])
        m = cover
        while m:
            low = m & -m
            cell = low.bit_length() - 1
            m ^= low
            key = _owner_key(cell, center, uid)
            prev = best_keys[cell]
            if prev is None or key < prev:
                best_keys[cell] = key
                state.aura_owner[cell] = slot


def clear_taunts_pointing_to(state: Any, dead_slot: int) -> None:
    """
    嘲讽者死亡后：清除所有指向它的 ``taunt_target``，并重建掩码。

    参数:
        state: 战斗态。
        dead_slot: 刚阵亡的槽位。
    """
    for i in range(state.count):
        if state.taunt_target[i] == dead_slot:
            state.taunt_target[i] = -1
    rebuild_taunt_auras(state)


def clear_taunt(
    state: Any,
    victim_slot: int,
    *,
    reason: str = "cleared",
    events: list[dict[str, Any]] | None = None,
) -> bool:
    """
    解除单个单位的强制目标（Phase B：时长到期 / 驱散钩子）。

    Phase A 死亡路径走 ``clear_taunts_pointing_to``；本函数供后续技能/buff 调用。

    参数:
        state: 战斗态。
        victim_slot: 被嘲讽者槽位。
        reason: 战报原因键（如 ``expired`` / ``dispel``）。
        events: 若提供且原先有强制目标，追加 ``ai_retarget``（to_uid=null）。

    返回:
        True 表示原先确实有强制目标并已清除。
    """
    if victim_slot < 0 or victim_slot >= state.count:
        return False
    old = int(state.taunt_target[victim_slot])
    if old < 0:
        return False
    state.taunt_target[victim_slot] = -1
    if events is not None:
        events.append(
            {
                "type": "ai_retarget",
                "from_uid": state.uid[old] if old < state.count else None,
                "to_uid": None,
                "reason": f"taunt_{reason}",
            },
        )
    return True


def try_apply_taunt_on_enter(
    state: Any,
    mover_slot: int,
    cell: int,
    events: list[dict[str, Any]],
) -> bool:
    """
    单位踏入 ``cell`` 后尝试触发嘲讽。

    参数:
        state: 战斗态。
        mover_slot: 移动者槽位。
        cell: 新落格。
        events: 战报事件列表（就地 append）。

    返回:
        True 表示已触发强制目标（调用方应 STOP_TAUNT）。
    """
    side = int(state.side[mover_slot])
    enemy_side = 1 - side
    if not ((state.taunt_aura_mask[enemy_side] >> cell) & 1):
        return False
    owner = int(state.aura_owner[cell])
    if owner < 0 or not state.alive[owner]:
        return False
    if int(state.side[owner]) == side:
        return False
    old = int(state.taunt_target[mover_slot])
    state.taunt_target[mover_slot] = owner
    events.append(
        {
            "type": "taunt",
            "taunter": state.uid[owner],
            "victim": state.uid[mover_slot],
            "cell": {"x": x_of(cell), "y": y_of(cell)},
        },
    )
    if old != owner:
        from_uid = state.uid[old] if 0 <= old < state.count else None
        events.append(
            {
                "type": "ai_retarget",
                "from_uid": from_uid,
                "to_uid": state.uid[owner],
                "reason": "taunt",
            },
        )
    return True
