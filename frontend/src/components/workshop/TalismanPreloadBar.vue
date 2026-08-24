<script setup lang="ts">
/**
 * Workshop preload dashed slots for the next battle (M8 R4).
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchTalismanPreloadApi, putTalismanPreloadApi } from '../../api/craft'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useInventoryStore } from '../../stores/inventory'
import { useResearchStore } from '../../stores/research'
import type { TalismanPreloadSlot } from '../../types/craft'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const inventoryStore = useInventoryStore()
const researchStore = useResearchStore()
const { writeBlocked } = usePlayWriteGate()

const slots = ref<TalismanPreloadSlot[]>([])
const maxSlots = ref(1)
const selectedId = ref<number | null>(null)
const busy = ref(false)

const bagTalismans = computed(() =>
  inventoryStore.items.filter((i) => i.item_type === 'talisman' && Number(i.quantity || 0) > 0),
)

onMounted(async () => {
  if (!researchStore.catalog) {
    await researchStore.loadCatalog()
  }
  await reload()
})

async function reload(): Promise<void> {
  const envelope = await fetchTalismanPreloadApi()
  if (envelope.code !== 0 || !envelope.data) {
    emit('log', envelope.message || '加载预载栏失败', 'warning')
    return
  }
  slots.value = envelope.data.slots
  maxSlots.value = envelope.data.max_slots
  if (slots.value[0]) {
    selectedId.value = slots.value[0].inventory_item_id
  }
}

async function apply(ids: number[]): Promise<void> {
  if (writeBlocked.value) return
  busy.value = true
  try {
    const envelope = await putTalismanPreloadApi(ids)
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '预载失败')
      emit('log', envelope.message || '预载失败', 'warning')
      return
    }
    slots.value = envelope.data.slots
    maxSlots.value = envelope.data.max_slots
    selectedId.value = slots.value[0]?.inventory_item_id ?? null
    await inventoryStore.load()
    emit('log', ids.length ? '已预载出战符箓' : '已清空预载栏', 'success')
  } finally {
    busy.value = false
  }
}

async function onLoad(): Promise<void> {
  if (selectedId.value == null) {
    ElMessage.info('请选择背包中的符箓')
    return
  }
  await apply([selectedId.value])
}

async function onClear(): Promise<void> {
  await apply([])
}

defineExpose({ reload })
</script>

<template>
  <el-card shadow="never" class="preload-card">
    <template #header>
      <el-text tag="b" size="small">出战预载</el-text>
    </template>
    <el-text size="small" type="info" class="help">
      出战符箓改在角色页装备栏上阵（无件数上限）。此处仍可查看当前已上阵列表。
    </el-text>
    <el-button size="small" type="primary" plain @click="$router.push('/character')">
      去装备栏上阵符箓
    </el-button>
    <el-text v-if="slots.length" size="small" type="info" class="help">
      已上阵：{{ slots.map((s) => s.label_zh).join('、') }}
    </el-text>
    <el-text v-else size="small" type="info" class="help">尚未上阵符箓</el-text>
    <el-form label-width="5rem" size="small" class="form">
      <el-form-item label="背包">
        <el-select
          v-model="selectedId"
          placeholder="选择符箓"
          clearable
          :disabled="writeBlocked"
        >
          <el-option
            v-for="item in bagTalismans"
            :key="item.id"
            :label="`${item.name} ×${item.quantity}`"
            :value="item.id"
          />
        </el-select>
        <el-text v-if="!bagTalismans.length" size="small" type="info" class="empty-bag">
          背包暂无符箓，请先画符
        </el-text>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          size="small"
          :loading="busy"
          :disabled="writeBlocked"
          @click="onLoad"
        >
          预载
        </el-button>
        <el-button
          size="small"
          :disabled="!slots.length || busy || writeBlocked"
          @click="onClear"
        >
          清空
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.preload-card {
  min-width: 0;
}
.help {
  display: block;
  margin-bottom: 0.5rem;
}
.slots {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.slot {
  min-width: 5.5rem;
  min-height: 2.5rem;
  padding: 0.35rem 0.5rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
}
.slot.filled {
  border-style: solid;
  color: var(--el-text-color-primary);
}
.form {
  margin-top: 0.25rem;
}
.empty-bag {
  display: block;
  margin-top: 0.35rem;
}
</style>
