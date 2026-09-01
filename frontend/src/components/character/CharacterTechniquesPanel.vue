<script setup lang="ts">
/**
 * 角色页功法：主功法一格 + 技法多格；点槽装备已学功法。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import {
  equipTechniqueApi,
  fetchMyTechniquesApi,
  unequipTechniqueApi,
} from '../../api/techniques'
import type {
  TechniqueItem,
  TechniqueLoadout,
  TechniqueSlotView,
} from '../../types/techniques'
import type { PoolCandidate } from '../../types/itemHover'
import {
  hoverFromTechnique,
  hoverFromTechniqueSlot,
} from '../../utils/itemHoverFormat'
import ItemSlotVisual from '../common/ItemSlotVisual.vue'
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

const HELP_FALLBACK = '主功法只能装备一本；技法可装备多本，修为越高槽位越多。'
const ZH_ORDINAL = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

const router = useRouter()
const loading = ref(false)
const busy = ref(false)
const open = ref(false)
const items = ref<TechniqueItem[]>([])
const loadout = ref<TechniqueLoadout | null>(null)
const selectedSlot = ref<{ slot_type: 'main' | 'art'; slot_index: number } | null>(null)

function slotPhrase(slotType: string, slotIndex: number): string {
  if (slotType !== 'art') return '主功法'
  return `技法${ZH_ORDINAL[slotIndex] ?? String(slotIndex + 1)}`
}

const equippedCount = computed(
  () => loadout.value?.slots.filter((s) => Boolean(s.technique_id)).length ?? 0,
)
const slotTotal = computed(() => loadout.value?.slots.length ?? 0)
const helpZh = computed(() => loadout.value?.help_zh?.trim() || HELP_FALLBACK)
const grantedSkills = computed(() => loadout.value?.granted_skills ?? [])

const mainSlots = computed(
  () => (loadout.value?.slots ?? []).filter((s) => s.slot_type === 'main'),
)
const artSlots = computed(
  () => (loadout.value?.slots ?? []).filter((s) => s.slot_type === 'art'),
)

function slotKey(slot: Pick<TechniqueSlotView, 'slot_type' | 'slot_index'>): string {
  return `${slot.slot_type}-${slot.slot_index}`
}

function isSelected(slot: TechniqueSlotView): boolean {
  return (
    selectedSlot.value?.slot_type === slot.slot_type &&
    selectedSlot.value?.slot_index === slot.slot_index
  )
}

function firstBorder(slot: TechniqueSlotView): string | undefined {
  return slot.elements?.[0]?.border
}

function applyPage(data: { items?: TechniqueItem[]; loadout?: TechniqueLoadout }): void {
  items.value = data.items || []
  loadout.value = data.loadout ?? null
}

async function reload(): Promise<void> {
  loading.value = true
  try {
    const env = await fetchMyTechniquesApi(props.actor)
    if (env.code !== 0 || !env.data) {
      ElMessage.error(env.message || '加载功法失败')
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

function onClickSlot(slot: TechniqueSlotView): void {
  const type = slot.slot_type === 'art' ? 'art' : 'main'
  if (isSelected(slot)) {
    selectedSlot.value = null
    return
  }
  selectedSlot.value = { slot_type: type, slot_index: slot.slot_index }
}

const pickerCandidates = computed((): PoolCandidate[] => {
  if (!selectedSlot.value) return []
  const currentId = loadout.value?.slots.find(
    (s) =>
      s.slot_type === selectedSlot.value?.slot_type &&
      s.slot_index === selectedSlot.value?.slot_index,
  )?.technique_id
  const equipped = new Set(
    (loadout.value?.slots ?? [])
      .map((s) => s.technique_id)
      .filter((id): id is string => Boolean(id)),
  )
  return items.value
    .filter((it) => !equipped.has(it.id) || it.id === currentId)
    .map((it) => ({
      key: it.id,
      name: it.name,
      icon: it.icon || it.id,
      worn: Boolean(currentId && it.id === currentId),
      hover: hoverFromTechnique(it),
      border: it.elements?.[0]?.border,
    }))
})

function slotHover(slot: TechniqueSlotView) {
  return hoverFromTechniqueSlot(slot) ?? { name: slot.label_zh || '空' }
}

async function onPickCandidate(item: PoolCandidate): Promise<void> {
  if (item.worn) {
    await onUnequip()
    return
  }
  await onEquip(item.key)
}

const selectedPhrase = computed(() => {
  if (!selectedSlot.value) return ''
  return slotPhrase(selectedSlot.value.slot_type, selectedSlot.value.slot_index)
})

async function onEquip(techniqueId: string): Promise<void> {
  if (busy.value || !selectedSlot.value) return
  busy.value = true
  try {
    const envelope = await equipTechniqueApi({
      technique_id: techniqueId,
      slot_type: selectedSlot.value.slot_type,
      slot_index: selectedSlot.value.slot_index,
      actor: props.actor,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '装备失败')
    }
    const name = items.value.find((b) => b.id === techniqueId)?.name ?? '功法'
    applyPage(envelope.data)
    ElMessage.success('装备成功')
    emit('log', `功法装备：${name} → ${selectedPhrase.value}`, 'success')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : '装备失败'
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
    const envelope = await unequipTechniqueApi({
      slot_type: selectedSlot.value.slot_type,
      slot_index: selectedSlot.value.slot_index,
      actor: props.actor,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '卸下失败')
    }
    applyPage(envelope.data)
    ElMessage.success('已卸下')
    emit('log', `功法卸下：${selectedPhrase.value}`, 'info')
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
  <el-card shadow="never" class="tech-panel" v-loading="loading">
    <template #header>
      <div class="tech-header" @click="open = !open">
        <el-text tag="b" size="small">功法</el-text>
        <el-text size="small" type="info">已装 {{ equippedCount }}/{{ slotTotal || 2 }}</el-text>
        <el-tooltip
          :content="helpZh"
          placement="bottom-end"
          effect="dark"
          trigger="hover"
          :show-after="200"
          popper-class="game-hover-tip"
        >
          <button type="button" class="tech-info" aria-label="查看功法槽说明" @click.stop>
            <el-icon :size="14"><InfoFilled /></el-icon>
          </button>
        </el-tooltip>
        <el-button
          size="small"
          type="primary"
          plain
          @click.stop="router.push('/cave/lab?mode=technique')"
        >
          去研究室
        </el-button>
        <el-text size="small" type="info" class="tech-toggle">
          {{ open ? '收起' : '展开' }}
        </el-text>
      </div>
    </template>

    <div v-show="open">
      <div v-if="loadout" class="tech-board">
        <div class="tech-group">
          <el-text size="small" class="tech-group-label">主功法</el-text>
          <div class="tech-cells">
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
                class="tech-cell tech-cell-main"
                :class="{
                  'slot-filled': Boolean(slot.technique_id),
                  'slot-selected': isSelected(slot),
                }"
                :style="firstBorder(slot) ? { borderColor: firstBorder(slot) } : undefined"
                @click="onClickSlot(slot)"
              >
                <span class="cell-caption">
                  <ItemSlotVisual
                    :name="slot.name || ''"
                    :icon="slot.technique_id ? slot.icon || slot.technique_id : null"
                    empty-text="空"
                  />
                </span>
              </button>
            </el-tooltip>
          </div>
        </div>
        <div class="tech-group">
          <el-text size="small" class="tech-group-label">技法</el-text>
          <div class="tech-cells">
            <el-tooltip
              v-for="slot in artSlots"
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
                class="tech-cell"
                :class="{
                  'slot-filled': Boolean(slot.technique_id),
                  'slot-selected': isSelected(slot),
                }"
                :style="firstBorder(slot) ? { borderColor: firstBorder(slot) } : undefined"
                @click="onClickSlot(slot)"
              >
                <span class="cell-caption">
                  <ItemSlotVisual
                    :name="slot.name || ''"
                    :icon="slot.technique_id ? slot.icon || slot.technique_id : null"
                    empty-text=""
                  />
                </span>
              </button>
            </el-tooltip>
          </div>
        </div>
      </div>

      <div v-if="grantedSkills.length" class="skill-row">
        <el-text size="small" tag="b">技能</el-text>
        <el-tooltip
          v-for="sk in grantedSkills"
          :key="sk.id"
          :content="sk.effect_zh || sk.label_zh"
          placement="top"
          effect="dark"
          :show-after="150"
          popper-class="game-hover-tip"
        >
          <el-tag size="small" effect="plain" class="skill-chip">{{ sk.label_zh }}</el-tag>
        </el-tooltip>
      </div>

      <PoolPickerGrid
        v-if="selectedSlot"
        :title="`已学 · ${selectedPhrase}`"
        empty-text="暂无可装备功法"
        :items="pickerCandidates"
        :busy="busy"
        @pick="onPickCandidate"
      />
    </div>
  </el-card>
</template>

<style scoped>
.tech-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
  cursor: pointer;
  user-select: none;
}

.tech-toggle {
  margin-left: auto;
}

.tech-info {
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

.tech-info:hover {
  color: var(--el-color-primary);
}

.tech-board {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
}

.tech-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  width: 100%;
}

.tech-group-label {
  color: var(--el-text-color-regular);
}

.tech-cells {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.4rem;
}

.tech-cell {
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

.tech-cell-main {
  width: 56px;
  height: 56px;
}

.slot-filled {
  border-style: solid;
}

.slot-selected {
  box-shadow: 0 0 0 2px #c9930f;
}

.cell-caption {
  display: block;
  width: 100%;
  height: 100%;
  color: var(--el-text-color-regular);
}

.skill-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.65rem;
}

.skill-chip {
  cursor: help;
}
</style>
