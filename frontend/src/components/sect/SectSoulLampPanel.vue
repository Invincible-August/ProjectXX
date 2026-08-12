<script setup lang="ts">
/**
 * 魂灯面板：同门状态列表（散修空态由父级处理）。
 */
import { onMounted, ref } from 'vue'
import { useSectStore } from '../../stores/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const sectStore = useSectStore()
const loadError = ref('')

onMounted(async () => {
  loadError.value = ''
  const err = await sectStore.loadLamps()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})
</script>

<template>
  <el-card shadow="never" class="sect-lamps">
    <template #header>
      <el-text tag="b">魂灯</el-text>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="hint"
    />

    <el-empty
      v-else-if="!sectStore.lamps.length"
      description="暂无同门魂灯"
      :image-size="48"
    />

    <div v-else class="lamp-list">
      <div
        v-for="lamp in sectStore.lamps"
        :key="lamp.character_id"
        class="lamp-row"
      >
        <div class="lamp-meta">
          <div class="title-row">
            <el-text tag="b">{{ lamp.name }}</el-text>
            <el-tag size="small">{{ lamp.role_label_zh || lamp.role }}</el-tag>
            <el-tag
              size="small"
              :type="lamp.awaiting_ferry ? 'danger' : 'info'"
            >
              {{ lamp.status_label_zh || lamp.status }}
            </el-tag>
          </div>
          <el-text size="small" type="info">
            {{ lamp.major_realm_label_zh || lamp.major_realm }}
            · {{ lamp.region_stub === 'same_region' ? '同图' : lamp.region_stub }}
          </el-text>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  margin-bottom: 0.5rem;
}

.lamp-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.lamp-row {
  display: flex;
  align-items: center;
}

.lamp-meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
}
</style>
