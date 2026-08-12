<script setup lang="ts">
/**
 * 体质背包与主/副格镶嵌（M2 骨架）。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  equipConstitutionApi,
  fetchConstitutionApi,
  fuseConstitutionApi,
  unequipConstitutionApi,
  upgradeConstitutionApi,
} from '../api/constitution'
import type { ConstitutionBag, ConstitutionState } from '../types/constitution'
import { useCharacterStore } from '../stores/character'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const characterStore = useCharacterStore()
const open = ref(true)
const busy = ref(false)
const state = ref<ConstitutionState | null>(null)
const selectedItemId = ref<number | null>(null)

async function reload(): Promise<void> {
  const envelope = await fetchConstitutionApi()
  if (envelope.code !== 0 || !envelope.data) {
    throw new Error(envelope.message || '加载体质失败')
  }
  state.value = envelope.data
}

onMounted(() => {
  void reload().catch((e: unknown) => {
    const message = e instanceof Error ? e.message : '加载体质失败'
    ElMessage.error(message)
  })
})

function itemInSlot(slotType: string, slotIndex: number): ConstitutionBag | null {
  if (!state.value) return null
  const slot = state.value.slots.find(
    (s) => s.slot_type === slotType && s.slot_index === slotIndex,
  )
  if (!slot?.item_id) return null
  return state.value.backpack.find((b) => b.id === slot.item_id) ?? null
}

async function onEquip(slotType: 'main' | 'sub', slotIndex: number): Promise<void> {
  if (busy.value || selectedItemId.value == null) {
    ElMessage.info('请先在背包中选中一件物品')
    return
  }
  busy.value = true
  try {
    const envelope = await equipConstitutionApi({
      item_id: selectedItemId.value,
      slot_type: slotType,
      slot_index: slotIndex,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '镶嵌失败')
    }
    state.value = envelope.data.constitution
    ElMessage.success('镶嵌成功')
    emit('log', `体质镶嵌：格 ${slotType}#${slotIndex}`, 'success')
    await characterStore.fetchMe()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '镶嵌失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onUnequip(slotType: 'main' | 'sub', slotIndex: number): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await unequipConstitutionApi({
      slot_type: slotType,
      slot_index: slotIndex,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '卸下失败')
    }
    state.value = envelope.data.constitution
    ElMessage.success('已卸下')
    emit('log', `体质卸下：格 ${slotType}#${slotIndex}`, 'info')
    await characterStore.fetchMe()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '卸下失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onUpgrade(): Promise<void> {
  if (selectedItemId.value == null) {
    ElMessage.info('请先选中背包物品')
    return
  }
  busy.value = true
  try {
    const envelope = await upgradeConstitutionApi(selectedItemId.value)
    if (envelope.code !== 0) {
      throw new Error(envelope.message || '升品失败')
    }
    ElMessage.success(String(envelope.data?.message ?? '升品占位成功'))
    emit('log', String(envelope.data?.message ?? '体质升品占位'), 'system')
    await reload()
    await characterStore.fetchMe()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '升品失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onFuse(): Promise<void> {
  if (!state.value) return
  const free = state.value.backpack.filter((b) => !b.is_equipped).slice(0, 2)
  if (free.length < 2) {
    ElMessage.info('至少需要 2 件未镶嵌物品做融合占位')
    return
  }
  busy.value = true
  try {
    const envelope = await fuseConstitutionApi(free.map((b) => b.id))
    if (envelope.code !== 0) {
      throw new Error(envelope.message || '融合失败')
    }
    ElMessage.success(String(envelope.data?.message ?? '融合占位成功'))
    emit('log', String(envelope.data?.message ?? '体质融合占位'), 'system')
    await reload()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '融合失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="cons-panel">
    <template #header>
      <div class="cons-header" @click="open = !open">
        <el-text tag="b">体质</el-text>
        <el-text size="small" type="info">{{ open ? '收起' : '展开' }}</el-text>
      </div>
    </template>

    <div v-show="open">
      <el-text size="small" type="info" class="hint">
        初始 1 主格 + 2 副格；选中背包物品后点击空格镶嵌。
      </el-text>

      <div v-if="state" class="slots">
        <div
          v-for="slot in state.slots"
          :key="`${slot.slot_type}-${slot.slot_index}`"
          class="slot"
        >
          <el-text size="small">
            {{ slot.slot_type === 'main' ? '主格' : '副格' }} #{{ slot.slot_index }}
          </el-text>
          <div class="slot-body">
            <template v-if="itemInSlot(slot.slot_type, slot.slot_index)">
              <el-tag size="small">
                {{ itemInSlot(slot.slot_type, slot.slot_index)?.name }}
              </el-tag>
              <el-button
                size="small"
                link
                type="danger"
                :loading="busy"
                @click="onUnequip(slot.slot_type as 'main' | 'sub', slot.slot_index)"
              >
                卸下
              </el-button>
            </template>
            <el-button
              v-else
              size="small"
              :loading="busy"
              @click="onEquip(slot.slot_type as 'main' | 'sub', slot.slot_index)"
            >
              镶嵌选中
            </el-button>
          </div>
        </div>
      </div>

      <el-divider content-position="left">背包</el-divider>
      <div v-if="state" class="bag">
        <el-check-tag
          v-for="item in state.backpack"
          :key="item.id"
          :checked="selectedItemId === item.id"
          :disabled="item.is_equipped"
          class="bag-item"
          @change="(checked: boolean) => { if (checked) selectedItemId = item.id }"
        >
          {{ item.name }}
          <el-text size="small" type="info">
            （{{ item.kind }}{{ item.is_equipped ? '·已镶嵌' : '' }}）
          </el-text>
        </el-check-tag>
      </div>

      <div class="ops">
        <el-button size="small" :loading="busy" @click="onUpgrade">升品（占位）</el-button>
        <el-button size="small" :loading="busy" @click="onFuse">融合（占位）</el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.cons-header {
  display: flex;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.hint {
  display: block;
  margin-bottom: 0.5rem;
}

.slots {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.slot {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.4rem 0.5rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
}

.slot-body {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.bag {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.bag-item {
  cursor: pointer;
}

.ops {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
