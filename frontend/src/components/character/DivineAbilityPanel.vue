<script setup lang="ts">
/**
 * 角色页神通：点槽从神通池装备；无主副之分；格数随修为+品阶。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  equipDivineAbilityApi,
  fetchMyDivineAbilitiesApi,
  unequipDivineAbilityApi,
} from '../../api/divineAbilities'
import type {
  DivineAbilityItem,
  DivineAbilityLoadout,
  DivineAbilitySlotView,
} from '../../types/divineAbilities'
import type { PoolCandidate } from '../../types/itemHover'
import {
  hoverFromDivine,
  hoverFromDivineSlot,
  shortItemName,
} from '../../utils/itemHoverFormat'
import ItemHoverTip from './ItemHoverTip.vue'
import PoolPickerGrid from './PoolPickerGrid.vue'

const props = withDefaults(
  defineProps<{
    actor?: 'main' | 'avatar'
  }>(),
  { actor: 'main' },
)

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const HELP_FALLBACK = '神通装备数量与修为和品阶相关'
const ZH_ORDINAL = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

const loading = ref(false)
const busy = ref(false)
const open = ref(false)
const items = ref<DivineAbilityItem[]>([])
const loadout = ref<DivineAbilityLoadout | null>(null)
const selectedIndex = ref<number | null>(null)

function slotPhrase(slotIndex: number): string {
  return `神通${ZH_ORDINAL[slotIndex] ?? String(slotIndex + 1)}`
}

const equippedCount = computed(
  () => loadout.value?.slots.filter((s) => Boolean(s.ability_id)).length ?? 0,
)
const slotTotal = computed(() => loadout.value?.slot_cap ?? 0)
const helpZh = computed(() => loadout.value?.help_zh?.trim() || HELP_FALLBACK)
const slots = computed(() => loadout.value?.slots ?? [])

function applyPage(data: { items?: DivineAbilityItem[]; loadout?: DivineAbilityLoadout }): void {
  items.value = data.items || []
  loadout.value = data.loadout ?? null
}

async function reload(): Promise<void> {
  loading.value = true
  try {
    const env = await fetchMyDivineAbilitiesApi(props.actor)
    if (env.code !== 0 || !env.data) {
      ElMessage.error(env.message || '加载神通失败')
      return
    }
    applyPage(env.data)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void reload()
})

watch(
  () => props.actor,
  () => {
    void reload()
  },
)

function shortName(name: string): string {
  return shortItemName(name)
}

function firstBorder(slot: DivineAbilitySlotView): string | undefined {
  return slot.elements?.[0]?.border
}

function onClickSlot(slot: DivineAbilitySlotView): void {
  if (selectedIndex.value === slot.slot_index) {
    selectedIndex.value = null
    return
  }
  selectedIndex.value = slot.slot_index
}

const pickerCandidates = computed((): PoolCandidate[] => {
  if (selectedIndex.value == null) return []
  const currentId = slots.value.find((s) => s.slot_index === selectedIndex.value)?.ability_id
  const equipped = new Set(
    slots.value.map((s) => s.ability_id).filter((id): id is string => Boolean(id)),
  )
  return items.value
    .filter((it) => !equipped.has(it.id) || it.id === currentId)
    .map((it) => ({
      key: it.id,
      shortName: shortItemName(it.name),
      worn: Boolean(currentId && it.id === currentId),
      hover: hoverFromDivine(it),
      border: it.elements?.[0]?.border,
    }))
})

function slotHover(slot: DivineAbilitySlotView) {
  return hoverFromDivineSlot(slot) ?? { name: slot.label_zh || '空' }
}

async function onPickCandidate(item: PoolCandidate): Promise<void> {
  if (item.worn) {
    await onUnequip()
    return
  }
  await onEquip(item.key)
}

const selectedPhrase = computed(() => {
  if (selectedIndex.value == null) return ''
  return slotPhrase(selectedIndex.value)
})

async function onEquip(abilityId: string): Promise<void> {
  if (busy.value || selectedIndex.value == null) return
  busy.value = true
  try {
    const envelope = await equipDivineAbilityApi({
      ability_id: abilityId,
      slot_index: selectedIndex.value,
      actor: props.actor,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '装备失败')
    }
    const name = items.value.find((b) => b.id === abilityId)?.name ?? '神通'
    applyPage(envelope.data)
    ElMessage.success('装备成功')
    emit('log', `神通装备：${name} → ${selectedPhrase.value}`, 'success')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '装备失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function onUnequip(): Promise<void> {
  if (busy.value || selectedIndex.value == null) return
  busy.value = true
  try {
    const envelope = await unequipDivineAbilityApi({
      slot_index: selectedIndex.value,
      actor: props.actor,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '卸下失败')
    }
    applyPage(envelope.data)
    ElMessage.success('已卸下')
    emit('log', `神通卸下：${selectedPhrase.value}`, 'info')
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
  <el-card shadow="never" class="divine-panel" v-loading="loading">
    <template #header>
      <div class="divine-header" @click="open = !open">
        <el-text tag="b" size="small">神通</el-text>
        <el-text size="small" type="info">已装 {{ equippedCount }}/{{ slotTotal }}</el-text>
        <el-tooltip
          :content="helpZh"
          placement="bottom-end"
          effect="dark"
          trigger="hover"
          :show-after="200"
          popper-class="game-hover-tip"
        >
          <button type="button" class="divine-info" aria-label="查看神通槽说明" @click.stop>
            <el-icon :size="14"><InfoFilled /></el-icon>
          </button>
        </el-tooltip>
        <el-text size="small" type="info" class="divine-toggle">
          {{ open ? '收起' : '展开' }}
        </el-text>
      </div>
    </template>

    <div v-show="open">
      <el-text v-if="slotTotal <= 0" size="small" type="info" class="empty-hint">
        当前修为与品阶尚未解锁神通槽。
      </el-text>
      <div v-else class="divine-board">
        <div class="divine-cells">
          <el-tooltip
            v-for="slot in slots"
            :key="slot.slot_index"
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
              class="divine-cell"
              :class="{
                'slot-filled': Boolean(slot.ability_id),
                'slot-selected': selectedIndex === slot.slot_index,
              }"
              :style="firstBorder(slot) ? { borderColor: firstBorder(slot) } : undefined"
              @click="onClickSlot(slot)"
            >
              <span class="cell-caption">
                {{ slot.name ? shortName(slot.name) : '' }}
              </span>
            </button>
          </el-tooltip>
        </div>
      </div>

      <PoolPickerGrid
        v-if="selectedIndex != null"
        :title="`已学 · ${selectedPhrase}`"
        empty-text="暂无可装备神通"
        :items="pickerCandidates"
        :busy="busy"
        @pick="onPickCandidate"
      />
    </div>
  </el-card>
</template>

<style scoped>
.divine-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
  cursor: pointer;
  user-select: none;
}

.divine-toggle {
  margin-left: auto;
}

.divine-info {
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
}

.divine-info:hover {
  color: var(--el-color-primary);
}

.divine-board {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
}

.divine-cells {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.4rem;
}

.divine-cell {
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

.empty-hint {
  display: block;
  text-align: center;
  margin-bottom: 0.5rem;
}
</style>
