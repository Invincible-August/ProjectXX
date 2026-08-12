<script setup lang="ts">
/**
 * 宗门兑宠面板：白名单目录 + 兑换按钮。
 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSectStore } from '../../stores/sect'
import type { ExchangeCatalogItem } from '../../types/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const sectStore = useSectStore()
const busy = ref(false)
const loadError = ref('')

onMounted(async () => {
  loadError.value = ''
  const err = await sectStore.loadExchange()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

async function onExchange(item: ExchangeCatalogItem): Promise<void> {
  if (busy.value || !item.enabled) return
  try {
    await ElMessageBox.confirm(
      `确认消耗 ${item.cost_contribution} 贡献兑换「${item.name}」（品阶 ${item.grade}）？`,
      '宗门兑宠',
      {
        type: 'warning',
        confirmButtonText: '确认兑换',
        cancelButtonText: '再想想',
      },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    const err = await sectStore.exchangePet(item.species_id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(sectStore.lastMessage || `已兑换「${item.name}」`)
    emit('log', sectStore.lastMessage || `兑宠：${item.name}`, 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="sect-exchange">
    <template #header>
      <div class="hdr">
        <el-text tag="b">宗门兑宠</el-text>
        <el-text size="small" type="info">
          当前贡献 {{ sectStore.exchange?.contrib ?? 0 }}
        </el-text>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="hint"
    />

    <el-alert
      v-else-if="sectStore.exchange && !sectStore.exchange.enabled"
      title="宗门兑宠未开放"
      type="warning"
      :closable="false"
      show-icon
      class="hint"
    />

    <el-alert
      v-else-if="sectStore.exchange && !sectStore.exchange.in_sect"
      title="未入宗，不可兑宠"
      type="info"
      :closable="false"
      show-icon
      class="hint"
    />

    <el-empty
      v-else-if="!sectStore.exchangeItems.length"
      description="暂无兑宠白名单"
      :image-size="48"
    />

    <div v-else class="ex-list">
      <div
        v-for="item in sectStore.exchangeItems"
        :key="item.species_id"
        class="ex-row"
      >
        <div class="ex-meta">
          <el-text tag="b">{{ item.name }}</el-text>
          <el-text size="small" type="info">
            {{ item.species_id }} · 品阶 {{ item.grade }} · 费用
            {{ item.cost_contribution }} 贡献
          </el-text>
        </div>
        <el-button
          type="success"
          size="small"
          :loading="busy"
          :disabled="!item.enabled || !sectStore.exchange?.in_sect"
          @click="onExchange(item)"
        >
          兑换
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.hint {
  margin-bottom: 0.5rem;
}

.ex-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.ex-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.ex-meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  flex: 1;
}
</style>
