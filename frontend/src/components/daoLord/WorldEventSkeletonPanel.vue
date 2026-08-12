<script setup lang="ts">
/**
 * 世界 Boss / 秘境骨架面板：不参加不挡主线；成型玩法见后续版本。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useWorldEventsStore } from '../../stores/worldEvents'
import { useWsStore } from '../../stores/ws'
import { joinRoom } from '../../ws/rooms'
import type { WorldEventPublic } from '../../types/worldEvents'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const eventsStore = useWorldEventsStore()
const wsStore = useWsStore()
const busyId = ref<string | number | null>(null)

async function onRegister(ev: WorldEventPublic): Promise<void> {
  busyId.value = ev.id
  try {
    const err = await eventsStore.register(ev.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(eventsStore.lastMessage || '已报名（骨架）')
    emit('log', eventsStore.lastMessage || `报名事件：${ev.label}`, 'info')
  } finally {
    busyId.value = null
  }
}

function onEnterRoom(ev: WorldEventPublic): void {
  if (!ev.room_id) {
    ElMessage.info('房间尚未开放')
    return
  }
  if (!wsStore.enabled) {
    ElMessage.warning('强交互通道未开启')
    return
  }
  wsStore.connect()
  const ok = joinRoom(wsStore.client, ev.room_id, { event_id: ev.id })
  if (ok) {
    ElMessage.success(`已请求进入房间：${ev.room_id}`)
    emit('log', `进入事件房间：${ev.label}`, 'info')
  } else {
    ElMessage.warning('WS 未连接，请稍后重试')
  }
}
</script>

<template>
  <el-card shadow="never" class="events">
    <template #header>
      <el-text tag="b">定时秘境 / 世界 Boss（骨架）</el-text>
    </template>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="骨架 / 后续开放完整奖励。不参加不挡主线；成型玩法见后续版本。"
      class="mb"
    />

    <el-text v-if="eventsStore.note" size="small" type="info" class="note">
      {{ eventsStore.note }}
    </el-text>

    <el-empty
      v-if="!eventsStore.events.length && !eventsStore.loading"
      description="当前无开放事件"
      :image-size="48"
    />

    <div v-for="ev in eventsStore.events" :key="String(ev.id)" class="ev-row">
      <div class="ev-main">
        <el-text tag="b">{{ ev.label }}</el-text>
        <el-tag size="small" type="info">骨架</el-tag>
        <el-tag v-if="ev.open" size="small" type="success">开放中</el-tag>
        <el-text size="small" type="info">
          报名 {{ ev.registered_count ?? (ev.registered ? 1 : 0) }} · 在场
          {{ ev.presence_count ?? 0 }}
        </el-text>
        <el-text v-if="ev.description || ev.summary" size="small">
          {{ ev.description || ev.summary }}
        </el-text>
      </div>
      <div class="ev-actions">
        <el-button
          size="small"
          :loading="busyId === ev.id"
          :disabled="!ev.open"
          @click="onRegister(ev)"
        >
          报名
        </el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="!ev.open || !ev.room_id"
          @click="onEnterRoom(ev)"
        >
          进入房间
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.mb {
  margin-bottom: 0.75rem;
}

.note {
  display: block;
  margin-bottom: 0.75rem;
}

.ev-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.ev-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.65rem;
  flex: 1;
}

.ev-actions {
  display: flex;
  gap: 0.35rem;
}
</style>
