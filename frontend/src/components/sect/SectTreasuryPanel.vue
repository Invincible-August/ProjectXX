<script setup lang="ts">
/** 藏宝阁：贡献兑换。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exchangeTreasury, fetchTreasury } from '../../api/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const data = ref<Record<string, any> | null>(null)

async function reload(): Promise<void> {
  const env = await fetchTreasury()
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
}

async function onExchange(key: string): Promise<void> {
  const env = await exchangeTreasury({ item_key: key })
  if (env.code !== 0) {
    ElMessage.error(env.message || '兑换失败')
    emit('log', env.message || '兑换失败', 'warning')
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
      <el-text tag="b">藏宝阁</el-text>
    </template>
    <el-text v-if="data" size="small" type="info">
      贡献 {{ data.contrib }} · 可分配页上限 {{ data.my_treasury_page_max }} · 禁止放入：{{
        (data.forbidden_deposit_types || []).join('、')
      }}
    </el-text>
    <div v-for="c in data?.catalog || []" :key="c.item_key" class="row">
      <el-text>{{ c.label_zh }} · {{ c.cost_contribution }} 贡献</el-text>
      <el-button size="small" @click="onExchange(c.item_key)">兑换</el-button>
    </div>
    <el-divider content-position="left">库存</el-divider>
    <el-empty v-if="!(data?.stock || []).length" description="暂无库存" :image-size="40" />
    <div v-for="s in data?.stock || []" :key="s.id" class="row">
      <el-text size="small">
        第{{ s.page }}页 · {{ s.label_zh || s.item_id }} ×{{ s.quantity }}
      </el-text>
    </div>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.4rem;
}
</style>
