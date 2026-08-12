<script setup lang="ts">
/**
 * 大厅战斗入口卡（M3 枢纽）：跳转布阵 / 战斗 + 体力条 + 最近一战摘要。
 *
 * 只做路由跳转与只读展示，不承载布阵 UI。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import StaminaBar from './battle/StaminaBar.vue'
import { useBattleStore } from '../stores/battle'

const router = useRouter()
const battleStore = useBattleStore()

/** 最近一战（本会话） */
const latest = computed(() => battleStore.sessionReports[0] ?? null)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">战斗（M3）</el-text>
    </template>

    <StaminaBar class="gate-stamina" />

    <div class="gate-actions">
      <el-button type="primary" size="small" @click="router.push('/formation')">
        布阵
      </el-button>
      <el-button type="danger" size="small" @click="router.push('/battle')">
        战斗
      </el-button>
    </div>

    <el-text v-if="latest" type="info" size="small" class="gate-latest">
      最近一战：{{ latest.title }} · {{ latest.result === 'win' ? '胜' : '负' }}
      <el-button
        size="small"
        text
        type="primary"
        @click="router.push(`/battle?report=${latest.session_key}`)"
      >
        回放
      </el-button>
    </el-text>
  </el-card>
</template>

<style scoped>
.gate-stamina {
  margin-bottom: 0.75rem;
}

.gate-actions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.gate-latest {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
</style>
