"""
位掩码地形与全源距离表（M3自动移动攻击算法设计.md §3/§5 · S6/M3-D02 最小实现）。

- 地形真值来自开战 setup；「可破 / 禁飞」等子类在被攻击 / 被踏入前对 AI 未知。
- 规划采用乐观信念（未知障碍视为可破、未知深渊视为可飞）；
  揭晓事件使 ``terrain_version`` 递增，距离表按版本号懒重建。
- 禁制 ``seal``（M3-D07）：子类按攻击类别挡远程；格不可通行（与障碍同属墙）。

纯度纪律（写死）：本模块不得 import FastAPI / SQLAlchemy / pydantic。
"""

from __future__ import annotations

from collections import deque

from app.domain.board_tables import CELL_COUNT, ORTHO_NEIGHBORS

# 地形类型常量（与 formations.yaml 的 type 字段对应）
TERRAIN_OBSTACLE = "obstacle"
TERRAIN_RAVINE = "ravine"
TERRAIN_SEAL = "seal"

# 禁制子类（中文：禁远程物理 / 禁远程法术 / 禁全部远程）
SEAL_SUBTYPE_RANGED_PHYSICAL = "ranged_physical"
SEAL_SUBTYPE_RANGED_MAGIC = "ranged_magic"
SEAL_SUBTYPE_RANGED_ALL = "ranged_all"
SEAL_SUBTYPES: frozenset[str] = frozenset(
    {
        SEAL_SUBTYPE_RANGED_PHYSICAL,
        SEAL_SUBTYPE_RANGED_MAGIC,
        SEAL_SUBTYPE_RANGED_ALL,
    },
)

# 不可达哨兵值（BFS 未触达）
UNREACHABLE = 99


def seal_blocks_attack(subtype: str, attack_kind: str) -> bool:
    """
    判断禁制子类是否挡住该攻击类别。

    参数:
        subtype: ``ranged_physical`` / ``ranged_magic`` / ``ranged_all``。
        attack_kind: 单位 ``attack_kind``（如 ``ranged_physical``）。

    返回:
        bool: True 表示该禁制格阻挡该次远程 LOS。
    """
    # 近战一律不受远程禁制影响（Phase A）
    if not str(attack_kind).startswith("ranged_"):
        return False
    kind = str(subtype or SEAL_SUBTYPE_RANGED_ALL)
    if kind == SEAL_SUBTYPE_RANGED_ALL:
        return True
    if kind == SEAL_SUBTYPE_RANGED_PHYSICAL:
        return attack_kind == "ranged_physical"
    if kind == SEAL_SUBTYPE_RANGED_MAGIC:
        return attack_kind == "ranged_magic"
    # 未知子类：保守按全禁远程（配置校验应已拒绝）
    return True


class TerrainState:
    """
    一场战斗内的地形真值 + 揭晓状态。

    属性:
        obstacle_subtype: cell → ``destructible`` / ``indestructible``（存活障碍）。
        ravine_subtype: cell → ``flyable`` / ``no_fly``。
        seal_subtype: cell → 禁制子类（挡对应远程）。
        seal_mask: 任意禁制格掩码（部署禁停 / 通行墙用）。
        revealed: 已揭晓子类的格集合。
        version: 地形版本号；破障 / 揭晓时 +1，用于距离表懒重建。
    """

    __slots__ = (
        "obstacle_subtype",
        "ravine_subtype",
        "seal_subtype",
        "seal_mask",
        "revealed",
        "version",
    )

    def __init__(self, terrain_cells: list[dict]) -> None:
        """
        参数:
            terrain_cells: ``[{cell, type, subtype}, ...]``（坐标已折算为扁平索引）。
        """
        self.obstacle_subtype: dict[int, str] = {}
        self.ravine_subtype: dict[int, str] = {}
        self.seal_subtype: dict[int, str] = {}
        self.seal_mask = 0
        self.revealed: set[int] = set()
        self.version = 0
        for item in terrain_cells:
            cell = int(item["cell"])
            kind = str(item["type"])
            subtype = str(item.get("subtype", ""))
            if kind == TERRAIN_OBSTACLE:
                self.obstacle_subtype[cell] = subtype or "destructible"
            elif kind == TERRAIN_RAVINE:
                self.ravine_subtype[cell] = subtype or "no_fly"
            elif kind == TERRAIN_SEAL:
                # 缺省 subtype → 禁全部远程（兼容旧数据；正式表须显式写子类）
                seal_sub = subtype or SEAL_SUBTYPE_RANGED_ALL
                self.seal_subtype[cell] = seal_sub
                self.seal_mask |= 1 << cell

    # ------------------------------------------------------------------
    # 信念掩码（供规划器；乐观口径见算法文档 §5.2）
    # ------------------------------------------------------------------

    def obstacle_mask(self) -> int:
        """存活障碍格掩码（无论子类是否已揭晓）。"""
        mask = 0
        for cell in self.obstacle_subtype:
            mask |= 1 << cell
        return mask

    def abyss_mask(self) -> int:
        """深渊格掩码（永远不可停留）。"""
        mask = 0
        for cell in self.ravine_subtype:
            mask |= 1 << cell
        return mask

    def seal_los_mask(self, attack_kind: str) -> int:
        """
        对该攻击类别生效的禁制 LOS 掩码。

        参数:
            attack_kind: 攻击方 ``attack_kind``。
        """
        mask = 0
        for cell, subtype in self.seal_subtype.items():
            if seal_blocks_attack(subtype, attack_kind):
                mask |= 1 << cell
        return mask

    def wall_mask(self, can_fly: bool) -> int:
        """
        「按当前信念不可通行」的格掩码。

        规则:
            - 已揭晓不可破障碍 → 墙。
            - 未揭晓障碍 → 乐观视为可破（不算墙，执行期撞上就打）。
            - 深渊：陆地单位一律视为墙；飞行单位仅「已揭晓禁飞」视为墙。
            - 禁制：一律墙（不可踏入 / 不可停留，M3-D07）。
        """
        mask = 0
        for cell, subtype in self.obstacle_subtype.items():
            if cell in self.revealed and subtype == "indestructible":
                mask |= 1 << cell
        for cell, subtype in self.ravine_subtype.items():
            if not can_fly:
                mask |= 1 << cell
            elif cell in self.revealed and subtype == "no_fly":
                mask |= 1 << cell
        # 禁制格不可进入（与障碍同等硬墙）
        mask |= self.seal_mask
        return mask

    def breakable_mask(self) -> int:
        """「按当前信念可打掉」的障碍掩码（未知 + 已知可破）。"""
        mask = 0
        for cell, subtype in self.obstacle_subtype.items():
            if cell not in self.revealed or subtype == "destructible":
                mask |= 1 << cell
        return mask

    # ------------------------------------------------------------------
    # 揭晓与破坏（返回揭晓结果供事件记录）
    # ------------------------------------------------------------------

    def hit_obstacle(self, cell: int) -> str:
        """
        对障碍结算一次命中的攻击。

        返回:
            str: ``break``（击破移除）或 ``immune``（揭晓不可破）。
        """
        subtype = self.obstacle_subtype.get(cell)
        if subtype is None:
            return "none"
        self.revealed.add(cell)
        self.version += 1
        if subtype == "destructible":
            # 命中一次即破：格恢复普通
            del self.obstacle_subtype[cell]
            return "break"
        return "immune"

    def reveal_ravine(self, cell: int) -> str:
        """
        踏入深渊时揭晓子类。

        返回:
            str: ``flyable``（可飞越）或 ``no_fly``（禁飞，须弹回）。
        """
        subtype = self.ravine_subtype.get(cell, "no_fly")
        if cell not in self.revealed:
            self.revealed.add(cell)
            self.version += 1
        return subtype


class TerrainDistance:
    """
    当前信念地形下的全源步距离表（懒重建）。

    键为 ``terrain_version``；只有破障 / 揭晓才使缓存失效。
    陆地与飞行通行性不同 → 分别缓存两张表。
    """

    __slots__ = ("_version", "_rows_land", "_rows_fly")

    def __init__(self) -> None:
        self._version = -1
        self._rows_land: list[list[int]] = []
        self._rows_fly: list[list[int]] = []

    def rows(self, terrain: TerrainState, can_fly: bool) -> list[list[int]]:
        """
        取当前版本的全源距离表；版本不符时重建。

        乐观口径：未知 / 可破障碍视为可通行（真实清除靠执行期撞上就打）。
        其它单位仍不进入本表（避免每次移子重建）；占位绕行 / 让路由
        ``combat_ai`` 局部软墙 BFS 处理（算法文档 §5.4）。
        """
        if self._version != terrain.version:
            self._rows_land = _build_all_pairs(terrain.wall_mask(can_fly=False))
            self._rows_fly = _build_all_pairs(terrain.wall_mask(can_fly=True))
            self._version = terrain.version
        return self._rows_fly if can_fly else self._rows_land


def _build_all_pairs(wall_mask: int) -> list[list[int]]:
    """对 49 个源各跑一次四邻接 BFS，得到全源步距离表。"""
    rows: list[list[int]] = []
    for src in range(CELL_COUNT):
        dist = [UNREACHABLE] * CELL_COUNT
        if not (wall_mask >> src) & 1:
            dist[src] = 0
            queue = deque([src])
            while queue:
                cur = queue.popleft()
                for nxt in ORTHO_NEIGHBORS[cur]:
                    if dist[nxt] != UNREACHABLE or (wall_mask >> nxt) & 1:
                        continue
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        rows.append(dist)
    return rows
