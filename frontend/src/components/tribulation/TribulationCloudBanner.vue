<script setup lang="ts">
/**
 * 劫云横幅：锁前天气 vs 劫云表现；云内 ×2 警告。
 */
import type { TribulationSessionPublic } from '../../types/tribulation'
import { weatherLabel } from '../../utils/weatherIcon'

defineProps<{
  session: TribulationSessionPublic
}>()
</script>

<template>
  <el-alert
    type="warning"
    show-icon
    :closable="false"
    class="cloud-banner"
  >
    <template #title>
      开渡后将覆盖半径 {{ session.cloud_radius }} 的劫云
    </template>
    <div class="lines">
      <el-text size="small">
        结算天气（开渡前）：{{
          weatherLabel(session.locked_weather, session.locked_weather_label)
        }}
        ≠ 表现天气（劫云）
      </el-text>
      <el-text v-if="session.in_cloud_double" size="small" type="danger" tag="b">
        已在劫云内开渡：基础伤害 ×2
      </el-text>
    </div>
  </el-alert>
</template>

<style scoped>
.cloud-banner {
  margin-bottom: 0.75rem;
}

.lines {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: 0.25rem;
}
</style>
