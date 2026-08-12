<script setup lang="ts">
/**
 * 化身体力与日行动（元婴起；未解锁不渲染空槽）。
 */
import type { AvatarStaminaPanel } from '../../types/avatar'

defineProps<{
  stamina: AvatarStaminaPanel
}>()
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">化身体力</el-text>
    </template>

    <el-progress
      :percentage="
        stamina.stamina_cap > 0
          ? Math.min(100, Math.round((stamina.stamina / stamina.stamina_cap) * 100))
          : 0
      "
      :stroke-width="12"
    />
    <div class="row">
      <el-text size="small">
        {{ stamina.stamina }} / {{ stamina.stamina_cap }}
      </el-text>
      <el-text size="small" type="info">
        今日行动剩余 {{ stamina.daily_actions_remaining }} / {{ stamina.daily_action_cap }}
      </el-text>
    </div>
    <el-text v-if="stamina.recovery_summary" size="small" type="info" class="hint">
      {{ stamina.recovery_summary }}
    </el-text>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.hint {
  display: block;
  margin-top: 0.35rem;
}
</style>
