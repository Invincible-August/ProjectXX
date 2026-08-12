<script setup lang="ts">
/**
 * 道主之争晋级表（tournament bracket）：
 * 列序 early → semi → final → lord；人数不足时只渲染已生成场次（1 人仅道主战、2 人决赛等）。
 */
import { computed } from 'vue'
import type { DaoContestMatchPublic } from '../../types/daoLord'

const props = defineProps<{
  matches: DaoContestMatchPublic[]
  meCharacterId?: number | null
  /** 当前阶段本道进行中的场次（整备/直播），用于高亮 */
  highlightMatchIds?: number[]
}>()

const emit = defineEmits<{
  select: [match: DaoContestMatchPublic]
}>()

const highlightSet = computed(
  () => new Set(props.highlightMatchIds || []),
)

interface RoundColumn {
  key: string
  title: string
  kind: string
  matches: DaoContestMatchPublic[]
}

const KIND_ORDER: Record<string, number> = {
  early: 1,
  semi: 2,
  final: 3,
  lord: 4,
}

const KIND_TITLE: Record<string, string> = {
  early: '淘汰赛',
  semi: '半决赛',
  final: '决赛',
  lord: '道主决战',
}

const columns = computed<RoundColumn[]>(() => {
  const list = [...(props.matches || [])]
  const byKey = new Map<string, DaoContestMatchPublic[]>()
  for (const m of list) {
    const key =
      m.round_kind === 'lord'
        ? 'lord'
        : `${m.round_kind}-${m.round_index}`
    if (!byKey.has(key)) byKey.set(key, [])
    byKey.get(key)!.push(m)
  }
  const cols: RoundColumn[] = [...byKey.entries()].map(([key, matches]) => {
    const sample = matches[0]
    const kind = sample?.round_kind || 'early'
    let title = KIND_TITLE[kind] || sample?.round_kind_label || kind
    if (kind !== 'lord' && sample && sample.round_index > 0) {
      // 多轮淘汰时区分第 N 轮
      const earlyCols = [...byKey.keys()].filter((k) => k.startsWith('early-'))
      if (kind === 'early' && earlyCols.length > 1) {
        title = `${title} · 第 ${sample.round_index} 轮`
      }
    }
    matches.sort((a, b) => a.bracket_slot - b.bracket_slot || a.id - b.id)
    return { key, title, kind, matches }
  })
  cols.sort((a, b) => {
    const ka = KIND_ORDER[a.kind] ?? 99
    const kb = KIND_ORDER[b.kind] ?? 99
    if (ka !== kb) return ka - kb
    const ia = a.matches[0]?.round_index ?? 0
    const ib = b.matches[0]?.round_index ?? 0
    return ia - ib
  })
  return cols
})

/** 列内垂直间距：越靠后轮次，槽位越少、卡片越高间距 */
function slotStyle(col: RoundColumn, index: number): Record<string, string> {
  const n = Math.max(1, col.matches.length)
  // 用较大 margin 拉开，形成晋级树视觉
  const gap = Math.max(12, Math.round(48 / n))
  return {
    marginTop: index === 0 ? '0' : `${gap}px`,
  }
}

function sideName(
  side?: { character_id: number; name?: string } | null,
): string {
  if (!side) return '轮空'
  return side.name || `#${side.character_id}`
}

function isMe(side?: { character_id: number } | null): boolean {
  return Boolean(
    props.meCharacterId != null &&
      side?.character_id === props.meCharacterId,
  )
}

function statusHint(m: DaoContestMatchPublic): string {
  if (m.resolve_reason === 'bye') return '轮空晋级'
  if (m.live_active || m.status === 'playing') {
    if (isMe(m.side_a) || isMe(m.side_b)) return '直播中'
    return '同轮直播'
  }
  // 同轮会有多场 adjusting（半决两场 / 跨道并行）；只把本人场标成「整备中」
  if (m.status === 'adjusting') {
    if (isMe(m.side_a) || isMe(m.side_b)) return '整备中'
    if (highlightSet.value.has(m.id)) return '同轮整备'
    return '待赛'
  }
  if (m.status === 'pending') return '待开打'
  if (m.status === 'finished' || m.winner_character_id) return '已结束'
  return m.status || '—'
}

function isBye(m: DaoContestMatchPublic): boolean {
  return m.resolve_reason === 'bye' || !m.side_b
}

function onClick(m: DaoContestMatchPublic): void {
  emit('select', m)
}
</script>

<template>
  <div class="bracket-board">
    <div class="head">
      <el-text tag="b" class="title">晋级对阵表</el-text>
      <el-text type="info" size="small">
        按实际人数动态生成（1 人直进道主战 · 2 人决赛 · 更多半决/淘汰）；点击场次看直播或回放
      </el-text>
    </div>
    <div v-if="!columns.length" class="empty">对阵尚未生成</div>
    <div v-else class="tree">
      <div
        v-for="(col, colIdx) in columns"
        :key="col.key"
        class="round"
        :class="[`kind-${col.kind}`, { last: colIdx === columns.length - 1 }]"
      >
        <div class="round-title">{{ col.title }}</div>
        <div class="slots">
          <button
            v-for="(m, idx) in col.matches"
            :key="m.id"
            type="button"
            class="match"
            :class="{
              live: m.live_active || m.status === 'playing',
              mine: isMe(m.side_a) || isMe(m.side_b),
              bye: isBye(m),
              done: Boolean(m.winner_character_id),
              active: highlightSet.has(m.id) && (isMe(m.side_a) || isMe(m.side_b)),
            }"
            :style="slotStyle(col, idx)"
            @click="onClick(m)"
          >
            <div
              class="fighter"
              :class="{
                win: m.winner_character_id === m.side_a?.character_id,
                me: isMe(m.side_a),
              }"
            >
              {{ sideName(m.side_a) }}
            </div>
            <div
              v-if="!isBye(m)"
              class="fighter"
              :class="{
                win: m.winner_character_id === m.side_b?.character_id,
                me: isMe(m.side_b),
              }"
            >
              {{ sideName(m.side_b) }}
            </div>
            <div class="foot">
              <span class="status">{{ statusHint(m) }}</span>
              <span v-if="m.winner_character_id && !isBye(m)" class="adv">
                → {{ m.winner_name || '晋级' }}
              </span>
            </div>
          </button>
        </div>
        <div v-if="colIdx < columns.length - 1" class="connector" aria-hidden="true" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bracket-board {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.head {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.title {
  font-size: 1rem;
}
.empty {
  color: var(--el-text-color-secondary);
  padding: 1rem 0;
}
.tree {
  display: flex;
  gap: 0;
  overflow-x: auto;
  padding: 0.5rem 0 1rem;
  align-items: stretch;
  min-height: 220px;
}
.round {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 168px;
  padding: 0 1.25rem 0 0.25rem;
  justify-content: center;
}
.round-title {
  position: absolute;
  top: 0;
  left: 0.25rem;
  font-weight: 700;
  font-size: 0.8rem;
  letter-spacing: 0.02em;
  color: var(--el-text-color-regular);
}
.slots {
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  flex: 1;
  padding-top: 1.6rem;
  min-height: 180px;
}
.match {
  text-align: left;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  border-radius: 4px;
  padding: 0.45rem 0.6rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
}
.match:hover {
  border-color: var(--el-color-primary);
}
.match.live {
  border-color: var(--el-color-danger);
  box-shadow: 0 0 0 1px var(--el-color-danger-light-5);
}
.match.mine {
  outline: 2px solid var(--el-color-primary-light-5);
}
.match.active {
  border-color: var(--el-color-warning);
  box-shadow: 0 0 0 1px var(--el-color-warning-light-5);
}
.match.bye {
  opacity: 0.85;
  border-style: dashed;
}
.fighter {
  padding: 0.28rem 0.2rem;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--el-border-color-lighter);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fighter:last-of-type {
  border-bottom: none;
}
.fighter.win {
  font-weight: 700;
  color: var(--el-color-success);
}
.fighter.me {
  color: var(--el-color-primary);
}
.foot {
  display: flex;
  justify-content: space-between;
  gap: 0.35rem;
  margin-top: 0.25rem;
  font-size: 0.7rem;
  color: var(--el-text-color-secondary);
}
.adv {
  color: var(--el-color-success);
}
/* 列间连接线（简易晋级树） */
.connector {
  position: absolute;
  right: 0;
  top: 50%;
  width: 1.1rem;
  height: 2px;
  background: var(--el-border-color);
}
.connector::before,
.connector::after {
  content: '';
  position: absolute;
  right: 0;
  width: 2px;
  height: 28px;
  background: var(--el-border-color);
}
.connector::before {
  top: -28px;
}
.connector::after {
  top: 0;
}
.round.kind-lord .round-title {
  color: var(--el-color-warning);
}
</style>
