"""
棋盘占位规则单测（M3 · S1）。

覆盖设计 §3.4 全部校验项：区外 / 中立列 / 重叠 / 超员 / 缺本体 / 未开放种类 / 地形禁停。
"""

from __future__ import annotations

import pytest

from app.domain.board import (
    PlacementError,
    board_meta_payload,
    default_deploy_cells,
    max_units_for_realm,
    mirrored_cells,
    validate_placement,
)
from app.domain.board_tables import (
    CHEBYSHEV_ROW,
    MANHATTAN_ROW,
    cell_of,
    mirror_cell,
    mirror_x,
)
from app.services.realm_config import get_game_config


def _board():
    """取解析后的 BoardConfig。"""
    return get_game_config().board


def _main(x: int, y: int) -> dict:
    """构造一个本体占位。"""
    return {"unit_uid": "main", "unit_kind": "main", "x": x, "y": y}


def _puppet(uid: str, x: int, y: int) -> dict:
    """构造一个试炼木傀占位。"""
    return {"unit_uid": uid, "unit_kind": "puppet", "x": x, "y": y}


def test_default_deploy_cells_match_config() -> None:
    """默认部署区 = (0,2)–(1,4) 共 6 格。"""
    cells = default_deploy_cells(_board())
    assert len(cells) == 6
    assert (0, 2) in cells and (1, 4) in cells
    assert (2, 3) not in cells  # 区外
    # 镜像后落在敌对半区
    mirrored = mirrored_cells(cells)
    assert (6, 2) in mirrored and (5, 4) in mirrored


def test_validate_ok() -> None:
    """合法布阵通过校验。"""
    validate_placement(
        [_main(0, 3), _puppet("puppet_1", 1, 2)],
        _board(),
        max_units=3,
    )


def test_out_of_zone_and_neutral_rejected() -> None:
    """区外 / 中立列落子 → 40041。"""
    with pytest.raises(PlacementError) as exc:
        validate_placement([_main(3, 3)], _board(), max_units=3)
    assert exc.value.code == 40041
    with pytest.raises(PlacementError) as exc:
        validate_placement([_main(0, 0)], _board(), max_units=3)
    assert exc.value.code == 40041


def test_overlap_rejected() -> None:
    """同格重复落子 → 40041。"""
    with pytest.raises(PlacementError) as exc:
        validate_placement(
            [_main(0, 3), _puppet("puppet_1", 0, 3)],
            _board(),
            max_units=3,
        )
    assert exc.value.code == 40041


def test_over_limit_rejected() -> None:
    """超出上阵上限 → 40041。"""
    units = [_main(0, 2), _puppet("p1", 0, 3), _puppet("p2", 0, 4)]
    with pytest.raises(PlacementError) as exc:
        validate_placement(units, _board(), max_units=2)
    assert exc.value.code == 40041


def test_main_required_and_unique() -> None:
    """缺本体 / 双本体 → 40042。"""
    with pytest.raises(PlacementError) as exc:
        validate_placement([_puppet("p1", 0, 3)], _board(), max_units=3)
    assert exc.value.code == 40042
    with pytest.raises(PlacementError) as exc:
        validate_placement(
            [
                _main(0, 3),
                {"unit_uid": "main2", "unit_kind": "main", "x": 0, "y": 2},
            ],
            _board(),
            max_units=3,
        )
    assert exc.value.code == 40042


def test_disabled_kind_rejected() -> None:
    """未开放种类（prop）→ 40043。"""
    with pytest.raises(PlacementError) as exc:
        validate_placement(
            [_main(0, 3), {"unit_uid": "prop_1", "unit_kind": "prop", "x": 0, "y": 2}],
            _board(),
            max_units=3,
        )
    assert exc.value.code == 40043


def test_terrain_blocked_cell_rejected() -> None:
    """阵法地形禁停格 → 40041。"""
    with pytest.raises(PlacementError) as exc:
        validate_placement(
            [_main(0, 3)],
            _board(),
            max_units=3,
            blocked_cells=frozenset({(0, 3)}),
        )
    assert exc.value.code == 40041


def test_max_units_for_realm() -> None:
    """锻体 3 人；未配置境界回退默认并受部署格数封顶。"""
    assert max_units_for_realm(_board(), "body_tempering") == 3
    assert max_units_for_realm(_board(), "unknown_realm") == 6


def test_board_meta_payload() -> None:
    """board-meta 含画盘所需字段。"""
    meta = board_meta_payload(_board())
    assert meta["size"] == 7
    assert meta["zones"]["neutral_x"] == [3]
    assert len(meta["default_deploy_cells"]) == 6
    assert meta["mirror_rule"] == "defender_mirror_x"
    assert meta["unit_kinds"]["main"]["required"] is True


def test_static_tables_sanity() -> None:
    """静态表口径抽查：镜像 / 曼哈顿 / 切比雪夫。"""
    assert mirror_x(0) == 6 and mirror_x(3) == 3
    assert mirror_cell(cell_of(0, 3)) == cell_of(6, 3)
    a, b = cell_of(0, 0), cell_of(6, 6)
    assert MANHATTAN_ROW[a][b] == 12
    assert CHEBYSHEV_ROW[a][b] == 6
    # 设计 §12.7 指定用例：远程射程 5 时 (0,0) 可覆盖 (5,5)（切比雪夫距离恰为 5）
    assert CHEBYSHEV_ROW[cell_of(0, 0)][cell_of(5, 5)] == 5
