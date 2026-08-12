<script setup lang="ts">
/**
 * 师徒面板：申请 / 确认 / 传功 / 出师 / 解除。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useMentorStore } from '../../stores/mentor'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const mentorStore = useMentorStore()
const busy = ref(false)
const targetName = ref('')
const intent = ref<'apprentice' | 'master'>('apprentice')

onMounted(async () => {
  const err = await mentorStore.refresh()
  if (err) emit('log', err, 'warning')
})

async function run(fn: () => Promise<string | null>, okHint?: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await fn()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(okHint || mentorStore.lastMessage || '完成')
    emit('log', mentorStore.lastMessage || okHint || '完成', 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">师徒</el-text>
    </template>

    <div v-if="mentorStore.bond" class="bond">
      <el-text>
        师傅：{{ mentorStore.bond.master_name }} · 徒弟：{{ mentorStore.bond.apprentice_name }}
      </el-text>
      <el-text size="small" type="info">
        你是{{ mentorStore.bond.role === 'master' ? '师傅' : '徒弟' }}
        <template v-if="mentorStore.channelRef"> · 师承频 {{ mentorStore.channelRef }}</template>
      </el-text>
      <div class="quests">
        <div v-for="q in mentorStore.quests" :key="q.quest_id" class="quest">
          <el-text size="small">
            {{ q.name }}：{{ q.progress }}/{{ q.target_count }}
            {{ q.completed ? '（已完成）' : '' }}
          </el-text>
        </div>
      </div>
      <div class="actions">
        <el-button
          v-if="mentorStore.bond.role === 'master'"
          size="small"
          type="primary"
          :loading="busy"
          @click="run(() => mentorStore.pass(), '传功成功')"
        >
          传功
        </el-button>
        <el-button
          size="small"
          type="success"
          :loading="busy"
          @click="run(() => mentorStore.graduate())"
        >
          出师
        </el-button>
        <el-button size="small" :loading="busy" @click="run(() => mentorStore.dissolve())">
          解除
        </el-button>
      </div>
    </div>

    <div v-else class="apply">
      <el-radio-group v-model="intent" size="small">
        <el-radio-button value="apprentice">拜师</el-radio-button>
        <el-radio-button value="master">收徒</el-radio-button>
      </el-radio-group>
      <el-input v-model="targetName" size="small" placeholder="对方道号" clearable />
      <el-button
        type="primary"
        size="small"
        :loading="busy"
        @click="run(() => mentorStore.apply(targetName, intent))"
      >
        发送申请
      </el-button>
    </div>

    <div v-if="mentorStore.incoming.length" class="inbox">
      <el-text tag="b" size="small">待确认</el-text>
      <div v-for="b in mentorStore.incoming" :key="b.bond_id" class="row">
        <el-text size="small">
          {{ b.master_name }} ← {{ b.apprentice_name }}
        </el-text>
        <el-button size="small" type="primary" @click="run(() => mentorStore.accept(b.bond_id))">
          确认
        </el-button>
        <el-button size="small" @click="run(() => mentorStore.reject(b.bond_id))">拒绝</el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.bond,
.apply,
.inbox {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.actions,
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}
.quests {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.inbox {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--el-border-color-lighter);
}
</style>
