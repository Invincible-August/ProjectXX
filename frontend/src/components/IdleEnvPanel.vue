<script setup lang="ts">
/**
 * 修炼区环境修正：一行展示基础→有效；明细与说明仅悬停 i 时展开。
 */
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import type { IdleDirection } from '../types/idle'
import type { IdleDirectionEnvPreview, IdleEnvBundle } from '../types/idleEnv'
import {
  computeEffectivePerTick,
  idleSourceLabel,
  multFromBreakdown,
} from '../utils/idleRateClient'

const props = defineProps<{
  idleEnv: IdleEnvBundle | null | undefined
  /** 世界轮询预览（实时时辰/天气） */
  worldIdlePreview?: IdleEnvBundle | null
  /** 当前本体方向，决定高亮哪条预览 */
  direction: IdleDirection | string
}>()

function directionKey(dir: string): 'spirit' | 'body' | 'crafting' | 'sect_mining' {
  if (dir === 'body' || dir === 'crafting' || dir === 'sect_mining' || dir === 'spirit') {
    return dir
  }
  return 'spirit'
}

const gainNoun = computed(() => {
  const d = props.direction
  if (d === 'body') return '淬体度'
  if (d === 'crafting') return '制造业经验'
  if (d === 'sect_mining') return '个人灵石'
  return '修为'
})

const activePreview = computed<IdleDirectionEnvPreview | null>(() => {
  const key = directionKey(String(props.direction || 'spirit'))
  const charP = props.idleEnv?.[key] ?? null
  const worldP = props.worldIdlePreview?.[key] ?? null
  // 未挂机时仍展示修灵环境，方便择时
  const fallbackChar = props.idleEnv?.spirit ?? null
  const fallbackWorld = props.worldIdlePreview?.spirit ?? null
  const baseChar = charP ?? (key === 'spirit' ? fallbackChar : charP)
  const baseWorld = worldP ?? (key === 'spirit' ? fallbackWorld : worldP)

  if (!baseChar && !baseWorld) return null
  if (!baseWorld) return baseChar
  if (!baseChar) return baseWorld

  const shichenId = baseWorld.shichen?.id
  const weatherId = baseWorld.weather?.id
  const effective = computeEffectivePerTick(
    baseChar.base_per_tick,
    baseWorld,
    baseChar,
    shichenId,
    weatherId,
  )
  const base = Math.max(0, Math.floor(Number(baseChar.base_per_tick) || 0))
  const totalMult = base > 0 ? effective / base : baseWorld.total_mult

  // 拆解：时辰/天气取世界实时；标签与通道取角色包
  const liveBreakdown = [
    ...(baseChar.breakdown || []).filter(
      (r) => r.source !== 'shichen' && r.source !== 'weather',
    ),
  ]
  const shichenRow = (baseWorld.breakdown || []).find((r) => r.source === 'shichen')
  const weatherRow = (baseWorld.breakdown || []).find((r) => r.source === 'weather')
  if (shichenRow) liveBreakdown.unshift(shichenRow)
  else {
    liveBreakdown.unshift({
      source: 'shichen',
      id: String(shichenId || ''),
      label: baseWorld.shichen.label,
      mult: multFromBreakdown(baseWorld, 'shichen'),
    })
  }
  if (weatherRow) liveBreakdown.splice(1, 0, weatherRow)
  else {
    liveBreakdown.splice(1, 0, {
      source: 'weather',
      id: String(weatherId || ''),
      label: baseWorld.weather.label,
      mult: multFromBreakdown(baseWorld, 'weather'),
    })
  }

  return {
    base_per_tick: baseChar.base_per_tick,
    effective_per_tick: effective,
    total_mult: Number.isFinite(totalMult) ? totalMult : baseChar.total_mult,
    breakdown: liveBreakdown,
    shichen: baseWorld.shichen,
    weather: baseWorld.weather,
  }
})

const multText = computed(() => {
  const p = activePreview.value
  if (!p) return ''
  return `×${p.total_mult.toFixed(2)}`
})

const multType = computed(() => {
  const m = activePreview.value?.total_mult ?? 1
  if (m > 1.02) return 'success'
  if (m < 0.98) return 'danger'
  return 'info'
})

const sourceLabel = (source: string): string => idleSourceLabel(source)

/** 时辰/天气修炼说明（有则展示） */
const envNotes = computed(() => {
  const p = activePreview.value
  if (!p) return [] as { title: string; text: string }[]
  const notes: { title: string; text: string }[] = []
  const s = p.shichen
  const w = p.weather
  if (s?.idle_note) {
    notes.push({ title: `时辰 · ${s.label || s.id}`, text: s.idle_note })
  } else if (s?.summary) {
    notes.push({ title: `时辰 · ${s.label || s.id}`, text: s.summary })
  }
  if (w?.idle_note) {
    notes.push({ title: `天气 · ${w.label || w.id}`, text: w.idle_note })
  } else if (w?.summary) {
    notes.push({ title: `天气 · ${w.label || w.id}`, text: w.summary })
  }
  return notes
})
</script>

<template>
  <div v-if="activePreview" class="idle-env">
    <div class="idle-env-rate">
      <el-text size="small">
        环境修正 · {{ gainNoun }}
        <el-text tag="b" size="small">
          基础 {{ activePreview.base_per_tick }} → 有效
          {{ activePreview.effective_per_tick }}
        </el-text>
      </el-text>
      <el-tag :type="multType" size="small" effect="plain">{{ multText }}</el-tag>
      <el-tooltip placement="top" :show-after="200" effect="light" popper-class="idle-env-tip">
        <template #content>
          <div class="tip-body">
            <div class="tip-title">加成拆解</div>
            <ul class="tip-list">
              <li
                v-for="(row, idx) in activePreview.breakdown"
                :key="`${row.source}-${row.id}-${idx}`"
                class="tip-row"
              >
                <span class="tip-label">
                  {{ sourceLabel(row.source) }}·{{ row.label }}
                </span>
                <span
                  class="tip-mult"
                  :class="{
                    up: row.mult > 1.001,
                    down: row.mult < 0.999,
                  }"
                >
                  ×{{ row.mult.toFixed(2) }}
                </span>
              </li>
            </ul>
            <template v-if="envNotes.length">
              <div class="tip-title tip-title-gap">说明</div>
              <div v-for="(n, i) in envNotes" :key="i" class="tip-note">
                <div class="tip-note-title">{{ n.title }}</div>
                <div class="tip-note-text">{{ n.text }}</div>
              </div>
            </template>
          </div>
        </template>
        <button type="button" class="idle-env-info" aria-label="查看加成说明">
          <el-icon :size="14"><InfoFilled /></el-icon>
        </button>
      </el-tooltip>
    </div>
  </div>
</template>

<style scoped>
.idle-env {
  margin: 0.35rem 0 0.5rem;
}

.idle-env-rate {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem 0.45rem;
}

.idle-env-info {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.15rem;
  height: 1.15rem;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--el-color-info);
  cursor: help;
  vertical-align: middle;
}

.idle-env-info:hover {
  color: var(--el-color-primary);
}
</style>

<!-- tooltip 挂到 body，需非 scoped -->
<style>
.idle-env-tip {
  max-width: 18rem;
  padding: 0.55rem 0.7rem !important;
  line-height: 1.4;
}

.idle-env-tip .tip-body {
  color: var(--el-text-color-primary);
  font-size: 12px;
}

.idle-env-tip .tip-title {
  font-weight: 600;
  margin-bottom: 0.35rem;
}

.idle-env-tip .tip-title-gap {
  margin-top: 0.55rem;
}

.idle-env-tip .tip-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.idle-env-tip .tip-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}

.idle-env-tip .tip-label {
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.idle-env-tip .tip-mult {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-secondary);
}

.idle-env-tip .tip-mult.up {
  color: var(--el-color-success);
}

.idle-env-tip .tip-mult.down {
  color: var(--el-color-warning);
}

.idle-env-tip .tip-note {
  margin-top: 0.25rem;
}

.idle-env-tip .tip-note-title {
  color: var(--el-text-color-secondary);
  margin-bottom: 0.1rem;
}

.idle-env-tip .tip-note-text {
  color: var(--el-text-color-regular);
}
</style>
