"""
默认 AI 决策（M3自动移动攻击算法设计.md §6 · 零搜索查表版 + 占位协调）。

每个 AP 调用一次 ``decide_action``，返回一个原子动作：
    - ``ACT_ATTACK_UNIT``：攻击敌方单位（当前位置可打到且视线未被遮挡）。
    - ``ACT_ATTACK_OBSTACLE``：攻击挡路障碍（首步是可破障碍时）。
    - ``ACT_MOVE``：向「最少 AP 就能打到」的敌人靠近，或为友军让路侧移。
    - ``ACT_IDLE``：无可达目标。

估价口径（唯一标准）:
    approach_ap(T) = min over c∈AttackPos(T)∩standable of ceil(STEP_soft[cur][c] / mp)
    优先键 = (approach_turns, approach_ap, chebyshev(cur, T), uid)

占位协调（§5.4 修订）:
    - 规划/执行把「其它单位」当作软墙：局部 BFS 绕行（不重建全源地形表）。
    - 若友军堵死唯一地形走廊、己方又无法软墙绕行 → 阻挡者优先侧移让路。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic；决策路径无随机。
"""

from __future__ import annotations

from collections import deque
from typing import Any

from app.domain.board_tables import (
    CELL_COUNT,
    CHEBYSHEV_ROW,
    FULL_MASK,
    ORTHO_MASK,
    ORTHO_NEIGHBORS,
    RANGE_MASK_EX,
)
from app.domain.line_of_sight import (
    los_block_mask,
    ranged_line_blocked,
)
from app.domain.terrain import UNREACHABLE

# 动作类型常量
ACT_ATTACK_UNIT = 1
ACT_ATTACK_OBSTACLE = 2
ACT_MOVE = 3
ACT_IDLE = 4


def attack_reach_mask(cell: int, is_melee: bool, attack_range: int) -> int:
    """
    当前站位的可攻击格掩码。

    近战：仅正交四向邻接；远程：切比雪夫 ≤ 射程（八向含斜角）。
    """
    if is_melee:
        return ORTHO_MASK[cell]
    r = min(attack_range, len(RANGE_MASK_EX) - 1)
    return RANGE_MASK_EX[r][cell]


def ranged_attack_blocked(attacker_cell: int, target_cell: int, block_mask: int) -> bool:
    """
    最小 LOS：远程攻击是否被直线中间格上的障碍 / 禁制遮挡。

    委托 ``line_of_sight.ranged_line_blocked``（与执行层同源）。
    """
    return ranged_line_blocked(attacker_cell, target_cell, block_mask)


def _approach_ap(
    step_row: list[int],
    attack_pos_mask: int,
    cur_cell: int,
    mp: int,
) -> tuple[int, int]:
    """
    计算接近某目标的最少 AP 与最佳落脚格。

    参数:
        step_row: 以自身为源的步距离行（可含占位软墙）。
        attack_pos_mask: 可攻击该目标的落脚格掩码（已过滤占用 / 含自身位）。
        cur_cell: 当前所在格。
        mp: 一次移动行动的移动力（步数）。

    返回:
        (最少 AP, 最佳落脚格)；不可达时 AP 为大数、格为 -1。
    """
    best_ap = UNREACHABLE
    best_cell = -1
    m = attack_pos_mask
    while m:
        low = m & -m
        c = low.bit_length() - 1
        m ^= low
        step = 0 if c == cur_cell else step_row[c]
        if step >= UNREACHABLE:
            continue
        # 一次移动行动可连续走 mp 步 → ceil(step/mp) 对纯移动是精确 AP
        ap = (step + mp - 1) // mp
        if ap < best_ap or (ap == best_ap and c < best_cell):
            best_ap = ap
            best_cell = c
    return best_ap, best_cell


def soft_blocked_mask(state: Any, slot: int) -> int:
    """
    本单位规划用的软阻挡掩码：信念墙 ∪ 其它存活单位占位。

    不含自身格；可破障碍仍按乐观口径可通行（撞上由决策改打障）。

    参数:
        state: ``BattleState``。
        slot: 规划中的单位槽位。

    返回:
        不可踏入格的位掩码。
    """
    can_fly = state.can_fly[slot]
    occupied_others = state.occupied_mask() & ~(1 << state.cell[slot])
    return int(state.terrain.wall_mask(can_fly)) | occupied_others


def local_bfs(src: int, blocked_mask: int) -> tuple[list[int], list[int]]:
    """
    单源四邻接 BFS（占位软墙 / 局部绕行用，不碰全源地形缓存）。

    参数:
        src: 源格扁平索引。
        blocked_mask: 不可进入格掩码（源格即使置位仍可作为起点）。

    返回:
        (dist, parent)：长度 49；不可达 dist=UNREACHABLE、parent=-1。
    """
    dist = [UNREACHABLE] * CELL_COUNT
    parent = [-1] * CELL_COUNT
    dist[src] = 0
    queue: deque[int] = deque([src])
    while queue:
        cur = queue.popleft()
        for nxt in ORTHO_NEIGHBORS[cur]:
            if dist[nxt] != UNREACHABLE:
                continue
            # 其它单位 / 硬墙不可进入；源格已处理
            if (blocked_mask >> nxt) & 1:
                continue
            dist[nxt] = dist[cur] + 1
            parent[nxt] = cur
            queue.append(nxt)
    return dist, parent


def first_step_along_parents(src: int, goal: int, parent: list[int], dist: list[int]) -> int:
    """
    从 parent 指针回溯，得到 src → goal 路径上的首步格。

    参数:
        src: 起点。
        goal: 终点。
        parent: ``local_bfs`` 父指针。
        dist: ``local_bfs`` 距离。

    返回:
        首步格；不可达或已在终点时为 -1。
    """
    if goal < 0 or goal == src or dist[goal] >= UNREACHABLE:
        return -1
    cell = goal
    # 沿父指针走回 src 的子节点
    while parent[cell] != src and parent[cell] >= 0:
        cell = parent[cell]
    if parent[cell] != src:
        return -1
    return cell


def _enemy_slots(state: Any, side: int) -> list[int]:
    """存活敌方槽位列表。"""
    return [
        i
        for i in range(state.count)
        if state.alive[i] and state.side[i] != side
    ]


def _standable_mask(state: Any, slot: int) -> int:
    """可落脚掩码：非墙、非深渊、非他人占用（自身格可保留）。"""
    can_fly = state.can_fly[slot]
    occupied = state.occupied_mask()
    cur = state.cell[slot]
    return (
        FULL_MASK
        & ~state.terrain.wall_mask(can_fly)
        & ~state.terrain.abyss_mask()
        & ~(occupied & ~(1 << cur))
    )


def _filter_ranged_attack_pos(
    pos_mask: int,
    target_cell: int,
    los_block: int,
) -> int:
    """远程：去掉对目标无视线的落脚格。"""
    filtered = 0
    m = pos_mask
    while m:
        low = m & -m
        c = low.bit_length() - 1
        m ^= low
        if not ranged_attack_blocked(c, target_cell, los_block):
            filtered |= low
    return filtered


def _best_goal_for_unit(
    state: Any,
    slot: int,
    step_row: list[int],
    standable: int,
    enemy_slots: list[int],
    los_block: int,
) -> tuple[int, int, int, str | None]:
    """
    在给定步距行上为单位选最佳攻击落脚目标。

    返回:
        (best_ap, best_goal, chebyshev_to_enemy, enemy_uid)；无目标时 ap=UNREACHABLE。
    """
    cur = state.cell[slot]
    is_melee = state.is_melee[slot]
    attack_range = state.attack_range[slot]
    mp = state.mp[slot]
    best_key: tuple[int, int, int, str] | None = None
    best_goal = -1
    best_ap = UNREACHABLE
    for i in enemy_slots:
        t_cell = state.cell[i]
        pos_mask = attack_reach_mask(t_cell, is_melee, attack_range) & standable
        if not is_melee:
            pos_mask = _filter_ranged_attack_pos(pos_mask, t_cell, los_block)
        ap, goal = _approach_ap(step_row, pos_mask, cur, mp)
        if ap >= UNREACHABLE:
            continue
        ap_per_turn = state.ap_per_turn
        key = (
            (ap + ap_per_turn - 1) // ap_per_turn,
            ap,
            CHEBYSHEV_ROW[cur][t_cell],
            state.uid[i],
        )
        if best_key is None or key < best_key:
            best_key = key
            best_goal = goal
            best_ap = ap
    enemy_uid = best_key[3] if best_key is not None else None
    cheb = best_key[2] if best_key is not None else UNREACHABLE
    return best_ap, best_goal, cheb, enemy_uid


def _terrain_greedy_path_cells(state: Any, slot: int, goal: int) -> list[int]:
    """
    沿全源地形距离表贪心走出的路径格序列（含起点，不含对单位的回避）。

    用于判定「友军是否挡在地形最短路上」。步数上限 49，防环。
    """
    if goal < 0:
        return []
    can_fly = state.can_fly[slot]
    goal_rows = state.dist.rows(state.terrain, can_fly)[goal]
    cur = state.cell[slot]
    path = [cur]
    for _ in range(CELL_COUNT):
        if cur == goal:
            break
        cur_dist = goal_rows[cur]
        nxt = -1
        for n in ORTHO_NEIGHBORS[cur]:
            if goal_rows[n] < cur_dist:
                nxt = n
                break
        if nxt < 0:
            break
        cur = nxt
        path.append(cur)
    return path


def _can_attack_from(
    state: Any,
    slot: int,
    from_cell: int,
    enemy_slots: list[int],
    los_block: int,
) -> bool:
    """从指定格是否至少能打到一名存活敌人。"""
    is_melee = state.is_melee[slot]
    attack_range = state.attack_range[slot]
    reach = attack_reach_mask(from_cell, is_melee, attack_range)
    for i in enemy_slots:
        t_cell = state.cell[i]
        if not (reach >> t_cell) & 1:
            continue
        if not is_melee and ranged_attack_blocked(from_cell, t_cell, los_block):
            continue
        return True
    return False


def _ally_needs_blocker_to_yield(state: Any, ally_slot: int, blocker_cell: int) -> bool:
    """
    友军是否因 blocker_cell 上的同侧单位而无法软墙抵达攻击位，
    且其地形贪心路径确实经过该格（需要让路而非无关侧移）。
    """
    side = state.side[ally_slot]
    enemy_slots = _enemy_slots(state, side)
    if not enemy_slots:
        return False
    ally_kind = str(state.attack_kind[ally_slot])
    los_block = los_block_mask(state.terrain, ally_kind)
    standable = _standable_mask(state, ally_slot)
    soft = soft_blocked_mask(state, ally_slot)
    soft_dist, _ = local_bfs(state.cell[ally_slot], soft)
    soft_ap, soft_goal, _, _ = _best_goal_for_unit(
        state, ally_slot, soft_dist, standable, enemy_slots, los_block,
    )
    # 软墙已能绕到攻击位 → 不需要别人让路
    if soft_ap < UNREACHABLE and soft_goal >= 0:
        return False
    # 地形表仍可达：说明是单位堵路而非地形不通
    terrain_row = state.dist.rows(state.terrain, state.can_fly[ally_slot])[state.cell[ally_slot]]
    terrain_ap, terrain_goal, _, _ = _best_goal_for_unit(
        state, ally_slot, terrain_row, standable, enemy_slots, los_block,
    )
    if terrain_ap >= UNREACHABLE or terrain_goal < 0:
        return False
    path_cells = _terrain_greedy_path_cells(state, ally_slot, terrain_goal)
    return blocker_cell in path_cells[1:]  # 不含友军自身起点


def pick_yield_cell(state: Any, slot: int) -> int:
    """
    若本单位挡在同侧友军的地形必经路上，且友军无法软墙绕行，选一个侧移格让路。

    规则:
        - 仅对「身后」友军让路：友军地形 approach_ap 严格大于自己（自己更靠前）。
        - 优先仍能攻击敌人的邻格；否则任意可站邻格。
        - 不踏入占用 / 墙 / 深渊 / 信念可破障碍。

    返回:
        让路目标格；无需让路时 -1。
    """
    my_cell = state.cell[slot]
    side = state.side[slot]
    enemy_slots = _enemy_slots(state, side)
    if not enemy_slots:
        return -1
    my_kind = str(state.attack_kind[slot])
    los_block = los_block_mask(state.terrain, my_kind)
    standable = _standable_mask(state, slot)
    my_terrain_row = state.dist.rows(state.terrain, state.can_fly[slot])[my_cell]
    my_ap, _, _, _ = _best_goal_for_unit(
        state, slot, my_terrain_row, standable, enemy_slots, los_block,
    )

    needs_yield = False
    for i in range(state.count):
        if not state.alive[i] or state.side[i] != side or i == slot:
            continue
        ally_stand = _standable_mask(state, i)
        ally_row = state.dist.rows(state.terrain, state.can_fly[i])[state.cell[i]]
        ally_ap, _, _, _ = _best_goal_for_unit(
            state, i, ally_row, ally_stand, enemy_slots, los_block,
        )
        # 只为更靠后的友军让路，避免两人互相侧移死锁
        if ally_ap <= my_ap:
            continue
        if _ally_needs_blocker_to_yield(state, i, my_cell):
            needs_yield = True
            break
    if not needs_yield:
        return -1

    occupied = state.occupied_mask()
    can_fly = state.can_fly[slot]
    hard = int(state.terrain.wall_mask(can_fly)) | int(state.terrain.abyss_mask())
    breakable = int(state.terrain.breakable_mask())
    candidates: list[int] = []
    for n in ORTHO_NEIGHBORS[my_cell]:
        if (occupied >> n) & 1:
            continue
        if (hard >> n) & 1:
            continue
        if (breakable >> n) & 1:
            continue
        candidates.append(n)
    if not candidates:
        return -1
    # 优先：让路后仍能打到人
    keep_attack = [c for c in candidates if _can_attack_from(state, slot, c, enemy_slots, los_block)]
    pool = keep_attack if keep_attack else candidates
    return min(pool)


def next_step_toward_goal(state: Any, slot: int, goal: int) -> int:
    """
    朝 goal 的下一步：跳过占用格；贪心降距失败则局部 BFS 绕行。

    供决策首步与执行层共用，保证「规划能走的执行也能走」。

    参数:
        state: 战斗态。
        slot: 移动单位。
        goal: 目标落脚格。

    返回:
        下一格；无路时 -1。
    """
    cur = state.cell[slot]
    if goal < 0 or goal == cur:
        return -1
    blocked = soft_blocked_mask(state, slot)
    # 1) 优先：空闲且使「软墙距离」严格下降的邻格（邻接序确定）
    soft_dist, soft_parent = local_bfs(cur, blocked)
    if soft_dist[goal] < UNREACHABLE:
        step = first_step_along_parents(cur, goal, soft_parent, soft_dist)
        if step >= 0:
            return step
    # 2) 软墙不可达时：仍尝试地形贪心但跳过占用（给执行层一个不撞人的局部步）
    can_fly = state.can_fly[slot]
    goal_rows = state.dist.rows(state.terrain, can_fly)[goal]
    cur_dist = goal_rows[cur]
    for n in ORTHO_NEIGHBORS[cur]:
        if goal_rows[n] >= cur_dist:
            continue
        if state.slot_at(n) >= 0:
            continue
        return n
    return -1


def decide_action(state: Any, slot: int) -> tuple[int, int]:
    """
    为一个单位决策一次原子动作（恰好消耗 1 AP）。

    参数:
        state: ``BattleState``（见 autochess.py）。
        slot: 单位槽位索引。

    返回:
        (动作类型, 载荷)：攻击单位 → 目标槽位；攻击障碍 → 障碍格；
        移动 → 目标落脚格；发呆 → -1。
    """
    cur = state.cell[slot]
    side = state.side[slot]
    is_melee = state.is_melee[slot]
    attack_range = state.attack_range[slot]
    can_fly = state.can_fly[slot]

    # --- 1) 嘲讽短路：强制目标优先于自由选敌（M3-D06） ---------------
    forced = int(state.taunt_target[slot]) if slot < len(state.taunt_target) else -1
    if forced >= 0 and (
        forced >= state.count
        or not state.alive[forced]
        or state.side[forced] == side
    ):
        state.taunt_target[slot] = -1
        forced = -1
    if forced >= 0:
        enemy_slots = [forced]
    else:
        enemy_slots = _enemy_slots(state, side)
    if not enemy_slots:
        return ACT_IDLE, -1

    attack_kind = str(state.attack_kind[slot])
    los_block = los_block_mask(state.terrain, attack_kind)

    # --- 友军拥堵让路：有效嘲讽时跳过（避免为接近其他敌人而侧移） -----
    if forced < 0:
        yield_cell = pick_yield_cell(state, slot)
        if yield_cell >= 0:
            return ACT_MOVE, yield_cell

    # --- 快速路径：当前站位就能打到人 ---------------------------------
    reach = attack_reach_mask(cur, is_melee, attack_range)
    enemy_mask = 0
    for i in enemy_slots:
        enemy_mask |= 1 << state.cell[i]
    if reach & enemy_mask:
        best_target = -1
        best_key: tuple[int, str] | None = None
        for i in enemy_slots:
            t_cell = state.cell[i]
            if not (reach >> t_cell) & 1:
                continue
            if not is_melee and ranged_attack_blocked(cur, t_cell, los_block):
                continue
            key = (CHEBYSHEV_ROW[cur][t_cell], state.uid[i])
            if best_key is None or key < best_key:
                best_key = key
                best_target = i
        if best_target >= 0:
            return ACT_ATTACK_UNIT, best_target

    # --- 选目标：占位软墙局部 BFS 打分（绕开友军/敌军占格） -------------
    standable = _standable_mask(state, slot)
    soft = soft_blocked_mask(state, slot)
    soft_dist, soft_parent = local_bfs(cur, soft)
    best_ap, best_goal, _, _ = _best_goal_for_unit(
        state, slot, soft_dist, standable, enemy_slots, los_block,
    )

    # 软墙全堵死时回退地形表（仍可能靠后续友军让路打通）
    if best_goal < 0 or best_ap >= UNREACHABLE:
        terrain_row = state.dist.rows(state.terrain, can_fly)[cur]
        best_ap, best_goal, _, _ = _best_goal_for_unit(
            state, slot, terrain_row, standable, enemy_slots, los_block,
        )

    if best_goal < 0 or best_goal == cur:
        return ACT_IDLE, -1

    # --- 求首步：软墙路径首格；遇可破障碍改打障 -------------------------
    # 若目标来自地形回退，软墙 parent 可能到不了 → 统一走 next_step
    first_step = first_step_along_parents(cur, best_goal, soft_parent, soft_dist)
    if first_step < 0:
        first_step = next_step_toward_goal(state, slot, best_goal)
    if first_step < 0:
        # 无空闲可迈步（等友军让路），避免反复 move+blocked_unit 空耗 AP
        return ACT_IDLE, -1

    breakable = state.terrain.breakable_mask()
    if (breakable >> first_step) & 1:
        return ACT_ATTACK_OBSTACLE, first_step
    return ACT_MOVE, best_goal
