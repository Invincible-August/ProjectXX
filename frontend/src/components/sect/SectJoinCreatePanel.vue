<script setup lang="ts">
/**
 * 拜入 NPC / 自建宗门面板。
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSectStore } from '../../stores/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  joined: []
}>()

const sectStore = useSectStore()
const busy = ref(false)
const createName = ref('')
const createMotto = ref('')

async function onJoin(templateId: string, label: string): Promise<void> {
  if (busy.value || sectStore.inSect) return
  try {
    await ElMessageBox.confirm(`确认拜入「${label}」？将扣除拜入灵石。`, '拜入宗门', {
      type: 'warning',
      confirmButtonText: '确认拜入',
      cancelButtonText: '再想想',
    })
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await sectStore.join(templateId)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(sectStore.lastMessage || `已拜入「${label}」`)
    emit('log', sectStore.lastMessage || `已拜入「${label}」`, 'success')
    emit('joined')
  } finally {
    busy.value = false
  }
}

async function onCreate(): Promise<void> {
  if (busy.value || sectStore.inSect) return
  const name = createName.value.trim()
  if (!name) {
    ElMessage.warning('请填写宗门名')
    return
  }
  const cost = sectStore.createCostSpiritStones
  try {
    await ElMessageBox.confirm(
      `确认创建宗门「${name}」？将消耗 ${cost} 灵石。`,
      '自建宗门',
      {
        type: 'warning',
        confirmButtonText: '确认创建',
        cancelButtonText: '再想想',
      },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await sectStore.create(name, createMotto.value.trim() || null)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(sectStore.lastMessage || `已创建「${name}」`)
    emit('log', sectStore.lastMessage || `已创建「${name}」`, 'success')
    createName.value = ''
    createMotto.value = ''
    emit('joined')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="join-create">
    <el-card shadow="never">
      <template #header>
        <el-text tag="b">拜入 NPC 宗门</el-text>
      </template>

      <el-alert
        v-if="sectStore.inSect"
        type="success"
        :closable="false"
        show-icon
        title="你已有宗门，不可重复拜入或再建。"
        class="hint"
      />

      <el-empty
        v-else-if="!sectStore.npc.length"
        description="暂无 NPC 宗门目录"
        :image-size="48"
      />

      <div v-else class="npc-list">
        <div v-for="item in sectStore.npc" :key="item.template_id" class="npc-row">
          <div class="npc-meta">
            <el-text tag="b">{{ item.label_zh }}</el-text>
            <el-text size="small" type="info">{{ item.summary || item.motto }}</el-text>
            <el-text size="small">
              门槛 {{ item.join_min_realm_label_zh || item.join_min_realm }} · 费用
              {{ item.join_cost_spirit_stones }} 灵石 · 挂机 ×{{
                Number(item.idle_bonus_vs_wanderer).toFixed(2)
              }}
            </el-text>
            <el-text v-if="!item.can_join && item.block_reason_zh" size="small" type="warning">
              {{ item.block_reason_zh }}
            </el-text>
          </div>
          <el-button
            type="primary"
            size="small"
            :loading="busy"
            :disabled="!item.can_join || sectStore.inSect"
            @click="onJoin(item.template_id, item.label_zh)"
          >
            拜入
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">自建宗门</el-text>
      </template>

      <el-text size="small" type="info" class="cost-line">
        创建费用：{{ sectStore.createCostSpiritStones }} 灵石（服务端权威）
      </el-text>

      <div class="create-form">
        <el-input
          v-model="createName"
          placeholder="宗门名"
          maxlength="32"
          show-word-limit
          :disabled="sectStore.inSect"
        />
        <el-input
          v-model="createMotto"
          placeholder="箴言（可选）"
          maxlength="64"
          show-word-limit
          :disabled="sectStore.inSect"
        />
        <el-button
          type="warning"
          :loading="busy"
          :disabled="sectStore.inSect"
          @click="onCreate"
        >
          创建宗门
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.join-create {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.hint {
  margin-bottom: 0.5rem;
}

.npc-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.npc-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.npc-meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  flex: 1;
}

.cost-line {
  display: block;
  margin-bottom: 0.5rem;
}

.create-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
