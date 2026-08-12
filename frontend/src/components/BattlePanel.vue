<script setup lang="ts">
/**
 * 大厅一键教学战（M3 §4.2 方案 B）：无布阵打教学怪（本体默认锚点空盘开战）。
 *
 * 战报摘要写入大厅事件日志；完整回放在 /battle 页（本会话战报列表）。
 * 修炼中（idle_direction ≠ none）禁止开战。
 */
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useActivityGate } from '../composables/useActivityGate'
import { useBattleStore } from '../stores/battle'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const router = useRouter()
const battleStore = useBattleStore()
const { canStartBattle, blockReason } = useActivityGate()

/** 正在修炼或其它互斥态时不可开战 */
const isCultivating = computed(() => !canStartBattle.value)

/**
 * 对 tutorial_slime 开战；摘要写入事件日志。
 */
async function onFight(): Promise<void> {
  if (battleStore.fighting) return
  if (!canStartBattle.value) {
    const msg = blockReason('start_battle') || '修炼中不可开战，请先停止修炼'
    ElMessage.warning(msg)
    emit('log', msg, 'warning')
    return
  }
  const error = await battleStore.startPve('tutorial_slime')
  if (error) {
    ElMessage.error(error)
    emit('log', error, 'warning')
    return
  }
  const r = battleStore.lastReport
  if (!r) return
  emit('log', `—— 开战：${r.monster_name ?? '教学妖兽'} ——`, 'system')
  const winnerText = r.result === 'win' ? '进攻方胜' : '防守方胜'
  emit(
    'log',
    `${winnerText}（${r.report.rounds} 回合）；修为 +${r.rewards.cultivation_points}，灵石 +${r.rewards.spirit_stones}；体力剩余 ${r.stamina.left}/${r.stamina.cap}`,
    r.result === 'win' ? 'success' : 'warning',
  )
  emit('log', '完整战报可在「战斗」页回放（仅本次登录有效）。', 'info')
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">快速教学战</el-text>
    </template>

    <el-text type="info" size="small" class="battle-hint">
      教学怪：浊气蛙。摘要写入右侧日志；完整回放去「战斗」页。
    </el-text>

    <el-alert
      v-if="isCultivating"
      title="修炼中不可开战，请先停止修炼"
      type="warning"
      show-icon
      :closable="false"
      class="battle-block"
    />

    <div class="battle-actions">
      <el-button
        type="danger"
        :loading="battleStore.fighting"
        :disabled="isCultivating"
        @click="onFight"
      >
        挑战浊气蛙
      </el-button>
      <el-button @click="router.push('/battle')">前往战斗页</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.battle-hint {
  display: block;
  margin-bottom: 0.75rem;
}

.battle-block {
  margin-bottom: 0.75rem;
}

.battle-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
