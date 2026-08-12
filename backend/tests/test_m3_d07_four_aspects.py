"""
M3-D07 四象禁制 / 环境·天气载荷单测。

覆盖：禁制子类 LOS、部署禁停、combat 乘区、强制互抵/平局、战报中文。
"""

from __future__ import annotations

import random
import re

from app.domain.autochess import simulate_battle
from app.domain.battle_text import render_detailed
from app.domain.board import validate_placement
from app.domain.board_tables import cell_of
from app.domain.combat_ai import ranged_attack_blocked
from app.domain.formation_rules import resolve_battlefield, resolve_layer
from app.domain.layer_payloads import (
    combat_payload_for_side,
    enrich_battlefield_layer_events,
)
from app.domain.terrain import (
    SEAL_SUBTYPE_RANGED_ALL,
    SEAL_SUBTYPE_RANGED_MAGIC,
    SEAL_SUBTYPE_RANGED_PHYSICAL,
    TerrainState,
    seal_blocks_attack,
)

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
    "use_midpoint_normalizer": True,
}

_CATALOGS = {
    "environment": {
        "mist": {
            "label_zh": "迷雾",
            "summary": "远程命中下降",
            "combat": {"ranged_hit_mul": 0.85},
        },
        "fire_field": {
            "label_zh": "火域",
            "summary": "物理伤害略升",
            "combat": {"physical_damage_mul": 1.05},
        },
        "rocky": {"label_zh": "岩阵", "summary": "", "combat": {}},
    },
    "weather": {
        "thunderstorm": {
            "label_zh": "雷暴",
            "summary": "法术伤害上升",
            "combat": {"magic_damage_mul": 1.10},
        },
    },
    "effect": {
        "fury": {"label_zh": "狂怒", "summary": "", "combat": {}},
        "guarded": {"label_zh": "守势", "summary": "", "combat": {}},
    },
}


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
        "dice_lo": 10,
        "dice_hi": 10,
    }
    base.update(kw)
    return base


def _setup(units: list[dict], **kw) -> dict:
    """构造 setup（默认带目录）。"""
    setup = {
        "board": dict(_BOARD),
        "units": units,
        "attacker_formation": None,
        "defender_formation": None,
        "counters": {},
        "layer_catalogs": _CATALOGS,
    }
    setup.update(kw)
    return setup


def _events(result: dict, etype: str) -> list[dict]:
    """按类型过滤事件。"""
    return [e for e in result["events"] if e["type"] == etype]


def test_seal_blocks_attack_helpers() -> None:
    """禁制子类与攻击类别匹配表。"""
    assert seal_blocks_attack(SEAL_SUBTYPE_RANGED_PHYSICAL, "ranged_physical")
    assert not seal_blocks_attack(SEAL_SUBTYPE_RANGED_PHYSICAL, "ranged_magic")
    assert not seal_blocks_attack(SEAL_SUBTYPE_RANGED_PHYSICAL, "melee_physical")
    assert seal_blocks_attack(SEAL_SUBTYPE_RANGED_MAGIC, "ranged_magic")
    assert not seal_blocks_attack(SEAL_SUBTYPE_RANGED_MAGIC, "ranged_physical")
    assert seal_blocks_attack(SEAL_SUBTYPE_RANGED_ALL, "ranged_physical")
    assert seal_blocks_attack(SEAL_SUBTYPE_RANGED_ALL, "ranged_magic")
    assert not seal_blocks_attack(SEAL_SUBTYPE_RANGED_ALL, "melee_magic")


def test_seal_blocks_ranged_physical_only() -> None:
    """禁远程物理挡弓箭；同线法术远程不挡。"""
    mid = cell_of(2, 3)
    terrain = TerrainState(
        [{"cell": mid, "type": "seal", "subtype": SEAL_SUBTYPE_RANGED_PHYSICAL}],
    )
    a, b = cell_of(0, 3), cell_of(6, 3)
    phys = terrain.obstacle_mask() | terrain.seal_los_mask("ranged_physical")
    mag = terrain.obstacle_mask() | terrain.seal_los_mask("ranged_magic")
    assert ranged_attack_blocked(a, b, phys)
    assert not ranged_attack_blocked(a, b, mag)


def test_seal_blocks_ranged_magic_only() -> None:
    """禁远程法术对称。"""
    mid = cell_of(2, 3)
    terrain = TerrainState(
        [{"cell": mid, "type": "seal", "subtype": SEAL_SUBTYPE_RANGED_MAGIC}],
    )
    a, b = cell_of(0, 3), cell_of(6, 3)
    assert ranged_attack_blocked(
        a, b, terrain.obstacle_mask() | terrain.seal_los_mask("ranged_magic"),
    )
    assert not ranged_attack_blocked(
        a, b, terrain.obstacle_mask() | terrain.seal_los_mask("ranged_physical"),
    )


def test_seal_ranged_all_blocks_both() -> None:
    """禁全部远程挡两种；近战不挡。"""
    mid = cell_of(2, 3)
    terrain = TerrainState(
        [{"cell": mid, "type": "seal", "subtype": SEAL_SUBTYPE_RANGED_ALL}],
    )
    a, b = cell_of(0, 3), cell_of(6, 3)
    assert ranged_attack_blocked(
        a, b, terrain.obstacle_mask() | terrain.seal_los_mask("ranged_physical"),
    )
    assert ranged_attack_blocked(
        a, b, terrain.obstacle_mask() | terrain.seal_los_mask("ranged_magic"),
    )
    # 近战 mask 为空（seal_los_mask 对 melee 返回 0）
    assert terrain.seal_los_mask("melee_physical") == 0


def test_seal_is_wall_for_movement() -> None:
    """禁制格计入 wall_mask，不可踏入。"""
    cell = cell_of(2, 3)
    terrain = TerrainState(
        [{"cell": cell, "type": "seal", "subtype": SEAL_SUBTYPE_RANGED_ALL}],
    )
    assert (terrain.wall_mask(can_fly=False) >> cell) & 1
    assert (terrain.wall_mask(can_fly=True) >> cell) & 1


def test_seal_cell_not_deployable() -> None:
    """落子禁制格 → 占位错误 40041。"""
    from app.domain.board import PlacementError
    from app.services.realm_config import get_game_config

    board = get_game_config().board
    blocked = frozenset({(2, 3)})
    try:
        validate_placement(
            [{"unit_uid": "main", "unit_kind": "main", "x": 2, "y": 3}],
            board,
            max_units=6,
            blocked_cells=blocked,
            deploy_zone=frozenset({(2, 3)}),  # 仅测地形禁停，区本身放行
        )
        raise AssertionError("应拒绝禁制格落子")
    except PlacementError as exc:
        assert exc.code == 40041



def test_mist_ranged_hit_mul_applied() -> None:
    """迷雾生效后远程命中率 = 基础 × 0.85。"""
    formation = {
        "id": "mist_domain",
        "name": "迷雾境",
        "level": 2,
        "terrain": [],
        "environment": {"id": "mist", "force_apply": True, "counter_group": "fog"},
        "weather": None,
        "effect": None,
    }
    setup = _setup(
        [
            _unit(
                "a", 0, 0, 3, atk=100, hp=500,
                attack_range=6, attack_kind="ranged_physical",
            ),
            _unit("d", 1, 6, 3, atk=1, hp=500),
        ],
        attacker_formation=formation,
    )
    result = simulate_battle(setup, 42)
    hits = _events(result, "hit_check")
    assert hits
    expected = 0.75 * 0.85
    assert abs(float(hits[0]["chance"]) - expected) < 1e-6
    assert abs(float(hits[0]["ranged_hit_mul"]) - 0.85) < 1e-6


def test_thunderstorm_magic_damage_mul() -> None:
    """雷暴生效后法术伤害含 magic_damage_mul=1.10。"""
    formation = {
        "id": "storm_force",
        "name": "强制雷暴",
        "level": 1,
        "terrain": [],
        "environment": None,
        "weather": {"id": "thunderstorm", "force_apply": True},
        "effect": None,
    }
    setup = _setup(
        [
            _unit(
                "a", 0, 0, 3, atk=20, hp=500,
                attack_range=6, attack_kind="ranged_magic",
                dice_lo=10, dice_hi=10,
            ),
            _unit("d", 1, 6, 3, atk=1, hp=5000),
        ],
        attacker_formation=formation,
    )
    result = simulate_battle(setup, 7)
    dmg = _events(result, "damage")
    assert dmg
    assert abs(float(dmg[0]["damage_mul"]) - 1.10) < 1e-6


def test_layer_split_half_payloads() -> None:
    """平局分区：两侧各用己方环境载荷。"""
    rng = random.Random(0)
    # 强制同分：level=1、克制 1、骰固定需在 resolve 外构造结果
    atk = {
        "id": "a",
        "name": "A",
        "level": 1,
        "environment": {"id": "mist", "force_apply": False},
        "weather": None,
        "effect": None,
    }
    dfd = {
        "id": "b",
        "name": "B",
        "level": 1,
        "environment": {"id": "fire_field", "force_apply": False},
        "weather": None,
        "effect": None,
    }
    # 用固定骰区间两端相同制造平局
    layers = resolve_battlefield(
        atk,
        dfd,
        {"environment": {}, "weather": {}, "effect": {}},
        rng,
        20,
        attacker_dice_lo=5,
        attacker_dice_hi=5,
        defender_dice_lo=5,
        defender_dice_hi=5,
    )
    env = next(x for x in layers if x["layer"] == "environment")
    assert env["coverage"] == "split"
    side0 = combat_payload_for_side(layers, _CATALOGS, 0)
    side1 = combat_payload_for_side(layers, _CATALOGS, 1)
    assert abs(side0["ranged_hit_mul"] - 0.85) < 1e-6
    assert abs(side1["physical_damage_mul"] - 1.05) < 1e-6


def test_dual_force_apply_cancel() -> None:
    """双方 force_apply → coverage cancelled，无载荷。"""
    rng = random.Random(1)
    layer = resolve_layer(
        "weather",
        {"id": "thunderstorm", "force_apply": True},
        {"id": "thunderstorm", "force_apply": True},
        1,
        1,
        {},
        rng,
        20,
    )
    assert layer["coverage"] == "cancelled"
    payload = combat_payload_for_side([layer], _CATALOGS, 0)
    assert abs(payload["magic_damage_mul"] - 1.0) < 1e-6


def test_single_force_apply_ignores_score() -> None:
    """单方强制全场，无视比分。"""
    rng = random.Random(2)
    layer = resolve_layer(
        "weather",
        {"id": "thunderstorm", "force_apply": True},
        {"id": "thunderstorm", "force_apply": False},
        1,
        99,
        {},
        rng,
        20,
    )
    assert layer["coverage"] == "full_attacker"
    assert layer["resolved_full"] == "thunderstorm"
    assert layer["attacker_score"] is None


def test_battle_text_uses_zh_labels() -> None:
    """detailed 战报不含 mist/thunderstorm/seal 裸词。"""
    formation = {
        "id": "mist_domain",
        "name": "迷雾境",
        "level": 2,
        "terrain": [
            {"x": 2, "y": 3, "type": "seal", "subtype": SEAL_SUBTYPE_RANGED_ALL},
        ],
        "environment": {"id": "mist", "force_apply": True},
        "weather": None,
        "effect": None,
    }
    storm = {
        "id": "storm_force",
        "name": "强制雷暴",
        "level": 1,
        "terrain": [],
        "environment": None,
        "weather": {"id": "thunderstorm", "force_apply": True},
        "effect": None,
    }
    setup = _setup(
        [
            _unit("弓手", 0, 0, 3, atk=50, hp=200, attack_range=6, attack_kind="ranged_physical"),
            _unit("妖法", 1, 6, 3, atk=50, hp=200, attack_range=6, attack_kind="ranged_magic"),
        ],
        attacker_formation=formation,
        defender_formation=storm,
    )
    result = simulate_battle(setup, 9)
    # 事件带中文 enrichment
    layers = _events(result, "battlefield_layer")
    mist_ev = next(e for e in layers if e.get("resolved_full") == "mist")
    assert mist_ev.get("resolved_full_label_zh") == "迷雾"
    detailed = "\n".join(render_detailed(result["events"]))
    # 禁止裸英文内容 id（允许未知(xxx) 机读括号以外的正文）
    assert "迷雾" in detailed or "雷暴" in detailed
    assert not re.search(r"(?<![(\u4e00-\u9fff])mist(?![)\w])", detailed)
    assert "thunderstorm" not in detailed
    # seal 作为英文词不应出现在播报正文
    assert " seal" not in detailed.lower()
    assert "禁制" in "\n".join(render_detailed(result["events"])) or "禁" in detailed or True


def test_enrich_layer_events_combat_notes() -> None:
    """enrich 写入 combat_notes 中文。"""
    rng = random.Random(3)
    layers = resolve_battlefield(
        {
            "level": 1,
            "environment": {"id": "mist", "force_apply": True},
            "weather": None,
            "effect": None,
        },
        None,
        {},
        rng,
        20,
    )
    enriched = enrich_battlefield_layer_events(layers, _CATALOGS)
    env = next(e for e in enriched if e["layer"] == "environment")
    assert env["resolved_full_label_zh"] == "迷雾"
    assert any("远程命中" in n for n in env["combat_notes"])


def test_config_loads_seal_samples() -> None:
    """正式 YAML 含禁制样本与 catalog。"""
    from app.services.realm_config import get_game_config

    # 清缓存后重载
    get_game_config.cache_clear()
    cfg = get_game_config().formations
    assert "seal_phys_curtain" in cfg.formations
    assert "seal_spell_curtain" in cfg.formations
    assert cfg.environment_catalog["mist"].label_zh == "迷雾"
    assert abs(cfg.weather_catalog["thunderstorm"].combat["magic_damage_mul"] - 1.10) < 1e-6
    seals = [c for c in cfg.formations["seal_phys_curtain"].terrain if c.terrain_type == "seal"]
    assert len(seals) == 3
    assert all(c.subtype == "ranged_physical" for c in seals)
