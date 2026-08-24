<script setup lang="ts">
/**
 * 宗门工坊：锻造工坊 / 炼丹阁 / 服务工坊。
 * 含代工（真扣材料）、兑换图纸入包、上缴背包图纸、领取成品。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  claimWorkshopJob,
  donateWorkshopBlueprint,
  exchangeWorkshopBlueprint,
  fetchWorkshop,
  hireWorkshop,
} from '../../api/sect'

const props = defineProps<{ branch: 'smithing' | 'alchemy' | 'talisman' }>()
const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const title = computed(() => {
  if (props.branch === 'smithing') return '锻造工坊'
  if (props.branch === 'alchemy') return '炼丹阁'
  return '服务工坊'
})

const sheetWord = computed(() =>
  props.branch === 'alchemy' ? '丹方' : '图纸',
)

const data = ref<Record<string, any> | null>(null)
const craftsmanId = ref('')
const recipeId = ref('')
const exchangeRecipeId = ref('')
const donateInventoryId = ref<number | null>(null)
const donateLabel = ref('')
const donateSelfResearch = ref(false)
const donateRecipeId = ref('')
const busy = ref(false)

async function reload(): Promise<void> {
  const env = await fetchWorkshop(props.branch)
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
  const cms = (data.value?.craftsmen as any[]) || []
  const bps = (data.value?.blueprints as any[]) || []
  const bag = (data.value?.bag_blueprints as any[]) || []
  craftsmanId.value = cms[0]?.craftsman_id || ''
  recipeId.value = bps[0]?.recipe_id || ''
  exchangeRecipeId.value = bps[0]?.recipe_id || ''
  donateInventoryId.value = bag[0]?.inventory_item_id ?? null
}

async function onHire(): Promise<void> {
  if (!craftsmanId.value || !recipeId.value) {
    ElMessage.warning(`请选择工匠与${sheetWord.value}`)
    return
  }
  busy.value = true
  try {
    const env = await hireWorkshop(props.branch, {
      craftsman_id: craftsmanId.value,
      recipe_id: recipeId.value,
    })
    if (env.code !== 0) {
      ElMessage.error(env.message || '聘用失败')
      emit('log', env.message || '聘用失败', 'warning')
      return
    }
    ElMessage.success(String(env.data?.message || '已接单'))
    emit('log', String(env.data?.message || '已接单'), 'success')
    await reload()
  } finally {
    busy.value = false
  }
}

async function onClaim(jobId: number): Promise<void> {
  busy.value = true
  try {
    const env = await claimWorkshopJob(jobId)
    if (env.code !== 0) {
      ElMessage.error(env.message || '领取失败')
      emit('log', env.message || '领取失败', 'warning')
      return
    }
    ElMessage.success(String(env.data?.message || '已领取'))
    emit('log', String(env.data?.message || '已领取'), 'success')
    await reload()
  } finally {
    busy.value = false
  }
}

async function onExchange(): Promise<void> {
  if (!exchangeRecipeId.value) {
    ElMessage.warning(`请选择要兑换的${sheetWord.value}`)
    return
  }
  busy.value = true
  try {
    const env = await exchangeWorkshopBlueprint(props.branch, {
      recipe_id: exchangeRecipeId.value,
    })
    if (env.code !== 0) {
      ElMessage.error(env.message || '兑换失败')
      emit('log', env.message || '兑换失败', 'warning')
      return
    }
    ElMessage.success(String(env.data?.message || '已兑换'))
    emit('log', String(env.data?.message || '已兑换'), 'success')
    await reload()
  } finally {
    busy.value = false
  }
}

async function onDonate(): Promise<void> {
  if (donateSelfResearch.value) {
    const rid = donateRecipeId.value.trim()
    if (!rid) {
      ElMessage.warning(`请填写自创${sheetWord.value}配方 id`)
      return
    }
    busy.value = true
    try {
      const env = await donateWorkshopBlueprint(props.branch, {
        recipe_id: rid,
        label_zh: donateLabel.value.trim() || rid,
        self_research: true,
      })
      if (env.code !== 0) {
        ElMessage.error(env.message || '上缴失败')
        emit('log', env.message || '上缴失败', 'warning')
        return
      }
      ElMessage.success(String(env.data?.message || '已提交审核'))
      emit('log', String(env.data?.message || '已提交审核'), 'success')
      donateRecipeId.value = ''
      donateLabel.value = ''
      donateSelfResearch.value = false
      await reload()
    } finally {
      busy.value = false
    }
    return
  }
  if (donateInventoryId.value == null) {
    ElMessage.warning(`请选择背包中的${sheetWord.value}`)
    return
  }
  busy.value = true
  try {
    const env = await donateWorkshopBlueprint(props.branch, {
      recipe_id: '',
      label_zh: donateLabel.value.trim(),
      inventory_item_id: donateInventoryId.value,
    })
    if (env.code !== 0) {
      ElMessage.error(env.message || '上缴失败')
      emit('log', env.message || '上缴失败', 'warning')
      return
    }
    ElMessage.success(String(env.data?.message || '已上缴'))
    emit('log', String(env.data?.message || '已上缴'), 'success')
    donateLabel.value = ''
    await reload()
  } finally {
    busy.value = false
  }
}

watch(
  () => props.branch,
  () => {
    void reload()
  },
)

onMounted(() => {
  void reload()
})
</script>

<template>
  <div class="workshop">
    <el-card shadow="never">
      <template #header>
        <el-text tag="b">{{ title }}</el-text>
      </template>
      <el-text v-if="data" size="small" type="info">贡献 {{ data.contrib }}</el-text>
      <el-text size="small" type="info" class="hint">
        代工开工真扣材料；兑换的图纸入背包秘籍页（manual）；上缴须消耗背包图纸。
      </el-text>
      <el-divider content-position="left">聘工匠代工</el-divider>
      <div class="form">
        <el-select v-model="craftsmanId" placeholder="工匠">
          <el-option
            v-for="c in data?.craftsmen || []"
            :key="c.craftsman_id"
            :label="`${c.label_zh} · 品阶${c.grade} · ${c.cost_contribution}贡献`"
            :value="c.craftsman_id"
          />
        </el-select>
        <el-select v-model="recipeId" :placeholder="sheetWord">
          <el-option
            v-for="b in data?.blueprints || []"
            :key="b.recipe_id"
            :label="`${b.label_zh || b.recipe_id}（${b.source || 'catalog'}）`"
            :value="b.recipe_id"
          />
        </el-select>
        <el-button type="primary" :loading="busy" @click="onHire">聘工匠代工</el-button>
      </div>
      <div v-if="(data?.my_jobs || []).length" class="jobs">
        <el-text size="small" tag="b">进行中代工</el-text>
        <div v-for="j in data?.my_jobs || []" :key="j.job_id" class="job-row">
          <el-text size="small">{{ j.recipe_id }}</el-text>
          <el-button
            size="small"
            type="success"
            :disabled="!j.ready || busy"
            @click="onClaim(j.job_id)"
          >
            {{ j.ready ? '领取成品' : '制作中' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">兑换{{ sheetWord }}</el-text>
      </template>
      <div class="form">
        <el-select v-model="exchangeRecipeId" :placeholder="`选择${sheetWord}`">
          <el-option
            v-for="b in data?.blueprints || []"
            :key="b.recipe_id"
            :label="`${b.label_zh} · ${b.cost_contribution}贡献`"
            :value="b.recipe_id"
            :disabled="b.sellable === false"
          />
        </el-select>
        <el-button :loading="busy" @click="onExchange">贡献兑换入包</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">上缴{{ sheetWord }}</el-text>
      </template>
      <el-text size="small" type="info">
        未收录可获贡献；已收录不可再缴。自创须掌门/太上/创派审核。品质与学习门槛后续开放。
      </el-text>
      <div class="form">
        <el-checkbox v-model="donateSelfResearch">自创（须审核，不耗背包）</el-checkbox>
        <template v-if="donateSelfResearch">
          <el-input v-model="donateRecipeId" :placeholder="`${sheetWord}配方 id`" />
          <el-input v-model="donateLabel" placeholder="中文名" />
        </template>
        <template v-else>
          <el-select v-model="donateInventoryId" :placeholder="`背包${sheetWord}`" clearable>
            <el-option
              v-for="b in data?.bag_blueprints || []"
              :key="b.inventory_item_id"
              :label="`${b.label_zh} ×${b.quantity}`"
              :value="b.inventory_item_id"
            />
          </el-select>
          <el-input v-model="donateLabel" placeholder="中文名（可空）" />
        </template>
        <el-button type="warning" :loading="busy" @click="onDonate">上缴</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.workshop {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.hint {
  display: block;
  margin-top: 0.35rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.jobs {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.job-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
