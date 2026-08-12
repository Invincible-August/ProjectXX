"""
嘲讽光环单测（M3-D06 Phase A · 嘲讽光环设计.md §10）。

覆盖：形状掩码、进入触发、强制目标优先、死亡解除、战报事件、确定性。
"""

from __future__ import annotations

from app.domain.autochess import simulate_battle
from app.domain.board_tables import ORTHO_MASK, cell_of
from app.domain.taunt_aura import (
    aura_snapshot_from_def,
    coverage_mask,
    rebuild_taunt_auras,
)
from app.services.realm_config import clear_game_config_cache, get_game_config

_BOARD = {
    "size": 7,
    "max_rounds": 40,
    "timeout_winner": "defender",
    "dice_sides": 20,
    "ap_per_turn": 2,
    "land_move_points": 2,
    "fly_move_points": 4,
    "hit_rates": {
        "melee_physical": 1.0,
        "melee_magic": 1.0,
        "ranged_physical": 1.0,
        "ranged_magic": 1.0,
    },
    "damage_floor": 0,
    "damage_dice_normalizer": 10,
}


def _ortho_aura() -> dict:
    """正交邻接光环快照。"""
    return aura_snapshot_from_def(
        "ortho_guard",
        {
            "label_zh": "护卫嘲讽",
            "help_zh": "test",
            "summary": "邻接四格",
            "shape": "ortho_adjacent",
            "include_self_cell": False,
            "duration_rounds": None,
        },
    )


def _unit(uid: str, side: int, x: int, y: int, **kw) -> dict:
    """构造引擎棋子。"""
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
    """构造 setup。"""
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


def test_coverage_ortho_matches_table() -> None:
    """ortho_adjacent 覆盖 = ORTHO_MASK。"""
    center = cell_of(5, 3)
    mask = coverage_mask(center, _ortho_aura())
    assert mask == int(ORTHO_MASK[center])
    assert not (mask >> center) & 1


def test_bundle_loads_taunt_auras() -> None:
    """Bundle 含 taunt_auras 样本，且怪物外键合法。"""
    clear_game_config_cache()
    cfg = get_game_config()
    assert "ortho_guard" in cfg.taunt_auras.auras
    assert "taunt_guardian" in cfg.monsters
    guard_units = cfg.monsters["taunt_guardian"].units
    assert any(u.taunt_aura_id == "ortho_guard" for u in guard_units)


def test_enter_aura_emits_taunt_and_retarget() -> None:
    """从光环外走入邻格 → taunt + ai_retarget + move.stop_reason=taunt。"""
    # 进攻方从 (3,3) 走向 (5,3) 护关者；第一步到 (4,3) 进入正交光环
    setup = _setup(
        [
            _unit("atk", 0, 3, 3, atk=5, hp=500, speed=20),
            _unit("aaa_glass", 1, 6, 1, atk=1, hp=500, speed=1),
            _unit(
                "guard",
                1,
                5,
                3,
                atk=1,
                hp=500,
                speed=1,
                taunt_aura=_ortho_aura(),
            ),
        ],
    )
    result = simulate_battle(setup, 42)
    taunts = _events_of(result, "taunt")
    assert taunts, "应发射 taunt 事件"
    assert taunts[0]["taunter"] == "guard"
    assert taunts[0]["victim"] == "atk"
    retargets = [e for e in _events_of(result, "ai_retarget") if e.get("reason") == "taunt"]
    assert retargets
    taunt_moves = [
        e for e in _events_of(result, "move") if e.get("stop_reason") == "taunt"
    ]
    assert taunt_moves


def test_taunt_priority_over_closer_enemy() -> None:
    """被嘲讽后只打嘲讽者，即使另一敌人邻接且 uid 更优先。"""
    # atk 从 (4,4) 为接近 aaa_glass(4,2) 而踏入 (4,3) → 进入 guard 光环
    # 进入后 glass 已邻接；无嘲讽会优先打 aaa_glass；有嘲讽必须打 zzz_guard
    setup = _setup(
        [
            _unit("atk", 0, 4, 4, atk=30, hp=500, speed=30),
            _unit("aaa_glass", 1, 4, 2, atk=1, hp=5000, speed=1),
            _unit(
                "zzz_guard",
                1,
                5,
                3,
                atk=1,
                hp=5000,
                speed=1,
                taunt_aura=_ortho_aura(),
            ),
        ],
    )
    result = simulate_battle(setup, 99)
    assert _events_of(result, "taunt"), "应先因接近 glass 踏入光环"
    taunt_seq = _events_of(result, "taunt")[0]["seq"]
    deaths = {e["uid"]: e["seq"] for e in _events_of(result, "death")}
    guard_death = deaths.get("zzz_guard", 10**9)
    hits_after = [
        e
        for e in _events_of(result, "hit_check")
        if e["attacker"] == "atk" and taunt_seq < e["seq"] < guard_death
    ]
    assert hits_after, "嘲讽后应有攻击检定"
    assert all(e["target"] == "zzz_guard" for e in hits_after)


def test_taunt_cleared_on_taunter_death() -> None:
    """嘲讽者死亡后可改打其他敌人。"""
    setup = _setup(
        [
            _unit("atk", 0, 3, 3, atk=80, hp=500, speed=30),
            _unit("glass", 1, 6, 3, atk=1, hp=40, speed=1),
            _unit(
                "guard",
                1,
                5,
                3,
                atk=1,
                hp=30,
                speed=1,
                taunt_aura=_ortho_aura(),
            ),
        ],
    )
    result = simulate_battle(setup, 7)
    assert _events_of(result, "taunt")
    deaths = _events_of(result, "death")
    assert any(e["uid"] == "guard" for e in deaths)
    # guard 死后应能打到 glass（否则胜不了 / 无 glass 受伤）
    guard_death_seq = next(e["seq"] for e in deaths if e["uid"] == "guard")
    hits_on_glass = [
        e
        for e in _events_of(result, "hit_check")
        if e["attacker"] == "atk"
        and e["target"] == "glass"
        and e["seq"] > guard_death_seq
    ]
    assert hits_on_glass, "嘲讽解除后应能攻击后排"


def test_taunt_determinism() -> None:
    """同 setup+seed 事件序列一致。"""
    setup = _setup(
        [
            _unit("atk", 0, 3, 3, atk=20, hp=300, speed=15),
            _unit("glass", 1, 6, 3, atk=1, hp=80, speed=1),
            _unit(
                "guard",
                1,
                5,
                3,
                atk=1,
                hp=80,
                speed=1,
                taunt_aura=_ortho_aura(),
            ),
        ],
    )
    r1 = simulate_battle(setup, 123)
    r2 = simulate_battle(setup, 123)
    assert r1["events"] == r2["events"]


def test_rebuild_mask_side_aggregation() -> None:
    """按侧聚合掩码：防守方光环写入 mask[1]。"""
    from app.domain.autochess import BattleState

    state = BattleState()
    state.count = 1
    state.uid = ["g"]
    state.side = [1]
    state.cell = [cell_of(5, 3)]
    state.alive = [True]
    state.taunt_aura = [_ortho_aura()]
    state.taunt_target = [-1]
    rebuild_taunt_auras(state)
    assert state.taunt_aura_mask[1] == int(ORTHO_MASK[cell_of(5, 3)])
    assert state.taunt_aura_mask[0] == 0
    assert state.aura_owner[cell_of(4, 3)] == 0


def test_monster_list_exposes_taunt_labels() -> None:
    """选怪列表应对 taunt_guardian 下发嘲讽中文摘要（§0.7）。"""
    from app.services.autochess_service import AutochessService

    clear_game_config_cache()
    rows = AutochessService.list_pve_monsters_public()
    guardian = next(r for r in rows if r["monster_id"] == "taunt_guardian")
    assert guardian["taunt_auras"]
    assert guardian["taunt_auras"][0]["aura_id"] == "ortho_guard"
    assert guardian["taunt_auras"][0]["label_zh"] == "护卫嘲讽"
    # 无光环怪应为空列表
    slime = next(r for r in rows if r["monster_id"] == "tutorial_slime")
    assert slime["taunt_auras"] == []
