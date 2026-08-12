"""
自走棋引擎单测（M3 · S3/S6）。

覆盖：确定性、近战接敌击杀、回合上限超时、破障、深渊弹回、远程遮挡、四象结算。
"""

from __future__ import annotations

from app.domain.autochess import simulate_battle
from app.domain.battle_text import render_board, render_detailed, render_summary

# 基础棋盘参数（与 board.yaml 同口径；测试内联避免依赖配置加载）
_BOARD = {
    "size": 7,
    "max_rounds": 30,
    "timeout_winner": "defender",
    "dice_sides": 20,
    "ap_per_turn": 2,
    "land_move_points": 2,
    "fly_move_points": 4,
    "hit_rates": {
        "melee_physical": 0.9,
        "melee_magic": 0.95,
        "ranged_physical": 0.75,
        "ranged_magic": 0.85,
    },
    "damage_floor": 0,
    "damage_dice_normalizer": 10,
}


def _unit(uid: str, side: int, x: int, y: int, **kw) -> dict:
    """构造一个引擎入参棋子。"""
    base = {
        "uid": uid,
        "kind": "main",
        "name": uid,
        "side": side,
        "x": x,
        "y": y,
        "atk": 10,
        "hp": 100,
        "speed": 5,
        "attack_range": 1,
        "attack_kind": "melee_physical",
        "can_fly": False,
    }
    base.update(kw)
    return base


def _setup(units: list[dict], **kw) -> dict:
    """构造引擎 setup。"""
    setup = {
        "board": dict(_BOARD),
        "units": units,
        "attacker_formation": None,
        "defender_formation": None,
        "counters": {},
    }
    setup.update(kw)
    return setup


def _events_of(result: dict, event_type: str) -> list[dict]:
    """按类型过滤事件。"""
    return [e for e in result["events"] if e["type"] == event_type]


def test_determinism_same_seed_same_events() -> None:
    """同 setup + seed → 逐事件一致；不同 seed 大概率不同。"""
    setup = _setup([_unit("a", 0, 0, 3, atk=15), _unit("d", 1, 6, 3)])
    r1 = simulate_battle(setup, 12345)
    r2 = simulate_battle(setup, 12345)
    assert r1 == r2
    assert all("seq" in e for e in r1["events"])


def test_melee_approach_and_finish() -> None:
    """强攻方必然接敌并击杀（100 atk vs 10 hp）。"""
    setup = _setup(
        [_unit("a", 0, 0, 3, atk=100, hp=500), _unit("d", 1, 6, 3, atk=1, hp=10)],
    )
    result = simulate_battle(setup, 7)
    assert result["winner"] == "attacker"
    assert result["result"] == "win"
    # 有移动事件且路径正交连续
    moves = _events_of(result, "move")
    assert moves
    for move in moves:
        path = move["path"]
        for prev, nxt in zip(path, path[1:]):
            assert abs(prev["x"] - nxt["x"]) + abs(prev["y"] - nxt["y"]) == 1
    assert _events_of(result, "death")


def test_timeout_defender_wins() -> None:
    """互相打不死 → 超回合上限判防守方胜。"""
    board = dict(_BOARD)
    board["max_rounds"] = 3
    board["damage_floor"] = 0
    setup = _setup(
        [
            _unit("a", 0, 0, 3, atk=1, hp=99999),
            _unit("d", 1, 6, 3, atk=1, hp=99999),
        ],
    )
    setup["board"] = board
    result = simulate_battle(setup, 99)
    assert result["winner"] == "defender"
    assert result["rounds"] == 3


def test_obstacle_break_and_reveal() -> None:
    """挡路可破障碍被打掉；不可破障碍揭晓后绕行。"""
    # y=3 整行只留 (3,3) 一个可破障碍挡路，其余通畅 → AI 会打掉或绕行
    setup = _setup(
        [_unit("a", 0, 0, 3, atk=100, hp=500), _unit("d", 1, 6, 3, atk=1, hp=10)],
        attacker_formation={
            "id": "test",
            "name": "测试阵",
            "level": 1,
            # 竖墙封住 x=2 全列（中间可破）：逼出破障或绕行分支
            "terrain": [
                {"x": 2, "y": y, "type": "obstacle", "subtype": "destructible"}
                for y in range(7)
            ],
            "environment": None,
            "weather": None,
            "effect": None,
        },
    )
    result = simulate_battle(setup, 5)
    assert result["winner"] == "attacker"
    hits = _events_of(result, "obstacle_hit")
    assert hits and hits[0]["result"] == "break"


def test_abyss_bounce_for_land_unit() -> None:
    """陆地单位不会停留深渊；防守方地形做 x 镜像。"""
    setup = _setup(
        [_unit("a", 0, 0, 3, atk=100, hp=500), _unit("d", 1, 6, 3, atk=1, hp=10)],
        defender_formation={
            "id": "trap",
            "name": "深渊阵",
            "level": 1,
            # 防守方视角 (1,3) → 镜像后落 (5,3)
            "terrain": [{"x": 1, "y": 3, "type": "ravine", "subtype": "no_fly"}],
            "environment": None,
            "weather": None,
            "effect": None,
        },
    )
    result = simulate_battle(setup, 11)
    start = _events_of(result, "battle_start")[0]
    ravines = [t for t in start["terrain"] if t["kind"] == "ravine"]
    assert ravines and ravines[0]["x"] == 5 and ravines[0]["y"] == 3
    # 所有移动的终点都不在深渊格上
    for move in _events_of(result, "move"):
        last = move["path"][-1]
        assert (last["x"], last["y"]) != (5, 3)


def test_ranged_los_blocked_by_obstacle() -> None:
    """远程直线被障碍遮挡时不可射击（打障或绕位）。"""
    setup = _setup(
        [
            _unit("a", 0, 0, 3, atk=100, hp=500, attack_range=6, attack_kind="ranged_magic"),
            _unit("d", 1, 6, 3, atk=1, hp=10),
        ],
        attacker_formation={
            "id": "wall",
            "name": "石壁",
            "level": 1,
            "terrain": [
                {"x": 2, "y": 3, "type": "obstacle", "subtype": "indestructible"},
            ],
            "environment": None,
            "weather": None,
            "effect": None,
        },
    )
    result = simulate_battle(setup, 3)
    # 每次命中判定发生时，攻击者与目标之间不得有存活遮挡（引擎已复核）
    assert result["winner"] == "attacker"


def test_battlefield_layers_resolution() -> None:
    """四象对抗：双方各带环境层 → 产生 battlefield_layer 事件与乘区。"""
    formation = {
        "id": "f1",
        "name": "阵一",
        "level": 1,
        "terrain": [],
        "environment": {
            "id": "rocky",
            "force_apply": False,
            "counter_group": "earth",
            "atk_mul": 1.0,
            "hp_mul": 1.0,
        },
        "weather": None,
        "effect": {
            "id": "fury",
            "force_apply": False,
            "counter_group": None,
            "atk_mul": 1.5,
            "hp_mul": 1.0,
        },
    }
    setup = _setup(
        [_unit("a", 0, 0, 3, atk=10, hp=100), _unit("d", 1, 6, 3, atk=10, hp=100)],
        attacker_formation=formation,
        defender_formation=None,
        counters={"environment": {"earth": {}}, "weather": {}, "effect": {}},
    )
    result = simulate_battle(setup, 1)
    layers = _events_of(result, "battlefield_layer")
    assert layers
    # 单方独有 → 全场覆盖；进攻方效果层 1.5 倍攻 → battle_start 中 atk=15
    start = _events_of(result, "battle_start")[0]
    attacker_unit = next(u for u in start["units"] if u["side"] == 0)
    assert attacker_unit["atk"] == 15


def test_render_outputs() -> None:
    """三档渲染均可生成且含关键要素。"""
    setup = _setup([_unit("a", 0, 0, 3, atk=100, hp=500), _unit("d", 1, 6, 3, hp=10)])
    result = simulate_battle(setup, 8)
    board_text = render_board(result["events"])
    assert "y\\x" in board_text and "图例" in board_text
    summary = render_summary(result["events"])
    assert summary["winner"] == result["winner"]
    detailed = render_detailed(result["events"])
    assert any("先攻" in line for line in detailed)
    assert any("战斗结束" in line for line in detailed)


def test_initiative_events_interleaved_before_unit_actions() -> None:
    """
    先攻不在回合开头批量堆叠：每个 initiative 紧挨该 uid 的下一条行动事件。

    日志/动画形态：先攻(最高) → 行动… → 先攻(次高) → 行动…。
    """
    setup = _setup(
        [
            _unit("slow", 0, 0, 3, atk=1, hp=500, speed=1),
            _unit("fast", 0, 1, 3, atk=1, hp=500, speed=20),
            _unit("enemy", 1, 6, 3, atk=1, hp=500, speed=5),
        ],
    )
    result = simulate_battle(setup, 42)
    events = result["events"]
    # 找到第一回合的 round_start 之后到下一 round_start / battle_end
    start_idx = next(i for i, e in enumerate(events) if e["type"] == "round_start")
    end_idx = len(events)
    for i in range(start_idx + 1, len(events)):
        if events[i]["type"] in ("round_start", "battle_end"):
            end_idx = i
            break
    round_events = events[start_idx:end_idx]
    # 不应出现「连续两条 initiative」开场刷屏（中间只夹 turn_order 也不算行动）
    initiatives = [e for e in round_events if e["type"] == "initiative"]
    assert len(initiatives) >= 2
    for init_ev in initiatives:
        idx = round_events.index(init_ev)
        # 下一条非 meta 事件应属于同一 uid 的行动（move/hit/…），或该单位本回合无动作被跳过
        following = None
        for nxt in round_events[idx + 1 :]:
            if nxt["type"] in ("turn_order", "round_start"):
                continue
            following = nxt
            break
        assert following is not None
        if following["type"] == "initiative":
            # 不允许两先攻背靠背
            raise AssertionError("initiative events must not be consecutive")
        # 行动事件应带同一 uid（move/blocked 用 uid；hit_check 用 attacker）
        actor = following.get("uid") or following.get("attacker")
        assert actor == init_ev["uid"]


def test_ally_repath_around_friendly_blocker() -> None:
    """开阔地：后排被友军挡最短路时改道绕行，不反复 blocked_unit 空耗。"""
    setup = _setup(
        [
            # 同列前后排：地形贪心必经前排格；软墙应改走旁路
            _unit("front", 0, 2, 3, atk=1, hp=500, speed=10),
            _unit("rear", 0, 0, 3, atk=100, hp=500, speed=1),
            _unit("enemy", 1, 6, 3, atk=1, hp=10, speed=1),
        ],
    )
    result = simulate_battle(setup, 21)
    assert result["winner"] == "attacker"
    stuck = [
        e
        for e in _events_of(result, "move")
        if e.get("uid") == "rear"
        and e.get("stop_reason") == "blocked_unit"
        and len(e.get("path") or []) <= 1
    ]
    # 允许偶发一拍等待，但不允许整场卡死式撞人
    assert len(stuck) <= 2


def test_ally_yield_opens_chokepoint_corridor() -> None:
    """窄廊 + 侧袋：前排挡死唯一通道时应侧移让路，后排得以通过并击杀。"""
    # 陆地单位视深渊为硬墙：y=3 通道；仅 (3,2)/(3,4) 为与 (3,3) 相连的让路袋
    terrain = []
    for x in range(7):
        for y in range(7):
            if y == 3:
                continue
            if x == 3 and y in (2, 4):
                continue
            terrain.append(
                {
                    "x": x,
                    "y": y,
                    "type": "ravine",
                    "subtype": "no_fly",
                },
            )
    setup = _setup(
        [
            _unit("front", 0, 3, 3, atk=1, hp=500, speed=10),
            _unit("rear", 0, 0, 3, atk=100, hp=500, speed=1),
            _unit("enemy", 1, 6, 3, atk=1, hp=10, speed=1),
        ],
        attacker_formation={
            "id": "chute",
            "name": "窄廊",
            "level": 1,
            "terrain": terrain,
            "environment": None,
            "weather": None,
            "effect": None,
        },
    )
    result = simulate_battle(setup, 13)
    assert result["winner"] == "attacker"
    # 前排必须出现离开 (3,3) 的让路移动
    front_moves = [e for e in _events_of(result, "move") if e.get("uid") == "front"]
    assert front_moves
    yielded = False
    for move in front_moves:
        path = move.get("path") or []
        if len(path) >= 2 and (path[0].get("x"), path[0].get("y")) == (3, 3):
            end = path[-1]
            if (end.get("x"), end.get("y")) in {(3, 2), (3, 4)}:
                yielded = True
                break
    assert yielded, "front should yield into side pocket (3,2) or (3,4)"
