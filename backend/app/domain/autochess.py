"""
自走棋战斗引擎（M3战斗成型设计.md §7 / §12 · M3自动移动攻击算法设计.md）。

对外唯一入口 ``simulate_battle(setup, seed)``：
    - 纯 CPU 函数：无 DB / 无网络 / 无 asyncio / 无模块级可变状态；
    - 入参与返回值均为可 JSON 序列化的原始数据；
    - 同一 ``setup + seed`` 必然产出逐事件一致的结果（确定性纪律见算法文档 §9）。

引擎无条件全量记录结构化事件；``simple`` / ``detailed`` 只是渲染档位
（见 battle_text.py），不是引擎分支。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

import random
from typing import Any

from app.domain.board_tables import ORTHO_NEIGHBORS, cell_of, mirror_x, x_of, y_of
from app.domain.combat_ai import (
    ACT_ATTACK_OBSTACLE,
    ACT_ATTACK_UNIT,
    ACT_IDLE,
    ACT_MOVE,
    decide_action,
    next_step_toward_goal,
)
from app.domain.formation_rules import (
    effect_multipliers_for_side,
    resolve_battlefield,
)
from app.domain.layer_payloads import (
    apply_side_combat_to_state,
    damage_mul_for_attack_kind,
    default_side_combat,
    enrich_battlefield_layer_events,
    hit_rate_with_combat,
)
from app.domain.formation_blueprint import (
    apply_force_shifts_to_state,
    blocking_terrain_flat_cells,
)
from app.domain.line_of_sight import los_block_source
from app.domain.taunt_aura import (
    clear_taunts_pointing_to,
    rebuild_taunt_auras,
    try_apply_taunt_on_enter,
)
from app.domain.terrain import TERRAIN_SEAL, TerrainDistance, TerrainState

# 战报结构版本（与 M1 rounds[] 不兼容）
SCHEMA_VERSION = 1


class BattleState:
    """
    战斗运行态（SoA 布局：槽位索引访问各属性数组）。

    属性数组下标即槽位 slot（0..count-1）；``terrain`` / ``dist`` 为地形
    信念与懒重建距离表。本类仅存在于单次 ``simulate_battle`` 调用栈上。
    """

    __slots__ = (
        "count", "uid", "kind", "name", "side", "cell", "hp", "max_hp",
        "atk", "speed", "mp", "can_fly", "attack_range", "attack_kind",
        "is_melee", "alive", "terrain", "dist", "ap_per_turn",
        "hit_rates", "damage_floor", "damage_dice_normalizer", "dice_sides",
        "dice_lo", "dice_hi", "use_midpoint_normalizer",
        # M3-D06 嘲讽光环运行态
        "taunt_target", "taunt_aura", "taunt_aura_mask", "aura_owner",
        # M3-D07 环境/天气 combat 乘区（按侧）
        "side_combat",
    )

    def __init__(self) -> None:
        self.count = 0
        self.uid: list[str] = []
        self.kind: list[str] = []
        self.name: list[str] = []
        self.side: list[int] = []
        self.cell: list[int] = []
        self.hp: list[int] = []
        self.max_hp: list[int] = []
        self.atk: list[int] = []
        self.speed: list[int] = []
        self.mp: list[int] = []
        self.can_fly: list[bool] = []
        self.attack_range: list[int] = []
        self.attack_kind: list[str] = []
        self.is_melee: list[bool] = []
        self.alive: list[bool] = []
        self.terrain: TerrainState | None = None
        self.dist: TerrainDistance | None = None
        self.ap_per_turn = 2
        self.hit_rates: dict[str, float] = {}
        self.damage_floor = 0
        self.damage_dice_normalizer = 10.0
        self.dice_sides = 20
        # 每单位修为区间骰上下限（缺省回落 1..dice_sides）
        self.dice_lo: list[int] = []
        self.dice_hi: list[int] = []
        self.use_midpoint_normalizer = True
        # 嘲讽：每槽强制目标（slot 或 -1）；光环快照；按侧掩码；格→嘲讽者
        self.taunt_target: list[int] = []
        self.taunt_aura: list[dict[str, Any] | None] = []
        self.taunt_aura_mask: list[int] = [0, 0]
        self.aura_owner: list[int] = []
        # 侧 → 环境/天气 combat 合并乘区
        self.side_combat: list[dict[str, float]] = [
            default_side_combat(),
            default_side_combat(),
        ]

    def occupied_mask(self) -> int:
        """所有存活单位的占位掩码。"""
        mask = 0
        for i in range(self.count):
            if self.alive[i]:
                mask |= 1 << self.cell[i]
        return mask

    def side_alive(self, side: int) -> bool:
        """某一侧是否仍有存活单位。"""
        return any(self.alive[i] and self.side[i] == side for i in range(self.count))

    def slot_at(self, cell: int) -> int:
        """查某格上的存活单位槽位；无则 -1。"""
        for i in range(self.count):
            if self.alive[i] and self.cell[i] == cell:
                return i
        return -1


def _coord(cell: int) -> dict[str, int]:
    """扁平索引 → ``{x, y}``（事件里统一用坐标对象，便于前端消费）。"""
    return {"x": x_of(cell), "y": y_of(cell)}


def _unit_dice_range(state: BattleState, slot: int) -> tuple[int, int]:
    """
    取单位修为骰区间；缺省回落 ``1..dice_sides``。

    参数:
        state: 战斗态。
        slot: 单位槽位。

    返回:
        (lo, hi)。
    """
    lo = int(state.dice_lo[slot]) if slot < len(state.dice_lo) else 1
    hi = int(state.dice_hi[slot]) if slot < len(state.dice_hi) else int(state.dice_sides)
    if lo < 1:
        lo = 1
    if hi < lo:
        hi = lo
    return lo, hi


def _roll_unit_dice(state: BattleState, slot: int, rng: random.Random) -> int:
    """按单位区间掷一骰。"""
    lo, hi = _unit_dice_range(state, slot)
    return int(rng.randint(lo, hi))


def _build_terrain_cells(setup: dict[str, Any]) -> list[dict[str, Any]]:
    """
    汇总双方阵法地形为扁平格列表。

    进攻方地形按原坐标写入；防守方地形做 x 镜像（配置一律按进攻方视角书写）。
    """
    cells: list[dict[str, Any]] = []
    for side_key, mirrored in (("attacker_formation", False), ("defender_formation", True)):
        formation = setup.get(side_key) or {}
        for item in formation.get("terrain") or []:
            x = int(item["x"])
            y = int(item["y"])
            if mirrored:
                x = mirror_x(x)
            cells.append(
                {
                    "cell": cell_of(x, y),
                    "type": str(item["type"]),
                    "subtype": str(item.get("subtype", "")),
                    "owner_side": 1 if mirrored else 0,
                },
            )
    return cells


def _build_state(
    setup: dict[str, Any],
    layer_results: list[dict[str, Any]],
) -> BattleState:
    """根据 setup 与四象结算结果构建战斗运行态（套用效果层与环境/天气载荷）。"""
    board = setup["board"]
    state = BattleState()
    state.ap_per_turn = int(board.get("ap_per_turn", 2))
    state.hit_rates = dict(board.get("hit_rates") or {})
    state.damage_floor = int(board.get("damage_floor", 0))
    state.damage_dice_normalizer = float(board.get("damage_dice_normalizer", 10.0))
    state.dice_sides = int(board.get("dice_sides", 20))
    state.use_midpoint_normalizer = bool(board.get("use_midpoint_normalizer", True))
    land_mp = int(board.get("land_move_points", 2))
    fly_mp = int(board.get("fly_move_points", 4))
    catalogs = setup.get("layer_catalogs") or {}

    # 按侧预计算环境+天气 combat（命中/伤害用；效果层仍改面板）
    apply_side_combat_to_state(state, layer_results, catalogs)

    for unit in setup["units"]:
        side = int(unit["side"])
        atk_mul, hp_mul = effect_multipliers_for_side(
            layer_results,
            setup.get("attacker_formation"),
            setup.get("defender_formation"),
            side,
        )
        can_fly = bool(unit.get("can_fly", False))
        attack_kind = str(unit.get("attack_kind", "melee_physical"))
        hp_value = max(1, int(int(unit["hp"]) * hp_mul))
        state.uid.append(str(unit["uid"]))
        state.kind.append(str(unit.get("kind", "main")))
        state.name.append(str(unit.get("name", unit["uid"])))
        state.side.append(side)
        state.cell.append(cell_of(int(unit["x"]), int(unit["y"])))
        state.hp.append(hp_value)
        state.max_hp.append(hp_value)
        state.atk.append(max(1, int(int(unit["atk"]) * atk_mul)))
        state.speed.append(int(unit.get("speed", 5)))
        state.mp.append(fly_mp if can_fly else land_mp)
        state.can_fly.append(can_fly)
        state.attack_range.append(int(unit.get("attack_range", 1)))
        state.attack_kind.append(attack_kind)
        state.is_melee.append(attack_kind.startswith("melee"))
        state.alive.append(True)
        # 修为区间骰；未带则回落 1..dice_sides
        d_lo = int(unit.get("dice_lo", 1))
        d_hi = int(unit.get("dice_hi", state.dice_sides))
        if d_hi < d_lo:
            d_hi = d_lo
        state.dice_lo.append(d_lo)
        state.dice_hi.append(d_hi)
        # 嘲讽光环快照：服务端组 setup 时已解析；测试可直接塞 dict
        aura_snap = unit.get("taunt_aura")
        state.taunt_aura.append(dict(aura_snap) if isinstance(aura_snap, dict) else None)
        state.taunt_target.append(-1)
        state.count += 1

    state.terrain = TerrainState(_build_terrain_cells(setup))
    state.dist = TerrainDistance()
    return state


def _build_turn_order(
    state: BattleState,
    rng: random.Random,
    events: list[dict[str, Any]],
    round_no: int,
) -> tuple[list[int], dict[int, dict[str, Any]]]:
    """
    掷先攻并生成本回合行动序（§7.1）。

    - ``initiative = speed × cultivation_dice``，每个大回合重掷；
    - 点数不同：高者先动；
    - 平票桶内双方交错：一方动完后若另一方仍有同点单位，下一动必须换边；
      某方清空后另一方连续清完（swap-pop 保证 O(1) 且顺序确定）。

    先攻掷骰结果**不**在此处写入 events（避免开局连刷三条先攻动画）；
    由回合循环在「该单位行动前」按序追加，日志形态为：先攻 → 行动。

    返回:
        tuple: (行动槽序, slot → 先攻事件载荷)。
    """
    rolls: list[tuple[int, int]] = []  # (initiative, slot)
    initiative_by_slot: dict[int, dict[str, Any]] = {}
    for i in range(state.count):
        if not state.alive[i]:
            continue
        lo, hi = _unit_dice_range(state, i)
        dice = _roll_unit_dice(state, i, rng)
        initiative = state.speed[i] * dice
        rolls.append((initiative, i))
        # 仅缓存；事件在该单位真正行动前再 append
        initiative_by_slot[i] = {
            "type": "initiative",
            "round": round_no,
            "uid": state.uid[i],
            "speed": state.speed[i],
            "dice": dice,
            "dice_lo": lo,
            "dice_hi": hi,
            "initiative": initiative,
        }

    # 按 initiative 从高到低分桶
    buckets: dict[int, list[int]] = {}
    for initiative, slot in rolls:
        buckets.setdefault(initiative, []).append(slot)

    order: list[int] = []
    for initiative in sorted(buckets.keys(), reverse=True):
        bucket = buckets[initiative]
        if len(bucket) == 1:
            order.append(bucket[0])
            continue
        # 平票桶：按侧拆分后强制交错
        by_side: list[list[int]] = [[], []]
        for slot in bucket:
            by_side[state.side[slot]].append(slot)
        last_side = -1
        while by_side[0] or by_side[1]:
            if last_side == -1:
                # 桶首动：双方都有人时用 seed 随机定边，否则取有人的一边
                if by_side[0] and by_side[1]:
                    side = rng.randint(0, 1)
                else:
                    side = 0 if by_side[0] else 1
            elif by_side[1 - last_side]:
                side = 1 - last_side  # 强制换边
            else:
                side = last_side  # 对方已空，本方连续清完
            pool = by_side[side]
            pick_idx = rng.randrange(len(pool))
            pool[pick_idx], pool[-1] = pool[-1], pool[pick_idx]  # swap-pop
            order.append(pool.pop())
            last_side = side

    events.append(
        {
            "type": "turn_order",
            "round": round_no,
            "order": [state.uid[slot] for slot in order],
        },
    )
    return order, initiative_by_slot

def _resolve_attack_on_unit(
    state: BattleState,
    attacker: int,
    target: int,
    rng: random.Random,
    events: list[dict[str, Any]],
) -> None:
    """
    结算一次对单位的攻击行动（命中 §7.3.3 → 伤害 §7.3.2）。

    命中/伤害乘区经 ``layer_payloads`` 钩子，与对抗结算解耦。
    """
    attack_kind = state.attack_kind[attacker]
    combat = state.side_combat[state.side[attacker]]
    table_rate = float(state.hit_rates.get(attack_kind, 0.9))
    base_rate = hit_rate_with_combat(
        table_rate,
        is_melee=state.is_melee[attacker],
        combat=combat,
    )
    extra_rate = 0.0  # 额外命中率（装备 / 功法后置）
    dodge_rate = 0.0  # 闪避几率（体质 / 功法后置）
    hit_chance = min(1.0, max(0.0, base_rate + extra_rate - dodge_rate))
    hit_roll = rng.randint(1, 100)
    hit = hit_roll <= round(hit_chance * 100)
    events.append(
        {
            "type": "hit_check",
            "attacker": state.uid[attacker],
            "target": state.uid[target],
            "attack_kind": attack_kind,
            "base_rate": base_rate,
            "extra_rate": extra_rate,
            "dodge_rate": dodge_rate,
            "ranged_hit_mul": float(combat.get("ranged_hit_mul", 1.0)),
            "chance": hit_chance,
            "dice": hit_roll,
            "forced": "none",  # 必中/必闪钩子（M3-D03 后接内容）
            "hit": hit,
        },
    )
    if not hit:
        return

    power = state.atk[attacker]
    counter_atk = 1.0  # 攻方克制系数（五行/道表后置）
    counter_def = 1.0  # 守方克制系数
    defense = 0  # 防御属性（M3 单位面板暂无防御，字段保留）
    lo, hi = _unit_dice_range(state, attacker)
    damage_dice = _roll_unit_dice(state, attacker, rng)
    if state.use_midpoint_normalizer:
        mid = max(1.0, (lo + hi) / 2.0)
        dice_factor = damage_dice / mid
    else:
        dice_factor = damage_dice / max(1.0, float(state.damage_dice_normalizer))
    damage_mul = damage_mul_for_attack_kind(attack_kind, combat)
    raw = power * counter_atk * dice_factor * damage_mul
    final = max(state.damage_floor, int(round(raw - defense * counter_def)))
    hp_before = state.hp[target]
    hp_after = max(0, hp_before - final)
    state.hp[target] = hp_after
    events.append(
        {
            "type": "damage",
            "attacker": state.uid[attacker],
            "target": state.uid[target],
            "power": power,
            "c_atk": counter_atk,
            "dice": damage_dice,
            "dice_lo": lo,
            "dice_hi": hi,
            "dice_factor": round(dice_factor, 4),
            "damage_mul": round(damage_mul, 4),
            "defense": defense,
            "c_def": counter_def,
            "raw": round(raw, 2),
            "final": final,
            "hp_before": hp_before,
            "hp_after": hp_after,
        },
    )
    if hp_after <= 0:
        state.alive[target] = False
        events.append({"type": "death", "uid": state.uid[target]})
        # 嘲讽者阵亡 → 清除指向它的强制目标并重建光环掩码
        clear_taunts_pointing_to(state, target)


def _execute_move(
    state: BattleState,
    slot: int,
    goal: int,
    events: list[dict[str, Any]],
) -> None:
    """
    执行一次移动行动：沿占位感知路径最多走 ``mp`` 步，逐格揭晓地形（§7 执行层）。

    选步口径与 ``combat_ai.next_step_toward_goal`` 一致：其它单位为软墙，
    优先绕行；仍无空闲降距邻格时才 ``blocked_unit`` / ``blocked_terrain``。

    停止原因:
        arrived / budget / blocked_unit / blocked_terrain / abyss_bounce / taunt。
    深渊约束：踏入前剩余步数须 ≥ 2；禁飞 → 弹回上一格并升地形版本；
    移动结束时不变式：所在格必不是深渊。
    """
    can_fly = state.can_fly[slot]
    budget = state.mp[slot]
    cur = state.cell[slot]
    path: list[dict[str, int]] = [_coord(cur)]
    stop_reason = "budget"
    abyss = state.terrain.abyss_mask()
    breakable = state.terrain.breakable_mask()
    # 嘲讽者自己移动时需要更新光环；普通单位只检测进入
    mover_has_aura = state.taunt_aura[slot] is not None

    prev_solid = cur  # 最近一个「非深渊」落脚格（弹回目标）
    while budget > 0:
        if cur == goal:
            stop_reason = "arrived"
            break
        # 与决策层共用：跳过占用，必要时局部 BFS 绕行
        # 注意：临时把 cell 写回 state，供 next_step 读当前位置
        state.cell[slot] = cur
        next_cell = next_step_toward_goal(state, slot, goal)
        if next_cell < 0:
            # 区分：邻格全被单位堵住 vs 地形不通
            stop_reason = "blocked_unit"
            for n in ORTHO_NEIGHBORS[cur]:
                if state.slot_at(n) < 0:
                    stop_reason = "blocked_terrain"
                    break
            break
        # 防御：若仍选到占用格（并发占位），停步等下个 AP 重规划 / 让路
        if state.slot_at(next_cell) >= 0:
            stop_reason = "blocked_unit"
            break
        # 撞上（信念可破的）障碍 → 停止移动，下个 AP 由决策层改为打障
        if (breakable >> next_cell) & 1:
            stop_reason = "blocked_terrain"
            break
        # 深渊格处理
        if (abyss >> next_cell) & 1:
            if budget < 2:
                # 踏入后必须还能再走 1 步离开 → 步数不足不得踏入
                stop_reason = "budget"
                break
            subtype = state.terrain.reveal_ravine(next_cell)
            if subtype == "no_fly" or not can_fly:
                # 禁飞（或单位不会飞）→ 弹回上一格
                events.append(
                    {
                        "type": "abyss_bounce",
                        "uid": state.uid[slot],
                        "cell": _coord(next_cell),
                        "back_to": _coord(prev_solid),
                    },
                )
                stop_reason = "abyss_bounce"
                cur = prev_solid
                break
            events.append(
                {
                    "type": "abyss_pass",
                    "uid": state.uid[slot],
                    "cell": _coord(next_cell),
                },
            )
            cur = next_cell
            budget -= 1
            path.append(_coord(cur))
            # 不可停留在深渊上：继续走（下一轮循环）；深渊格不判嘲讽
            continue
        cur = next_cell
        prev_solid = cur
        budget -= 1
        path.append(_coord(cur))
        # 嘲讽者移动 → 光环随人（进入检查前更新，避免踩到自己旧光环）
        if mover_has_aura:
            state.cell[slot] = cur
            rebuild_taunt_auras(state)
        # 踏入新格：敌方光环 → STOP_TAUNT
        if try_apply_taunt_on_enter(state, slot, cur, events):
            stop_reason = "taunt"
            break

    # 不变式：移动结束不得停在深渊上；若因步数耗尽悬停 → 弹回
    if (abyss >> cur) & 1:
        events.append(
            {
                "type": "abyss_bounce",
                "uid": state.uid[slot],
                "cell": _coord(cur),
                "back_to": _coord(prev_solid),
            },
        )
        cur = prev_solid
        stop_reason = "abyss_bounce"

    state.cell[slot] = cur
    # 非逐步更新路径下，嘲讽者最终落点仍须刷新掩码
    if mover_has_aura:
        rebuild_taunt_auras(state)
    events.append(
        {
            "type": "move",
            "uid": state.uid[slot],
            "path": path,
            "stop_reason": stop_reason,
        },
    )


def _unit_turn(
    state: BattleState,
    slot: int,
    rng: random.Random,
    events: list[dict[str, Any]],
) -> None:
    """执行一个单位的整个先攻行动回合（AP 循环，每个原子动作恰 1 AP）。"""
    ap = state.ap_per_turn
    while ap > 0 and state.alive[slot]:
        # 一方全灭立即停手
        if not state.side_alive(0) or not state.side_alive(1):
            return
        action, payload = decide_action(state, slot)
        if action == ACT_ATTACK_UNIT:
            # 远程执行前复核遮挡（决策已过滤，此处防御性复核保持权威）
            attack_kind = state.attack_kind[slot]
            block_src = None
            if not state.is_melee[slot]:
                block_src = los_block_source(
                    state.terrain,
                    state.cell[slot],
                    state.cell[payload],
                    attack_kind,
                )
            if block_src is not None:
                events.append(
                    {
                        "type": "blocked",
                        "uid": state.uid[slot],
                        "target": state.uid[payload],
                        "reason": "los_blocked",
                        "block_source": block_src,
                    },
                )
                ap -= 1
                continue
            _resolve_attack_on_unit(state, slot, payload, rng, events)
            ap -= 1
        elif action == ACT_ATTACK_OBSTACLE:
            # 打障碍：视为一次必中的攻击行动；揭晓可破 / 不可破
            result = state.terrain.hit_obstacle(payload)
            events.append(
                {
                    "type": "obstacle_hit",
                    "uid": state.uid[slot],
                    "cell": _coord(payload),
                    "result": result,  # break=击破 / immune=无法破坏
                },
            )
            ap -= 1
        elif action == ACT_MOVE:
            _execute_move(state, slot, payload, events)
            ap -= 1
        else:  # ACT_IDLE
            events.append(
                {
                    "type": "blocked",
                    "uid": state.uid[slot],
                    "reason": "no_reachable_target",
                },
            )
            return  # 无事可做，弃掉剩余 AP


def simulate_battle(setup: dict[str, Any], seed: int) -> dict[str, Any]:
    """
    演算一整场自走棋战斗（纯函数、可复现）。

    参数:
        setup: 开战配置（board / units / 双方阵法 / 克制表），全为原始数据。
        seed: 随机种子；同 setup + seed 结果逐事件一致。

    返回:
        dict: ``{schema_version, seed, winner, result, rounds, events}``；
        ``winner ∈ {attacker, defender}``；``result`` 为进攻方视角 win/lose。
    """
    rng = random.Random(seed)
    events: list[dict[str, Any]] = []
    board = setup["board"]
    dice_sides = int(board.get("dice_sides", 20))
    max_rounds = int(board.get("max_rounds", 30))
    timeout_winner = str(board.get("timeout_winner", "defender"))

    # 1) 四象对抗（S3 空阵时三层全为 none，结果自然为空）
    form_dice = setup.get("formation_dice") or {}
    layer_results = resolve_battlefield(
        setup.get("attacker_formation"),
        setup.get("defender_formation"),
        setup.get("counters") or {},
        rng,
        dice_sides,
        attacker_dice_lo=form_dice.get("attacker_lo"),
        attacker_dice_hi=form_dice.get("attacker_hi"),
        defender_dice_lo=form_dice.get("defender_lo"),
        defender_dice_hi=form_dice.get("defender_hi"),
    )
    for item in enrich_battlefield_layer_events(
        layer_results,
        setup.get("layer_catalogs"),
    ):
        events.append({"type": "battlefield_layer", **item})

    # 2) 构建运行态（含地形与效果乘区）
    state = _build_state(setup, layer_results)

    # 3) 开战强制移位（四象与效果乘区之后、回合前）
    terrain_items = _build_terrain_cells(setup)
    blocked_flat = blocking_terrain_flat_cells(terrain_items)
    atk_form = setup.get("attacker_formation") or {}
    def_form = setup.get("defender_formation") or {}
    shift_events = apply_force_shifts_to_state(
        state,
        attacker_shifts=atk_form.get("force_shifts"),
        defender_shifts=def_form.get("force_shifts"),
        blocked_cells=blocked_flat,
    )
    events.extend(shift_events)

    # 3b) 嘲讽光环掩码（移位后坐标为准）
    rebuild_taunt_auras(state)

    # 4) battle_start：初始棋子 / 可见地形（移位后坐标；不泄露可破 / 禁飞子类）
    events.insert(
        0,
        {
            "type": "battle_start",
            "seed": seed,
            "units": [
                {
                    "uid": state.uid[i],
                    "kind": state.kind[i],
                    "side": state.side[i],
                    "name": state.name[i],
                    **_coord(state.cell[i]),
                    "hp": state.hp[i],
                    "atk": state.atk[i],
                    "speed": state.speed[i],
                    "attack_range": state.attack_range[i],
                    "attack_kind": state.attack_kind[i],
                    "can_fly": state.can_fly[i],
                }
                for i in range(state.count)
            ],
            # 地形：障/渊开战前不泄露子类；禁制 Phase A 子类可见（M3-D07）
            "terrain": [
                {
                    **_coord(item["cell"]),
                    "kind": item["type"],
                    **(
                        {"subtype": item["subtype"]}
                        if item["type"] == TERRAIN_SEAL and item.get("subtype")
                        else {}
                    ),
                }
                for item in terrain_items
            ],
        },
    )

    # 5) 回合循环
    rounds_played = 0
    winner: str | None = None
    for round_no in range(1, max_rounds + 1):
        if not state.side_alive(0):
            winner = "defender"
            break
        if not state.side_alive(1):
            winner = "attacker"
            break
        rounds_played = round_no
        events.append({"type": "round_start", "round": round_no})
        # 先掷完本回合先攻并排序；事件按「先攻 → 该单位行动」交错写出，
        # 避免开局连刷全部【先攻】行再开播动画。
        order, initiative_by_slot = _build_turn_order(state, rng, events, round_no)
        for slot in order:
            if not state.alive[slot]:
                continue
            init_ev = initiative_by_slot.get(slot)
            if init_ev is not None:
                events.append(dict(init_ev))
            _unit_turn(state, slot, rng, events)
            if not state.side_alive(0) or not state.side_alive(1):
                break

    # 6) 胜负判定（含回合上限超时）
    if winner is None:
        if not state.side_alive(0):
            winner = "defender"
        elif not state.side_alive(1):
            winner = "attacker"
        else:
            winner = "attacker" if timeout_winner == "attacker" else "defender"

    events.append(
        {
            "type": "battle_end",
            "winner": winner,
            "rounds": rounds_played,
            "survivors": [
                {"uid": state.uid[i], "side": state.side[i], "hp": state.hp[i]}
                for i in range(state.count)
                if state.alive[i]
            ],
        },
    )

    # 7) 附加事件序号（seq 从 0 起，供前端播放器定位）
    for seq, event in enumerate(events):
        event["seq"] = seq

    return {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "winner": winner,
        "result": "win" if winner == "attacker" else "lose",
        "rounds": rounds_played,
        "events": events,
    }
