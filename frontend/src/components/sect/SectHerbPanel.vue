<script setup lang="ts">
/** 灵药园：兑换灵植 + 托管种植。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exchangeHerb, fetchHerbs, harvestHerb, plantHerb } from '../../api/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const data = ref<Record<string, any> | null>(null)
const plantId = ref('')
const herbalistId = ref<string | undefined>(undefined)

async function reload(): Promise<void> {
  const env = await fetchHerbs()
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
  const plants = (data.value?.plants as any[]) || []
  plantId.value = plants[0]?.plant_id || ''
}

async function onExchange(): Promise<void> {
  const env = await exchangeHerb({ plant_id: plantId.value })
  if (env.code !== 0) {
    ElMessage.error(env.message || '兑换失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已兑换'))
  emit('log', String(env.data?.message || '已兑换'), 'success')
  await reload()
}

async function onPlant(hosted: boolean): Promise<void> {
  const env = await plantHerb({
    plant_id: plantId.value,
    herbalist_id: herbalistId.value || null,
    hosted,
  })
  if (env.code !== 0) {
    ElMessage.error(env.message || (hosted ? '托管失败' : '种植失败'))
    return
  }
  ElMessage.success(String(env.data?.message || '已种植'))
  emit('log', String(env.data?.message || '已种植'), 'success')
  await reload()
}

async function onHarvest(id: number): Promise<void> {
  const env = await harvestHerb(id)
  if (env.code !== 0) {
    ElMessage.error(env.message || '收获失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已收获'))
  await reload()
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">灵药园</el-text>
    </template>
    <el-text v-if="data" size="small" type="info">
      地块 {{ data.growing }}/{{ data.capacity }} · 贡献 {{ data.contrib }} · 游戏日
      {{ data.game_day }}
    </el-text>
    <div class="row">
      <el-select v-model="plantId" placeholder="灵植" style="min-width: 180px">
        <el-option
          v-for="p in data?.plants || []"
          :key="p.plant_id"
          :label="`${p.label_zh} · 兑${p.exchange_cost_contribution}/种${p.plant_cost_contribution}`"
          :value="p.plant_id"
        />
      </el-select>
      <el-select
        v-model="herbalistId"
        clearable
        placeholder="灵植师（托管必选）"
        style="min-width: 160px"
      >
        <el-option
          v-for="h in data?.herbalists || []"
          :key="h.herbalist_id"
          :label="`${h.label_zh} · +${h.cost_contribution}`"
          :value="h.herbalist_id"
        />
      </el-select>
      <el-button type="success" @click="onExchange">直接兑换</el-button>
      <el-button @click="onPlant(false)">自行种植</el-button>
      <el-button type="primary" @click="onPlant(true)">托管种植</el-button>
    </div>
    <div v-for="p in data?.plots || []" :key="p.id" class="row">
      <el-text size="small">
        {{ p.plant_id }} · 成熟日 {{ p.ready_game_day }}
        <el-tag v-if="p.hosted" size="small" type="warning">托管</el-tag>
        <el-tag v-if="p.ready" size="small" type="success">可收获</el-tag>
      </el-text>
      <el-button size="small" :disabled="!p.ready" @click="onHarvest(p.id)">收获</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
  align-items: center;
}
</style>
