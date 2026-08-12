<script setup lang="ts">
/**
 * 通用 7×7 棋盘（固定格子层 + 棋子加载层）。
 *
 * 设计要点：
 * - 格子层恒定渲染 size×size，不随棋子/地形变化重建 DOM；
 * - 棋子层绝对定位，left/top 过渡 = 移动动画；
 * - 可选 fx：路径高亮、行动/攻击浮标、攻击连线；
 * - 屏幕方向：本方半区（x 小）在下、敌方半区（x 大）在上。
 */
import { computed } from 'vue'

/** 棋盘三区（x 轴划分；与后端 board-meta 口径一致） */
export interface BoardZones {
  own_x: number[]
  neutral_x: number[]
  enemy_x: number[]
}

/** 棋盘地形格（大类：obstacle / ravine / seal） */
export interface BoardTerrainCell {
  x: number
  y: number
  kind: string
}

/** 加载到棋盘上的棋子 */
export interface BoardPiece {
  /** 唯一 key（动画追踪用） */
  uid: string
  x: number
  y: number
  /** 圆形棋子内的单字标签（本 / 傀 / 敌 …） */
  label: string
  /** 棋子种类（决定己方配色） */
  kind: string
  /** 0 = 己方 / 进攻方；1 = 敌方 / 防守方 */
  side: number
  /** 当前 / 最大生命（都提供时棋子下方渲染血条） */
  hp?: number
  max_hp?: number
  /** 是否处于选中态（金色描边） */
  selected?: boolean
  /** 战报回放高亮：行动者 / 受击目标 */
  highlight?: 'actor' | 'target' | 'hit' | null
}

/** 格子高亮色调 */
export type BoardCellTone = 'path' | 'from' | 'to' | 'target'

/** 浮标色调 */
export type BoardTagTone = 'act' | 'move' | 'atk' | 'hit' | 'miss' | 'death'

/** 战报演出叠加层 */
export interface BoardFx {
  cells?: { x: number; y: number; tone: BoardCellTone }[]
  tags?: { x: number; y: number; text: string; tone: BoardTagTone }[]
  beam?: {
    fromX: number
    fromY: number
    toX: number
    toY: number
    tone: 'attack' | 'move'
  } | null
}

const props = withDefaults(
  defineProps<{
    /** 棋盘边长（恒为 7，仅保留可配置口径） */
    size?: number
    /** 三区划分；缺省用 M3 默认（本方 0-2 / 中立 3 / 敌方 4-6） */
    zones?: BoardZones
    /** 需要高亮的可部署格（布阵编辑器用） */
    deployCells?: [number, number][]
    /** 地形格 */
    terrain?: BoardTerrainCell[]
    /** 棋子列表（加载层） */
    pieces?: BoardPiece[]
    /** 战报演出叠加（路径 / 浮标 / 连线） */
    fx?: BoardFx | null
    /** 是否可点击格子（布阵编辑器 true / 战报回放 false） */
    interactive?: boolean
    /** 是否显示坐标轴标签 */
    showAxis?: boolean
  }>(),
  {
    size: 7,
    zones: () => ({ own_x: [0, 1, 2], neutral_x: [3], enemy_x: [4, 5, 6] }),
    deployCells: () => [],
    terrain: () => [],
    pieces: () => [],
    fx: null,
    interactive: false,
    showAxis: false,
  },
)

const emit = defineEmits<{
  /** 点击某格（回传游戏坐标 x, y；仅 interactive 时有意义） */
  cellClick: [x: number, y: number]
}>()

/** 屏幕行序：从上到下 = x 从大到小（敌方在上、本方在下） */
const rowXs = computed(() => {
  const list: number[] = []
  for (let x = props.size - 1; x >= 0; x -= 1) list.push(x)
  return list
})

/** 屏幕列序：从左到右 = y 从小到大 */
const colYs = computed(() => {
  const list: number[] = []
  for (let y = 0; y < props.size; y += 1) list.push(y)
  return list
})

/** 可部署格集合（字符串 key 查询） */
const deploySet = computed(
  () => new Set(props.deployCells.map(([x, y]) => `${x},${y}`)),
)

/** 地形格映射 */
const terrainMap = computed(() => {
  const map = new Map<string, BoardTerrainCell>()
  for (const cell of props.terrain) map.set(`${cell.x},${cell.y}`, cell)
  return map
})

/** 格子 fx 映射（后写覆盖前写） */
const cellFxMap = computed(() => {
  const map = new Map<string, BoardCellTone>()
  for (const cell of props.fx?.cells || []) {
    map.set(`${cell.x},${cell.y}`, cell.tone)
  }
  return map
})

/** 地形大类 → 显示字符（子类未揭晓不泄露） */
const TERRAIN_MARKS: Record<string, string> = {
  obstacle: '障',
  ravine: '渊',
  seal: '禁',
}

/** 格所属分区样式 */
function zoneClass(x: number): string {
  if (props.zones.neutral_x.includes(x)) return 'cell-neutral'
  if (props.zones.enemy_x.includes(x)) return 'cell-enemy'
  return 'cell-own'
}

function terrainAt(x: number, y: number): BoardTerrainCell | undefined {
  return terrainMap.value.get(`${x},${y}`)
}

function cellFxTone(x: number, y: number): BoardCellTone | undefined {
  return cellFxMap.value.get(`${x},${y}`)
}

/** 游戏坐标 → 覆盖层百分比定位 */
function cellOverlayStyle(x: number, y: number): Record<string, string> {
  const col = y
  const row = props.size - 1 - x
  return {
    left: `${(col / props.size) * 100}%`,
    top: `${(row / props.size) * 100}%`,
    width: `${100 / props.size}%`,
    height: `${100 / props.size}%`,
  }
}

/** 棋子加载层定位：游戏坐标 → 覆盖层百分比（left/top 变化触发移动过渡） */
function pieceStyle(piece: BoardPiece): Record<string, string> {
  return cellOverlayStyle(piece.x, piece.y)
}

/** 攻击/移动连线：两端格心 → SVG line */
const beamStyle = computed(() => {
  const beam = props.fx?.beam
  if (!beam) return null
  const n = props.size
  const x1 = ((beam.fromY + 0.5) / n) * 100
  const y1 = ((n - 1 - beam.fromX + 0.5) / n) * 100
  const x2 = ((beam.toY + 0.5) / n) * 100
  const y2 = ((n - 1 - beam.toX + 0.5) / n) * 100
  return { x1: `${x1}%`, y1: `${y1}%`, x2: `${x2}%`, y2: `${y2}%`, tone: beam.tone }
})

/** 血条宽度与配色（随剩余比例从绿变红） */
function hpStyle(piece: BoardPiece): Record<string, string> {
  const ratio =
    piece.max_hp && piece.max_hp > 0
      ? Math.max(0, Math.min(1, (piece.hp ?? 0) / piece.max_hp))
      : 0
  const color = ratio > 0.5 ? '#5cb85c' : ratio > 0.25 ? '#e6a23c' : '#e05252'
  return { width: `${ratio * 100}%`, background: color }
}
</script>

<template>
  <div class="bg-root">
    <!-- 左侧 x 轴标签（可选） -->
    <div v-if="showAxis" class="bg-axis-col">
      <div v-for="x in rowXs" :key="`ax-${x}`" class="bg-axis-cell">{{ x }}</div>
      <!-- 占位对齐底部 y 轴行 -->
      <div class="bg-axis-cell bg-axis-corner" />
    </div>

    <div class="bg-main">
      <div class="bg-stage">
        <!-- 固定格子层：恒定 size×size，永不因棋子变化重建 -->
        <div
          class="bg-cells"
          :style="{ gridTemplateColumns: `repeat(${size}, 1fr)` }"
        >
          <template v-for="x in rowXs" :key="`row-${x}`">
            <component
              :is="interactive ? 'button' : 'div'"
              v-for="y in colYs"
              :key="`cell-${x}-${y}`"
              :type="interactive ? 'button' : undefined"
              class="bg-cell"
              :class="[
                zoneClass(x),
                {
                  interactive,
                  deployable: deploySet.has(`${x},${y}`),
                  [`fx-${cellFxTone(x, y)}`]: Boolean(cellFxTone(x, y)),
                },
              ]"
              @click="interactive && emit('cellClick', x, y)"
            >
              <span v-if="terrainAt(x, y)" class="bg-terrain">
                {{ TERRAIN_MARKS[terrainAt(x, y)!.kind] ?? '?' }}
              </span>
            </component>
          </template>
        </div>

        <!-- 攻击/移动连线 -->
        <svg v-if="beamStyle" class="bg-beam" aria-hidden="true">
          <line
            :x1="beamStyle.x1"
            :y1="beamStyle.y1"
            :x2="beamStyle.x2"
            :y2="beamStyle.y2"
            class="bg-beam-line"
            :class="`beam-${beamStyle.tone}`"
          />
        </svg>

        <!-- 棋子加载层：绝对定位覆盖；left/top 过渡 = 移动动画 -->
        <TransitionGroup name="piece" tag="div" class="bg-pieces">
          <div
            v-for="piece in pieces"
            :key="piece.uid"
            class="bg-piece"
            :class="{
              'is-actor': piece.highlight === 'actor',
              'is-target': piece.highlight === 'target',
              'is-hit': piece.highlight === 'hit',
            }"
            :style="pieceStyle(piece)"
          >
            <span
              class="bg-token"
              :class="[
                piece.side === 1 ? 'token-enemy' : `token-${piece.kind}`,
                { 'token-selected': piece.selected },
              ]"
            >
              {{ piece.label }}
            </span>
            <span
              v-if="piece.max_hp && piece.max_hp > 0"
              class="bg-hp-track"
            >
              <i class="bg-hp-fill" :style="hpStyle(piece)" />
            </span>
          </div>
        </TransitionGroup>

        <!-- 浮标：行动 / 移动 / 攻击 / 伤害 -->
        <div class="bg-tags">
          <div
            v-for="(tag, idx) in fx?.tags || []"
            :key="`tag-${idx}-${tag.x}-${tag.y}-${tag.text}`"
            class="bg-tag"
            :class="`tag-${tag.tone}`"
            :style="cellOverlayStyle(tag.x, tag.y)"
          >
            {{ tag.text }}
          </div>
        </div>
      </div>

      <!-- 底部 y 轴标签（可选） -->
      <div
        v-if="showAxis"
        class="bg-axis-row"
        :style="{ gridTemplateColumns: `repeat(${size}, 1fr)` }"
      >
        <div v-for="y in colYs" :key="`ay-${y}`" class="bg-axis-cell">
          {{ y }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bg-root {
  display: flex;
  gap: 4px;
  width: 100%;
}

.bg-axis-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bg-axis-col .bg-axis-cell {
  flex: 1;
}

.bg-axis-corner {
  flex: 0 0 16px;
}

.bg-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

/* 舞台：格子层 + 棋子层的公共定位容器（深色底板） */
.bg-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: #12121c;
  border-radius: 10px;
  padding: 6px;
  box-sizing: border-box;
}

.bg-cells {
  display: grid;
  gap: 4px;
  width: 100%;
  height: 100%;
}

.bg-cell {
  border: 1px solid #262636;
  border-radius: 6px;
  background: #1a1a28;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  min-width: 0;
  min-height: 0;
  transition:
    box-shadow 0.15s ease,
    background 0.2s ease,
    border-color 0.2s ease;
}

/* 分区着色：敌方偏暗红、中立更暗、本方中性 */
.cell-enemy {
  background: #251722;
  border-color: #3a2230;
}

.cell-neutral {
  background: #14141e;
  border-color: #20202e;
}

.cell-own {
  background: #1a1a28;
}

/* 可部署高亮：青绿描边 */
.deployable {
  background: #14262e;
  border-color: #2a5f66;
}

/* 战报路径/落点高亮 */
.fx-path {
  background: #1e2a3a !important;
  border-color: #3d6a8a !important;
  box-shadow: inset 0 0 0 1px rgba(90, 160, 210, 0.35);
}

.fx-from {
  background: #2a2a1a !important;
  border-color: #8a7a3d !important;
}

.fx-to {
  background: #1a2e28 !important;
  border-color: #3d8a6a !important;
  box-shadow: inset 0 0 0 1px rgba(80, 200, 150, 0.4);
}

.fx-target {
  background: #2e1a1a !important;
  border-color: #8a3d3d !important;
  box-shadow: inset 0 0 0 1px rgba(220, 100, 90, 0.45);
}

.bg-cell.interactive {
  cursor: pointer;
}

.bg-cell.interactive:hover {
  box-shadow: 0 0 0 2px #3f88c5 inset;
}

.bg-cell.interactive.cell-neutral,
.bg-cell.interactive.cell-enemy {
  cursor: not-allowed;
}

.bg-terrain {
  font-size: clamp(10px, 2.2vw, 14px);
  color: #8b8ba0;
  user-select: none;
}

.bg-beam {
  position: absolute;
  inset: 6px;
  width: calc(100% - 12px);
  height: calc(100% - 12px);
  pointer-events: none;
  z-index: 2;
  overflow: visible;
}

.bg-beam-line {
  stroke-width: 2.5;
  stroke-linecap: round;
  fill: none;
}

.beam-attack {
  stroke: #e07060;
  stroke-dasharray: 5 4;
  animation: beam-pulse 0.55s ease-in-out infinite alternate;
}

.beam-move {
  stroke: #6aa8d8;
  stroke-dasharray: 4 5;
  opacity: 0.85;
}

@keyframes beam-pulse {
  from {
    opacity: 0.55;
  }
  to {
    opacity: 1;
  }
}

/* 棋子加载层 */
.bg-pieces {
  position: absolute;
  inset: 6px;
  pointer-events: none;
  z-index: 3;
}

.bg-piece {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  /* left/top 过渡 = 棋子移动动画 */
  transition:
    left 0.4s ease,
    top 0.4s ease,
    opacity 0.3s ease,
    transform 0.25s ease;
}

.bg-token {
  width: 68%;
  aspect-ratio: 1;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(11px, 2.4vw, 15px);
  font-weight: 700;
  color: #fff;
  user-select: none;
  box-shadow:
    0 2px 6px rgba(0, 0, 0, 0.45),
    0 0 0 1px rgba(255, 255, 255, 0.08) inset;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

/* 己方按种类配色；敌方统一红 */
.token-main {
  background: #1f9e8e;
}

.token-puppet {
  background: #7d8291;
}

.token-pet {
  background: #c9930f;
}

.token-avatar {
  background: #8b5fd6;
}

.token-prop {
  background: #a06a3c;
}

.token-enemy {
  background: #c8453e;
}

.token-selected {
  box-shadow:
    0 0 0 2px #f0b429,
    0 2px 6px rgba(0, 0, 0, 0.45);
}

.is-actor .bg-token {
  box-shadow:
    0 0 0 2px #f0c040,
    0 2px 8px rgba(0, 0, 0, 0.5);
  animation: actor-pulse 0.7s ease-in-out infinite alternate;
}

.is-target .bg-token {
  box-shadow:
    0 0 0 2px #e07060,
    0 2px 8px rgba(0, 0, 0, 0.5);
}

.is-hit .bg-token {
  animation: hit-shake 0.35s ease;
}

@keyframes actor-pulse {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.08);
  }
}

@keyframes hit-shake {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-3px);
  }
  75% {
    transform: translateX(3px);
  }
}

/* 血条 */
.bg-hp-track {
  width: 62%;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.14);
  overflow: hidden;
}

.bg-hp-fill {
  display: block;
  height: 100%;
  border-radius: 2px;
  transition: width 0.25s ease;
}

.bg-tags {
  position: absolute;
  inset: 6px;
  pointer-events: none;
  z-index: 4;
}

.bg-tag {
  position: absolute;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 2%;
  font-size: clamp(9px, 1.8vw, 11px);
  font-weight: 700;
  line-height: 1.2;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.75);
  animation: tag-rise 0.45s ease-out;
  white-space: nowrap;
}

.tag-act {
  color: #f0c040;
}

.tag-move {
  color: #7ec0ea;
}

.tag-atk {
  color: #f0a090;
}

.tag-hit {
  color: #ff7a6a;
}

.tag-miss {
  color: #9aa0b0;
}

.tag-death {
  color: #ff5a5a;
}

@keyframes tag-rise {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 入场（落子）与离场（阵亡）动画 */
.piece-enter-from {
  opacity: 0;
}

.piece-leave-to {
  opacity: 0;
}

.piece-leave-active {
  transition: opacity 0.4s ease;
}

.bg-axis-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #6b6b80;
  min-width: 14px;
}

.bg-axis-row {
  display: grid;
  gap: 4px;
  padding: 0 6px;
}

.bg-axis-row .bg-axis-cell {
  min-height: 16px;
}
</style>
