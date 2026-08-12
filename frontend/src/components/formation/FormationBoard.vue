<script setup lang="ts">
/**
 * 7×7 布阵棋盘：基于通用 BoardGrid（固定格子层 + 棋子加载层）。
 *
 * 坐标口径：左下 (0,0)，x 向右为纵深、y 为横向；屏幕上本方在下、敌方在上。
 * 交互：先在 UnitBench 选中棋子再点合法格落子；点己方棋子选中后可移动。
 */
import { computed } from 'vue'
import BoardGrid from '../board/BoardGrid.vue'
import type { BoardPiece, BoardTerrainCell } from '../board/BoardGrid.vue'
import type {
  BoardMeta,
  FormationTerrainCell,
  UnitPlacement,
} from '../../types/formation'

const props = defineProps<{
  meta: BoardMeta
  units: UnitPlacement[]
  terrain: FormationTerrainCell[]
  /** 当前选中的棋子 uid（Bench 或棋盘上的） */
  selectedUid: string | null
  /** 有效可部署格；缺省回退 board-meta 默认区 */
  deployCells?: [number, number][]
}>()

const emit = defineEmits<{
  /** 点击某格（由父组件决定落子/选中/无效提示） */
  cellClick: [x: number, y: number]
}>()

/** 棋子种类 → 简称 */
const KIND_LABELS: Record<string, string> = {
  main: '本',
  puppet: '傀',
  pet: '宠',
  avatar: '化',
  prop: '器',
}

/** 高亮用部署格：阵法有效区优先 */
const deployCellsResolved = computed(
  () => props.deployCells ?? props.meta.default_deploy_cells,
)

/** 已落棋子 → 棋盘加载层棋子 */
const pieces = computed<BoardPiece[]>(() =>
  props.units.map((unit) => ({
    uid: unit.unit_uid,
    x: unit.x,
    y: unit.y,
    kind: unit.unit_kind,
    side: 0,
    label: KIND_LABELS[unit.unit_kind] ?? unit.unit_kind.charAt(0),
    selected: unit.unit_uid === props.selectedUid,
  })),
)

/** 阵法地形 → 通用地形格（type 字段改名 kind） */
const terrainCells = computed<BoardTerrainCell[]>(() =>
  props.terrain.map((cell) => ({ x: cell.x, y: cell.y, kind: cell.type })),
)
</script>

<template>
  <div class="board-wrap">
    <BoardGrid
      :size="meta.size"
      :zones="meta.zones"
      :deploy-cells="deployCellsResolved"
      :terrain="terrainCells"
      :pieces="pieces"
      interactive
      show-axis
      @cell-click="(x, y) => emit('cellClick', x, y)"
    />
    <el-text type="info" size="small" class="board-legend">
      青绿格 = 可部署区（随阵法变化） · 上方暗红 = 敌方半区 · 中间暗行 =
      中立（默认禁落） · 障/渊/禁 = 阵法地形（不可停留）
    </el-text>
  </div>
</template>

<style scoped>
.board-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 460px;
}
</style>
