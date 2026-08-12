<script setup lang="ts">
/**
 * 修炼区环境修正展示：有效速率、乘区拆解、天气/时辰说明。
 */
import { computed } from 'vue'
import type { IdleDirection } from '../types/idle'
import type { IdleDirectionEnvPreview, IdleEnvBundle } from '../types/idleEnv'

const props = defineProps<{
  idleEnv: IdleEnvBundle | null | undefined
  /** 当前本体方向，决定高亮哪条预览 */
  direction: IdleDirection | string
}>()

const activePreview = computed<IdleDirectionEnvPreview | null>(() => {
  const env = props.idleEnv
  if (!env) return null
  if (props.direction === 'spirit') return env.spirit
  if (props.direction === 'body') return env.body
  if (props.direction === 'crafting') return env.crafting
  // 未修炼时仍展示修灵方向环境，方便玩家择时
  return env.spirit
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

const craftNoteLines = computed(() => {
  const notes = activePreview.value?.weather?.craft_notes
  if (!notes || typeof notes !== 'object') return []
  const labels: Record<string, string> = {
    alchemy: '炼丹',
    smithing: '炼器',
    talisman: '制符',
    puppet: '傀儡',
    array: '阵法',
  }
  return Object.entries(notes).map(([k, v]) => `${labels[k] || k}：${v}`)
})

const sourceLabel = (source: string): string => {
  const map: Record<string, string> = {
    realm_base: '境界基础',
    shichen: '时辰',
    weather: '天气',
    tag_shichen: '灵根/功法·时辰',
    tag_weather: '灵根/功法·天气',
    constitution: '体质',
    equipment: '装备',
    buff_pill: '丹药buff',
    buff_talisman: '符箓buff',
    spirit_eye: '灵眼',
    cave: '洞府',
  }
  return map[source] || source
}
</script>

<template>
  <div v-if="activePreview" class="idle-env">
    <div class="idle-env-rate">
      <el-text size="small" type="info">环境修正后</el-text>
      <el-text tag="b">
        基础 {{ activePreview.base_per_tick }} → 有效
        {{ activePreview.effective_per_tick }}
      </el-text>
      <el-tag :type="multType" size="small" effect="plain">{{ multText }}</el-tag>
    </div>

    <div class="idle-env-breakdown">
      <el-tag
        v-for="(row, idx) in activePreview.breakdown"
        :key="`${row.source}-${row.id}-${idx}`"
        size="small"
        class="bd-tag"
        :type="row.mult > 1 ? 'success' : row.mult < 1 ? 'warning' : 'info'"
        effect="plain"
      >
        {{ sourceLabel(row.source) }}·{{ row.label }} ×{{ row.mult.toFixed(2) }}
      </el-tag>
    </div>

    <el-collapse class="idle-env-collapse">
      <el-collapse-item title="时辰 / 天气说明" name="catalog">
        <div class="catalog-block">
          <el-text tag="b" size="small">
            {{ activePreview.shichen.label }}
          </el-text>
          <el-text v-if="activePreview.shichen.summary" size="small" class="line">
            {{ activePreview.shichen.summary }}
          </el-text>
          <el-text v-if="activePreview.shichen.idle_note" size="small" type="success" class="line">
            修炼：{{ activePreview.shichen.idle_note }}
          </el-text>
          <el-text
            v-if="activePreview.shichen.spawn_bias_note"
            size="small"
            type="warning"
            class="line"
          >
            妖兽：{{ activePreview.shichen.spawn_bias_note }}
          </el-text>
        </div>
        <el-divider />
        <div class="catalog-block">
          <el-text tag="b" size="small">
            {{ activePreview.weather.label }}
          </el-text>
          <el-text v-if="activePreview.weather.summary" size="small" class="line">
            {{ activePreview.weather.summary }}
          </el-text>
          <el-text v-if="activePreview.weather.idle_note" size="small" type="success" class="line">
            修炼：{{ activePreview.weather.idle_note }}
          </el-text>
          <el-text
            v-if="activePreview.weather.spawn_bias_note"
            size="small"
            type="warning"
            class="line"
          >
            妖兽：{{ activePreview.weather.spawn_bias_note }}
          </el-text>
          <el-text
            v-for="(line, i) in craftNoteLines"
            :key="i"
            size="small"
            class="line"
          >
            {{ line }}
          </el-text>
          <el-text
            v-if="activePreview.weather.tribulation_note"
            size="small"
            type="danger"
            class="line"
          >
            渡劫：{{ activePreview.weather.tribulation_note }}
          </el-text>
        </div>
        <el-text
          v-if="idleEnv?.tags_applied?.length"
          size="small"
          type="info"
          class="tags"
        >
          已生效标签：{{ idleEnv.tags_applied.join('、') }}
        </el-text>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.idle-env {
  margin: 0.5rem 0 0.75rem;
  padding: 0.5rem 0.65rem;
  border-radius: 6px;
  background: rgba(64, 158, 255, 0.06);
  border: 1px solid rgba(64, 158, 255, 0.15);
}

.idle-env-rate {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.65rem;
  margin-bottom: 0.4rem;
}

.idle-env-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.35rem;
}

.bd-tag {
  font-variant-numeric: tabular-nums;
}

.idle-env-collapse {
  --el-collapse-header-height: 32px;
  border: none;
}

.idle-env-collapse :deep(.el-collapse-item__header) {
  background: transparent;
  border: none;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.idle-env-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border: none;
}

.catalog-block {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.line {
  display: block;
  line-height: 1.45;
}

.tags {
  display: block;
  margin-top: 0.5rem;
}
</style>
