<script setup lang="ts">
/** 矿脉：被动入宗门库 + 采矿挂机。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMine, startMine, stopMine } from '../../api/sect'
import { useCharacterStore } from '../../stores/character'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const characterStore = useCharacterStore()
const data = ref<Record<string, any> | null>(null)
const busy = ref(false)

async function reload(): Promise<void> {
  const env = await fetchMine()
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
}

async function onStart(): Promise<void> {
  busy.value = true
  try {
    const env = await startMine()
    if (env.code !== 0) {
      ElMessage.error(env.message || '开始采矿失败')
      emit('log', env.message || '开始采矿失败', 'warning')
      return
    }
    ElMessage.success(String(env.data?.message || '已开始采矿'))
    emit('log', String(env.data?.message || '已开始采矿'), 'success')
    await characterStore.fetchMe()
    await reload()
  } finally {
    busy.value = false
  }
}

async function onStop(): Promise<void> {
  busy.value = true
  try {
    const env = await stopMine()
    if (env.code !== 0) {
      ElMessage.error(env.message || '停止采矿失败')
      return
    }
    ElMessage.success(String(env.data?.message || '已停止采矿'))
    emit('log', String(env.data?.message || '已停止采矿'), 'success')
    await characterStore.fetchMe()
    await reload()
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">矿脉</el-text>
    </template>
    <template v-if="data">
      <el-text>
        设施 Lv.{{ data.facility_level }} · 席位 {{ data.miners }}/{{ data.max_miners }} · 灵石库
        {{ data.spirit_stone_pool }}
      </el-text>
      <el-text size="small" type="info" style="display: block; margin: 0.35rem 0">
        入库约 {{ data.pool_rate_per_hour }}/时 · 采矿每 {{ data.tick_seconds }}s 得
        {{ data.personal_stones_per_tick }} 灵石、耗 {{ data.stamina_per_tick }} 体力
      </el-text>
        <el-text size="small" type="info" style="display: block; margin-bottom: 0.5rem">
          {{ data.note_zh }} · 消耗战斗体力条（与生活属性体力同源）；开始后修炼区可见「结束采矿」
        </el-text>
      <el-tag v-if="data.mining" type="success" size="small">采矿挂机中</el-tag>
      <div class="row">
        <el-button type="primary" :loading="busy" :disabled="data.mining" @click="onStart">
          开始采矿
        </el-button>
        <el-button :loading="busy" :disabled="!data.mining" @click="onStop">停止采矿</el-button>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
