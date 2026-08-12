<script setup lang="ts">
/** 宗门大阵：兑换/上缴；有权者可选阵/启停/加点。 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  allocateFormationAttr,
  donateFormation,
  exchangeFormation,
  fetchFormation,
  selectFormation,
  setFormationActive,
} from '../../api/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const data = ref<Record<string, any> | null>(null)
const selected = ref('')
const donateId = ref('')
const exchangeId = ref('')

async function reload(): Promise<void> {
  const env = await fetchFormation()
  if (env.code !== 0) {
    ElMessage.error(env.message || '加载失败')
    return
  }
  data.value = env.data || null
  selected.value = String(data.value?.formation_id || '')
  const catalog = (data.value?.catalog as any[]) || []
  donateId.value = catalog[0]?.formation_id || ''
  exchangeId.value = catalog[0]?.formation_id || ''
}

async function onSelect(): Promise<void> {
  const env = await selectFormation({ formation_id: selected.value })
  if (env.code !== 0) {
    ElMessage.error(env.message || '选择失败')
    return
  }
  ElMessage.success('已选择阵法')
  await reload()
}

async function onActive(active: boolean): Promise<void> {
  const env = await setFormationActive({ active })
  if (env.code !== 0) {
    ElMessage.error(env.message || '操作失败')
    emit('log', env.message || '操作失败', 'warning')
    return
  }
  ElMessage.success(String(env.data?.message || '已更新'))
  await reload()
}

async function onAllocate(attrKey: string): Promise<void> {
  const env = await allocateFormationAttr({ attr_key: attrKey })
  if (env.code !== 0) {
    ElMessage.error(env.message || '加点失败')
    emit('log', env.message || '加点失败', 'warning')
    return
  }
  ElMessage.success(String(env.data?.message || '已加点'))
  emit('log', String(env.data?.message || '已加点'), 'success')
  await reload()
}

async function onExchange(): Promise<void> {
  const env = await exchangeFormation({ formation_id: exchangeId.value })
  if (env.code !== 0) {
    ElMessage.error(env.message || '兑换失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已兑换'))
  emit('log', String(env.data?.message || '已兑换'), 'success')
  await reload()
}

async function onDonate(): Promise<void> {
  const env = await donateFormation({ formation_id: donateId.value, need_review: true })
  if (env.code !== 0) {
    ElMessage.error(env.message || '上缴失败')
    return
  }
  ElMessage.success(String(env.data?.message || '已提交上缴'))
  emit('log', String(env.data?.message || '已提交上缴'), 'success')
  await reload()
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">宗门大阵</el-text>
    </template>
    <el-text v-if="data" size="small">
      当前 {{ data.formation_id || '未选' }} · Lv.{{ data.level }} ·
      {{ data.active ? '开启中' : '关闭' }} · 灵石库 {{ data.spirit_stone_pool }} · 贡献
      {{ data.contrib }}
    </el-text>
    <el-text v-if="data" size="small" type="info" style="display: block; margin: 0.35rem 0">
      属性点 {{ data.attr_spent }} ·
      <template v-for="a in data.attr_catalog || []" :key="a.attr_key">
        {{ a.label_zh }}{{ a.points }}
      </template>
    </el-text>

    <div class="row">
      <el-select v-model="exchangeId" placeholder="兑换阵法" style="min-width: 160px">
        <el-option
          v-for="f in data?.catalog || []"
          :key="`ex-${f.formation_id}`"
          :label="`${f.label_zh} · ${f.exchange_cost_contribution}贡献${f.learned ? '（已学）' : ''}`"
          :value="f.formation_id"
        />
      </el-select>
      <el-button @click="onExchange">兑换</el-button>
      <el-select v-model="donateId" placeholder="上缴阵法" style="min-width: 140px">
        <el-option
          v-for="f in data?.catalog || []"
          :key="`do-${f.formation_id}`"
          :label="f.label_zh"
          :value="f.formation_id"
        />
      </el-select>
      <el-button @click="onDonate">上缴</el-button>
    </div>

    <template v-if="data?.can_manage">
      <div class="row">
        <el-select v-model="selected" placeholder="阵法" style="min-width: 180px">
          <el-option
            v-for="f in (data?.catalog || []).filter((x: any) => x.learned)"
            :key="f.formation_id"
            :label="f.label_zh"
            :value="f.formation_id"
          />
        </el-select>
        <el-button @click="onSelect">选择</el-button>
        <el-button type="primary" @click="onActive(true)">开启</el-button>
        <el-button @click="onActive(false)">关闭</el-button>
      </div>
      <div class="row">
        <el-button
          v-for="a in data?.attr_catalog || []"
          :key="a.attr_key"
          size="small"
          @click="onAllocate(a.attr_key)"
        >
          强化{{ a.label_zh }}
        </el-button>
      </div>
    </template>
    <el-text v-else size="small" type="info" style="display: block; margin-top: 0.5rem">
      无管理权限：仅可兑换与上缴阵法功法
    </el-text>
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
