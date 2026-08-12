"""
阵法部署契约 / 强制移位单测（M3-D08 · 阵法部署与自研设计）。

覆盖：resolve_deploy 四模式、越区拒绝、force_shift noop/applied/occupied。
"""

from __future__ import annotations

import pytest

from app.domain.autochess import simulate_battle
from app.domain.board import PlacementError, validate_placement
from app.domain.formation_blueprint import (
    DeployConfig,
    apply_force_shifts_to_state,
    resolve_deploy_cells,
    validate_blueprint,
)
from app.services.formation_service import FormationService
from app.services.realm_config import clear_game_config_cache, get_game_config


def _board():
    """取 BoardConfig。"""
    return get_game_config().board


def _main(x: int, y: int) -> dict:
    """本体占位。"""
    return {"unit_uid": "main", "unit_kind": "main", "x": x, "y": y}


@pytest.fixture(autouse=True)
def _reload_cfg() -> None:
    """确保读到最新 formations.yaml。"""
    clear_game_config_cache()


def test_wide_front_add_cells() -> None:
    """default + add_cells 扩展两格。"""
    formation = get_game_config().formations.formations["wide_front"]
    cells = FormationService.resolve_effective_deploy(formation)
    assert (2, 2) in cells and (2, 4) in cells
    assert (0, 3) in cells  # 默认区仍在
    assert len(cells) == 8


def test_cloud_drift_free_own_allows_own_half() -> None:
    """free_own：己方半区可落；中立/敌区拒绝。"""
    board = _board()
    formation = get_game_config().formations.formations["cloud_drift"]
    zone = FormationService.resolve_effective_deploy(formation)
    assert (0, 0) in zone and (2, 6) in zone
    assert (3, 3) not in zone
    assert (4, 3) not in zone
    # (2, 0) 合法
    validate_placement(
        [_main(2, 0)],
        board,
        max_units=4,
        deploy_zone=zone,
    )
    with pytest.raises(PlacementError) as exc:
        validate_placement([_main(3, 3)], board, max_units=4, deploy_zone=zone)
    assert exc.value.code == 40041


def test_left_wing_mask_rejects_outside() -> None:
    """mask：区外拒绝。"""
    board = _board()
    formation = get_game_config().formations.formations["left_wing_mask"]
    zone = FormationService.resolve_effective_deploy(formation)
    assert (0, 3) in zone
    assert (1, 4) not in zone
    with pytest.raises(PlacementError):
        validate_placement([_main(1, 4)], board, max_units=4, deploy_zone=zone)


def test_ravine_blocked_subtracted_from_deploy() -> None:
    """地形禁停格从有效部署区扣除。"""
    formation = get_game_config().formations.formations["ravine_trap"]
    cells = FormationService.resolve_effective_deploy(formation)
    assert (1, 3) not in cells


def test_blueprint_rejects_deploy_terrain_conflict() -> None:
    """部署格与障碍冲突 → validate_blueprint 失败。"""
    board = _board()
    deploy = DeployConfig(mode="default", add_cells=((2, 3),))
    from app.services.realm_config import FormationTerrainCell
    from app.domain.formation_blueprint import default_terrain_layout

    terrain = (
        FormationTerrainCell(x=2, y=3, terrain_type="obstacle", subtype="destructible"),
    )
    with pytest.raises(ValueError, match="冲突"):
        validate_blueprint(
            board,
            formation_id="bad",
            deploy=deploy,
            terrain_layout=default_terrain_layout(has_terrain=True),
            terrain=terrain,
            force_shifts=(),
        )


def test_force_shift_applied_and_noop() -> None:
    """移位：源有子 → applied；源空 → noop；目标占 → cancel。"""
    board = get_game_config().board
    # 最小 setup：攻方空阵 + 守方一子在 (4,3)
    setup = {
        "board": {
            "size": board.size,
            "ap_per_turn": 2,
            "max_rounds": 1,
            "timeout_winner": "defender",
            "dice_sides": 20,
            "land_move_points": 2,
            "fly_move_points": 4,
            "hit_rates": board.hit_rates,
            "damage_floor": board.damage_floor,
            "damage_dice_normalizer": board.damage_dice_normalizer,
        },
        "units": [
            {
                "uid": "a_main",
                "kind": "main",
                "name": "本体",
                "side": 0,
                "x": 0,
                "y": 3,
                "atk": 10,
                "hp": 100,
                "speed": 5,
                "attack_range": 1,
                "attack_kind": "melee_physical",
                "can_fly": False,
            },
            {
                "uid": "d_m",
                "kind": "monster",
                "name": "怪",
                "side": 1,
                "x": 4,
                "y": 3,
                "atk": 1,
                "hp": 50,
                "speed": 1,
                "attack_range": 1,
                "attack_kind": "melee_physical",
                "can_fly": False,
            },
        ],
        "attacker_formation": {
            "id": "shift_gust",
            "level": 2,
            "terrain": [],
            "force_shifts": [{"from": [4, 3], "to": [5, 3]}],
            "environment": None,
            "weather": None,
            "effect": None,
        },
        "defender_formation": None,
        "counters": {"effect": {}, "environment": {}, "weather": {}},
    }
    outcome = simulate_battle(setup, seed=42)
    shifts = [e for e in outcome["events"] if e.get("type") == "force_shift"]
    assert len(shifts) == 1
    assert shifts[0]["result"] == "shift_applied"
    # battle_start 中怪应已在 (5,3)
    start = next(e for e in outcome["events"] if e["type"] == "battle_start")
    defender = next(u for u in start["units"] if u["uid"] == "d_m")
    assert defender["x"] == 5 and defender["y"] == 3

    # 源空 → noop
    setup2 = dict(setup)
    setup2["units"] = [
        setup["units"][0],
        {**setup["units"][1], "x": 6, "y": 3},
    ]
    outcome2 = simulate_battle(setup2, seed=42)
    shifts2 = [e for e in outcome2["events"] if e.get("type") == "force_shift"]
    assert shifts2[0]["result"] == "shift_noop"


def test_force_shift_cancel_occupied() -> None:
    """目标格已有对方子 → cancel。"""
    from app.domain.board_tables import cell_of

    class _Fake:
        """最小战斗态替身。"""

        def __init__(self) -> None:
            self.count = 2
            self.uid = ["d1", "d2"]
            self.kind = ["monster", "monster"]
            self.side = [1, 1]
            self.cell = [cell_of(4, 3), cell_of(5, 3)]
            self.alive = [True, True]

        def slot_at(self, cell: int) -> int:
            for i in range(self.count):
                if self.alive[i] and self.cell[i] == cell:
                    return i
            return -1

    state = _Fake()
    events = apply_force_shifts_to_state(
        state,
        attacker_shifts=[{"from": [4, 3], "to": [5, 3]}],
        defender_shifts=None,
    )
    assert events[0]["result"] == "shift_cancel_occupied"


def test_deploy_snapshot_single_resolve() -> None:
    """FormationDeploySnapshot 一次解析禁停与有效格。"""
    from app.domain.formation_blueprint import resolve_formation_deploy

    formation = get_game_config().formations.formations["ravine_trap"]
    snap = resolve_formation_deploy(
        _board(),
        formation.deploy,
        formation.terrain,
    )
    assert (1, 3) in snap.blocked_cells
    assert (1, 3) not in snap.deploy_cells
    assert len(snap.deploy_cells) == 5


def test_none_formation_compat_default_zone() -> None:
    """none 阵法有效区 = 默认 6 格。"""
    formation = get_game_config().formations.formations["none"]
    cells = FormationService.resolve_effective_deploy(formation)
    assert len(cells) == 6
    assert formation.deploy.mode == "default"

