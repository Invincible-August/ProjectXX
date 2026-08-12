<script setup lang="ts">
/** 藏经阁。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exchangeScripture, fetchScripture } from '../../api/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const data = ref<Record<string, any> | null>(null)

async function reload(): Promise<void> {
  const env = await fetchScripture()
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
}

async function onExchange(tid: string): Promise<void> {
  const env = await exchangeScripture({ technique_id: tid })
  if (env.code !== 0) {
    ElMessage.error(env.message || '兑换失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已兑换'))
  emit('log', String(env.data?.message || '已兑换'), 'success')
  await reload()
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">藏经阁</el-text>
    </template>
    <el-text v-if="data" size="small" type="info">贡献 {{ data.contrib }}</el-text>
    <div v-for="c in data?.catalog || []" :key="c.technique_id" class="row">
      <el-text>
        {{ c.label_zh }} · {{ c.cost_contribution }} 贡献
        <el-tag v-if="c.owned" size="small" type="success">已收录</el-tag>
      </el-text>
      <el-button size="small" @click="onExchange(c.technique_id)">兑换</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.4rem;
  align-items: center;
}
</style>
