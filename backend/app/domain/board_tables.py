"""
棋盘导入期静态表（M3自动移动攻击算法设计.md §3～§4 · O1/O2）。

- 扁平索引：``cell = y * 7 + x``；左下角为 (0,0)。
- 49 格 < 64 bit，任意格集合用一个 Python ``int`` 位掩码表示。
- 全部表在模块导入时构建一次，均为不可变 ``tuple``/``int``：
  只读共享、无锁、多进程 fork 后 COW 不复制。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

# 棋盘边长与格数常量
BOARD_SIZE = 7
CELL_COUNT = BOARD_SIZE * BOARD_SIZE  # 49
FULL_MASK = (1 << CELL_COUNT) - 1


def cell_of(x: int, y: int) -> int:
    """
    将棋盘坐标转为扁平格索引（左下锚点）。

    参数:
        x: 横坐标，0..6，向右增大。
        y: 纵坐标，0..6，向上增大。

    返回:
        int: 扁平索引 ``y * 7 + x``。
    """
    return y * BOARD_SIZE + x


def x_of(cell: int) -> int:
    """取扁平索引的 x 坐标。"""
    return cell % BOARD_SIZE


def y_of(cell: int) -> int:
    """取扁平索引的 y 坐标。"""
    return cell // BOARD_SIZE


def mirror_x(x: int) -> int:
    """防守方半区 x 镜像：``x' = 6 - x``（y 不变）。"""
    return (BOARD_SIZE - 1) - x


def mirror_cell(cell: int) -> int:
    """对扁平索引做 x 镜像。"""
    return cell_of(mirror_x(x_of(cell)), y_of(cell))


def iter_bits(mask: int) -> list[int]:
    """
    枚举位掩码中所有置位格索引（低位在前，顺序确定）。

    说明：决策热路径应内联 while 循环；此函数供非热路径与测试使用。
    """
    cells: list[int] = []
    m = mask
    while m:
        low = m & -m
        cells.append(low.bit_length() - 1)
        m ^= low
    return cells


def _build_ortho_tables() -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...]]:
    """构建正交邻接掩码表与邻格索引表（近战攻击位 / 逐步走子用）。"""
    masks: list[int] = []
    neighbors: list[tuple[int, ...]] = []
    for cell in range(CELL_COUNT):
        cx, cy = x_of(cell), y_of(cell)
        mask = 0
        adj: list[int] = []
        # 仅上下左右四向（移动与近战均禁止斜向）
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                n = cell_of(nx, ny)
                mask |= 1 << n
                adj.append(n)
        masks.append(mask)
        neighbors.append(tuple(adj))
    return tuple(masks), tuple(neighbors)


def _build_range_masks() -> tuple[tuple[int, ...], ...]:
    """
    构建切比雪夫射程掩码表：``RANGE_MASK_EX[r][cell]``。

    表示以 cell 为中心、切比雪夫距离 ≤ r 且排除自身的格集合（远程攻击位）。
    """
    tables: list[tuple[int, ...]] = []
    for r in range(BOARD_SIZE):
        row: list[int] = []
        for cell in range(CELL_COUNT):
            cx, cy = x_of(cell), y_of(cell)
            mask = 0
            for other in range(CELL_COUNT):
                if other == cell:
                    continue
                ox, oy = x_of(other), y_of(other)
                if max(abs(ox - cx), abs(oy - cy)) <= r:
                    mask |= 1 << other
            row.append(mask)
        tables.append(tuple(row))
    return tuple(tables)


def _build_distance_rows() -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]]:
    """构建 49×49 曼哈顿 / 切比雪夫距离查表（查表比现算 abs 更省字节码）。"""
    manhattan: list[tuple[int, ...]] = []
    chebyshev: list[tuple[int, ...]] = []
    for a in range(CELL_COUNT):
        ax, ay = x_of(a), y_of(a)
        man_row: list[int] = []
        che_row: list[int] = []
        for b in range(CELL_COUNT):
            bx, by = x_of(b), y_of(b)
            dx, dy = abs(bx - ax), abs(by - ay)
            man_row.append(dx + dy)
            che_row.append(max(dx, dy))
        manhattan.append(tuple(man_row))
        chebyshev.append(tuple(che_row))
    return tuple(manhattan), tuple(chebyshev)


def _build_ray_between() -> tuple[tuple[int, ...], ...]:
    """
    构建直线中间格掩码表：``RAY_BETWEEN[a][b]``。

    仅当 a、b 共行 / 共列 / 共对角时非 0（不含两端点）；
    其它角度按成型设计 §5.2 简化为不遮挡（完整 LOS 见延后项 M3-D02）。
    """
    rays: list[tuple[int, ...]] = []
    for a in range(CELL_COUNT):
        ax, ay = x_of(a), y_of(a)
        row: list[int] = []
        for b in range(CELL_COUNT):
            bx, by = x_of(b), y_of(b)
            dx, dy = bx - ax, by - ay
            mask = 0
            # 共线判定：水平 / 垂直 / 45° 对角
            if (a != b) and (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
                steps = max(abs(dx), abs(dy))
                sx = (dx > 0) - (dx < 0)
                sy = (dy > 0) - (dy < 0)
                for i in range(1, steps):
                    mask |= 1 << cell_of(ax + sx * i, ay + sy * i)
            row.append(mask)
        rays.append(tuple(row))
    return tuple(rays)


# ---------------------------------------------------------------------------
# 导入期构建（一次性；全部不可变）
# ---------------------------------------------------------------------------

ORTHO_MASK, ORTHO_NEIGHBORS = _build_ortho_tables()
RANGE_MASK_EX = _build_range_masks()
MANHATTAN_ROW, CHEBYSHEV_ROW = _build_distance_rows()
RAY_BETWEEN = _build_ray_between()
