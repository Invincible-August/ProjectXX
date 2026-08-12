<script setup lang="ts">
/**
 * 宗门任务面板：接取 / 完成；展示接取方（本体 / 化身）。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSectStore } from '../../stores/sect'
import type { SectQuestItem } from '../../types/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const sectStore = useSectStore()
const busy = ref(false)
const loadError = ref('')

onMounted(async () => {
  loadError.value = ''
  const err = await sectStore.loadQuests()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

async function onAccept(item: SectQuestItem): Promise<void> {
  if (busy.value || !item.can_accept) return
  busy.value = true
  try {
    const err = await sectStore.acceptQuest(item.quest_id, item.assignee)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(sectStore.lastMessage || '已接取')
    emit('log', sectStore.lastMessage || `接取：${item.label_zh}`, 'success')
  } finally {
    busy.value = false
  }
}

async function onComplete(item: SectQuestItem): Promise<void> {
  if (busy.value || !item.can_complete) return
  busy.value = true
  try {
    const err = await sectStore.completeQuest(item.quest_id, item.assignee)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(sectStore.lastMessage || '任务完成')
    emit('log', sectStore.lastMessage || `完成：${item.label_zh}`, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="sect-quests">
    <template #header>
      <el-text tag="b">宗门任务</el-text>
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
      v-else-if="!sectStore.quests.length"
      description="暂无任务（未入宗或功能未解锁）"
      :image-size="48"
    />

    <div v-else class="quest-list">
      <div
        v-for="item in sectStore.quests"
        :key="`${item.quest_id}:${item.assignee}`"
        class="quest-row"
      >
        <div class="quest-meta">
          <div class="title-row">
            <el-text tag="b">{{ item.label_zh }}</el-text>
            <el-tag size="small" :type="item.assignee === 'avatar' ? 'warning' : 'primary'">
              {{ item.assignee_label_zh || (item.assignee === 'avatar' ? '化身' : '本体') }}
            </el-tag>
            <el-tag size="small" type="info">{{ item.status }}</el-tag>
          </div>
          <el-text size="small" type="info">{{ item.summary }}</el-text>
          <el-text size="small">奖励贡献 +{{ item.reward_contribution }}</el-text>
          <el-text v-if="item.block_reason_zh" size="small" type="warning">
            {{ item.block_reason_zh }}
          </el-text>
        </div>
        <div class="quest-actions">
          <el-button
            v-if="item.can_accept"
            type="primary"
            size="small"
            :loading="busy"
            @click="onAccept(item)"
          >
            接取
          </el-button>
          <el-button
            v-if="item.can_complete"
            type="success"
            size="small"
            :loading="busy"
            @click="onComplete(item)"
          >
            完成
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  margin-bottom: 0.5rem;
}

.quest-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.quest-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.quest-meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  flex: 1;
}

.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
}

.quest-actions {
  display: flex;
  gap: 0.35rem;
}
</style>
