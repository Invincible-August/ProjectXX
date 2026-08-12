<script setup lang="ts">
/**
 * 渡劫双维状态面板：威力档 / 次数档 / 预估品阶 / HP。
 */
import { computed } from 'vue'
import type { TribulationSessionPublic } from '../../types/tribulation'
import { weatherLabel } from '../../utils/weatherIcon'
import { shichenLabel } from '../../utils/shichenLabel'

const props = defineProps<{
  session: TribulationSessionPublic
}>()

const progressPct = computed(() => {
  const total = Math.max(1, Number(props.session.strike_total) || 0)
  const done = Number(props.session.strike_done)
  if (!Number.isFinite(done) || total <= 0) return 0
  return Math.min(100, Math.round((done / total) * 100))
})

const hpPct = computed(() => {
  const max = Math.max(1, Number(props.session.hp_max) || 0)
  const cur = Number(props.session.hp_current)
  if (!Number.isFinite(cur) || max <= 0) return 0
  return Math.min(100, Math.round((cur / max) * 100))
})
</script>

<template>
  <el-card shadow="never" class="status-panel">
    <template #header>
      <el-text tag="b">渡劫状态</el-text>
      <el-tag size="small" class="phase-tag">
        {{ session.phase_label_zh || session.phase }}
      </el-tag>
    </template>

    <el-descriptions :column="1" size="small" border>
      <el-descriptions-item label="目标">{{ session.target_label }}</el-descriptions-item>
      <el-descriptions-item v-if="session.projected_grade" label="预估品阶">
        {{ session.projected_grade_name || session.projected_grade }}
      </el-descriptions-item>
      <el-descriptions-item label="本次雷劫">
        {{ session.power_label }} · {{ session.count_label }}（{{ session.strike_total }} 击）
      </el-descriptions-item>
      <el-descriptions-item label="结算天气（开渡前）">
        {{ weatherLabel(session.locked_weather, session.locked_weather_label) }}
        · 时辰 {{ shichenLabel(session.locked_shichen, session.locked_shichen_label) }}
      </el-descriptions-item>
      <el-descriptions-item label="表现天气">
        {{
          session.display_weather_label
            || (session.display_weather === 'tribulation_cloud'
              ? '劫云'
              : weatherLabel(session.display_weather))
        }}
      </el-descriptions-item>
    </el-descriptions>

    <el-alert
      v-if="session.in_cloud_double"
      title="已在劫云内：基础伤害 ×2"
      type="error"
      show-icon
      :closable="false"
      class="warn"
    />

    <div class="bars">
      <el-text size="small">HP {{ session.hp_current }} / {{ session.hp_max }}</el-text>
      <el-progress :percentage="hpPct" :stroke-width="10" status="exception" />
      <el-text size="small">
        进度 {{ session.strike_done }} / {{ session.strike_total }}（{{ progressPct }}%）
      </el-text>
      <el-progress
        :percentage="progressPct"
        :stroke-width="10"
        class="strike-progress"
      />
    </div>

    <el-text
      v-if="session.axis_hints?.power || session.axis_hints?.mitigation"
      size="small"
      type="info"
      class="axis"
    >
      轴提示：{{ session.axis_hints?.power || '' }}
      <template v-if="session.axis_hints?.mitigation">
        · {{ session.axis_hints.mitigation }}
      </template>
    </el-text>
  </el-card>
</template>

<style scoped>
.status-panel :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.phase-tag {
  margin-left: 0.5rem;
}

.warn {
  margin: 0.75rem 0;
}

.bars {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.strike-progress {
  transition: width 0.4s ease;
}

.axis {
  display: block;
  margin-top: 0.5rem;
}
</style>
