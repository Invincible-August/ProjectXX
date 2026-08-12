<script setup lang="ts">
/**
 * 大厅双线程入口卡（M4）：化身 / 工坊 / 灵兽园 + 角标摘要。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'
import { avatarIdleBadge } from '../../utils/idleLabels'

const router = useRouter()
const characterStore = useCharacterStore()

const character = computed(() => characterStore.character)

/** 化身状态文案 */
const avatarBadge = computed(() => {
  const ch = character.value
  if (!ch) return ''
  return avatarIdleBadge(ch.avatar_summary?.idle_direction, Boolean(ch.has_avatar))
})

/** 工坊可领取数 */
const craftReady = computed(() => character.value?.craft_jobs_summary?.ready ?? 0)

/** 灵宠持有数 */
const petsCount = computed(() => character.value?.pets_count ?? 0)
</script>

<template>
  <el-card shadow="never" class="dual-gate">
    <template #header>
      <el-text tag="b">双线程（M4）</el-text>
    </template>

    <div class="gate-grid">
      <div class="gate-card" @click="router.push('/avatar')">
        <el-badge :value="avatarBadge" :hidden="!avatarBadge" type="info">
          <el-button type="primary" size="small">化身</el-button>
        </el-badge>
        <el-text size="small" type="info">凝练 · 双挂机 · 传修为</el-text>
      </div>

      <div class="gate-card" @click="router.push('/workshop')">
        <el-badge :value="craftReady" :hidden="craftReady <= 0" type="success">
          <el-button type="warning" size="small">工坊</el-button>
        </el-badge>
        <el-text size="small" type="info">配方队列 · 领取 · 背包</el-text>
      </div>

      <div class="gate-card" @click="router.push('/pets')">
        <el-badge :value="petsCount" :hidden="petsCount <= 0" type="primary">
          <el-button type="success" size="small">灵兽园</el-button>
        </el-badge>
        <el-text size="small" type="info">持有 {{ petsCount }} 只</el-text>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.dual-gate {
  transition: box-shadow 0.2s ease;
}

.dual-gate:hover {
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.12);
}

.gate-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.gate-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  padding: 0.25rem 0;
  border-radius: 4px;
  transition: background 0.15s ease;
}

.gate-card:hover {
  background: rgba(64, 158, 255, 0.06);
}
</style>
