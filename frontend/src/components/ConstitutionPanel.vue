<script setup lang="ts">
/**
 * 体质：本源一格 + 旁支多格；点槽打开收藏区（不进道具背包）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  equipConstitutionApi,
  fetchConstitutionApi,
  unequipConstitutionApi,
} from '../api/constitution'
import type { ConstitutionBag, ConstitutionSlotView, ConstitutionState } from '../types/constitution'
import type { PoolCandidate } from '../types/itemHover'
import { hoverFromConstitution, shortItemName } from '../utils/itemHoverFormat'
import ItemHoverTip from './character/ItemHoverTip.vue'
import PoolPickerGrid from './character/PoolPickerGrid.vue'
import { useCharacterStore } from '../stores/character'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const HELP_FALLBACK = '可以通过轮回点购买更多体质槽'
const ZH_ORDINAL = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二']

function slotPhrase(slotType: string, slotIndex: number): string {
  if (slotType !== 'sub') return '本源'
  return `旁支${ZH_ORDINAL[slotIndex] ?? String(slotIndex + 1)}`
}

const characterStore = useCharacterStore()
const open = ref(false)
const busy = ref(false)
const state = ref<ConstitutionState | null>(null)
const selectedSlot = ref<{ slot_type: 'main' | 'sub'; slot_index: number } | null>(null)

const equippedCount = computed(
  () => state.value?.slots.filter((s) => Boolean(s.item_id)).length ?? 0,
)
const slotTotal = computed(() => state.value?.slot_count ?? state.value?.slots.length ?? 0)
const helpZh = computed(() => state.value?.help_zh?.trim() || HELP_FALLBACK)

const collection = computed((): ConstitutionBag[] => {
  if (!state.value) return []
  return state.value.collection ?? state.value.backpack ?? []
})

const mainSlots = computed(() =>
  (state.value?.slots ?? []).filter((s) => s.slot_type === 'main'),
)
const subSlots = computed(() =>
  (state.value?.slots ?? []).filter((s) => s.slot_type === 'sub'),
)

function slotKey(slot: Pick<ConstitutionSlotView, 'slot_type' | 'slot_index'>): string {
  return `${slot.slot_type}-${slot.slot_index}`
}

function isSelected(slot: ConstitutionSlotView): boolean {
  return (
    selectedSlot.value?.slot_type === slot.slot_type &&
    selectedSlot.value?.slot_index === slot.slot_index
  )
}

function itemInSlot(slot: ConstitutionSlotView): ConstitutionBag | null {
  if (!slot.item_id) return null
  return collection.value.find((b) => b.id === slot.item_id) ?? null
}

function shortName(name: string): string {
  return shortItemName(name)
}

function slotHover(slot: ConstitutionSlotView) {
  const item = itemInSlot(slot)
  if (!item) return { name: slotPhrase(slot.slot_type, slot.slot_index), helpZh: '空' }
  return hoverFromConstitution(item)
}

const pickerCandidates = computed((): PoolCandidate[] => {
  if (!selectedSlot.value) return []
  const currentId = state.value?.slots.find(
    (s) =>
      s.slot_type === selectedSlot.value?.slot_type &&
      s.slot_index === selectedSlot.value?.slot_index,
  )?.item_id
  return collection.value
    .filter((item) => !item.is_equipped || item.id === currentId)
    .map((item) => ({
      key: String(item.id),
      shortName: shortItemName(item.name),
      worn: Boolean(currentId && item.id === currentId),
      hover: hoverFromConstitution(item),
    }))
})

async function onPickCandidate(item: PoolCandidate): Promise<void> {
  if (item.worn) {
    await onUnequip()
    return
  }
  await onEquip(Number(item.key))
}

const selectedPhrase = computed(() => {
  if (!selectedSlot.value) return ''
  return slotPhrase(selectedSlot.value.slot_type, selectedSlot.value.slot_index)
})

function selectedSlotView(): ConstitutionSlotView | null {
  if (!selectedSlot.value || !state.value) return null
  return (
    state.value.slots.find(
      (s) =>
        s.slot_type === selectedSlot.value?.slot_type &&
        s.slot_index === selectedSlot.value?.slot_index,
    ) ?? null
  )
}

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

function onClickSlot(slot: ConstitutionSlotView): void {
  const type = slot.slot_type === 'sub' ? 'sub' : 'main'
  if (isSelected(slot)) {
    selectedSlot.value = null
    return
  }
  selectedSlot.value = { slot_type: type, slot_index: slot.slot_index }
}

async function onEquip(itemId: number): Promise<void> {
  if (busy.value || !selectedSlot.value) return
  busy.value = true
  try {
    const envelope = await equipConstitutionApi({
      item_id: itemId,
      slot_type: selectedSlot.value.slot_type,
      slot_index: selectedSlot.value.slot_index,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '镶嵌失败')
    }
    const itemName = collection.value.find((b) => b.id === itemId)?.name ?? '体质'
    const where = selectedPhrase.value
    state.value = envelope.data.constitution
    ElMessage.success('镶嵌成功')
    emit('log', `体质镶嵌：${itemName} → ${where}`, 'success')
    await characterStore.fetchMe()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '镶嵌失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onUnequip(): Promise<void> {
  if (busy.value || !selectedSlot.value) return
  busy.value = true
  try {
    const envelope = await unequipConstitutionApi({
      slot_type: selectedSlot.value.slot_type,
      slot_index: selectedSlot.value.slot_index,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '卸下失败')
    }
    const slot = selectedSlotView()
    const worn = slot ? itemInSlot(slot) : null
    const where = selectedPhrase.value
    const itemName = worn?.name
    state.value = envelope.data.constitution
    ElMessage.success('已卸下')
    emit('log', itemName ? `体质卸下：${where}（${itemName}）` : `体质卸下：${where}`, 'info')
    await characterStore.fetchMe()
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '卸下失败'
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
        <el-text tag="b" size="small">体质</el-text>
        <el-text size="small" type="info">已镶 {{ equippedCount }}/{{ slotTotal || 3 }}</el-text>
        <el-tooltip
          :content="helpZh"
          placement="bottom-end"
          effect="dark"
          trigger="hover"
          :show-after="200"
          popper-class="game-hover-tip constitution-slot-tip"
        >
          <button
            type="button"
            class="cons-info"
            aria-label="查看体质槽说明"
            @click.stop
          >
            <el-icon :size="14"><InfoFilled /></el-icon>
          </button>
        </el-tooltip>
        <el-text size="small" type="info" class="cons-toggle">
          {{ open ? '收起' : '展开' }}
        </el-text>
      </div>
    </template>

    <div v-show="open">
      <div v-if="state" class="cons-board">
        <div class="cons-group">
          <el-text size="small" class="cons-group-label">本源</el-text>
          <div class="cons-cells">
            <el-tooltip
              v-for="slot in mainSlots"
              :key="slotKey(slot)"
              effect="dark"
              placement="top"
              :show-after="200"
              popper-class="game-hover-tip item-hover-tip"
            >
              <template #content>
                <ItemHoverTip :model="slotHover(slot)" />
              </template>
              <button
                type="button"
                class="cons-cell cons-cell-main"
                :class="{
                  'slot-filled': Boolean(slot.item_id),
                  'slot-selected': isSelected(slot),
                }"
                @click="onClickSlot(slot)"
              >
                <span class="cell-caption">
                  {{ itemInSlot(slot) ? shortName(itemInSlot(slot)!.name) : '空' }}
                </span>
              </button>
            </el-tooltip>
          </div>
        </div>
        <div class="cons-group">
          <el-text size="small" class="cons-group-label">旁支</el-text>
          <div class="cons-cells">
            <el-tooltip
              v-for="slot in subSlots"
              :key="slotKey(slot)"
              effect="dark"
              placement="top"
              :show-after="200"
              popper-class="game-hover-tip item-hover-tip"
            >
              <template #content>
                <ItemHoverTip :model="slotHover(slot)" />
              </template>
              <button
                type="button"
                class="cons-cell"
                :class="{
                  'slot-filled': Boolean(slot.item_id),
                  'slot-selected': isSelected(slot),
                }"
                @click="onClickSlot(slot)"
              >
                <span class="cell-caption">
                  {{ itemInSlot(slot) ? shortName(itemInSlot(slot)!.name) : '' }}
                </span>
              </button>
            </el-tooltip>
          </div>
        </div>
      </div>

      <PoolPickerGrid
        v-if="selectedSlot"
        :title="`收集 · ${selectedPhrase}`"
        empty-text="尚未收集体质"
        :items="pickerCandidates"
        :busy="busy"
        @pick="onPickCandidate"
      />
    </div>
  </el-card>
</template>

<style scoped>
.cons-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
  cursor: pointer;
  user-select: none;
}

.cons-toggle {
  margin-left: auto;
}

.cons-info {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 1.15rem;
  height: 1.15rem;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--el-color-info);
  cursor: help;
  vertical-align: middle;
}

.cons-info:hover {
  color: var(--el-color-primary);
}

.cons-board {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
}

.cons-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  width: 100%;
}

.cons-group-label {
  color: var(--el-text-color-regular);
}

.cons-cells {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.4rem;
  min-width: 0;
}

.cons-cell {
  width: 48px;
  height: 48px;
  padding: 0.1rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cons-cell-main {
  width: 56px;
  height: 56px;
  border-color: var(--el-color-primary-light-5);
}

.cons-cell:hover {
  border-color: var(--el-color-primary-light-5);
}

.slot-filled {
  border-style: solid;
}

.slot-selected {
  box-shadow: 0 0 0 2px #c9930f;
}

.cell-caption {
  font-size: 12px;
  line-height: 1.15;
  text-align: center;
  color: var(--el-text-color-regular);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
