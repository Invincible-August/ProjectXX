<script setup lang="ts">
/**
 * Equipment 17-zone paper doll (M8) — silhouette + side slots + fold.
 * Slot ids align with backend app.constants.equipment.
 * Two-handed weapons share the same item_uid on weapon_1 and weapon_2.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import type {
  EquipmentSlot,
  EquipmentSlotPublic,
  EquipmentStatPreview,
  PuppetLoadoutEntry,
  TalismanLoadoutEntry,
} from '../../types/equipment'
import type { PoolCandidate } from '../../types/itemHover'
import {
  hoverFromEquipment,
  hoverFromSlotPublic,
  shortItemName,
} from '../../utils/itemHoverFormat'
import ItemHoverTip from './ItemHoverTip.vue'
import PoolPickerGrid from './PoolPickerGrid.vue'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useCharacterStore } from '../../stores/character'
import { useEquipmentStore } from '../../stores/equipment'
import { puppetSenseFromLoad } from '../../utils/puppetSensePreview'

const props = withDefaults(
  defineProps<{
    /** 化身页隐藏傀儡 / 灵宠 / 符宝 / 符箓 */
    actor?: 'main' | 'avatar'
  }>(),
  { actor: 'main' },
)

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const equipmentStore = useEquipmentStore()
const characterStore = useCharacterStore()
const { writeBlocked, writeBlockReason } = usePlayWriteGate()
const open = ref(false)
const busy = ref(false)
const puppetPickerOpen = ref(false)
const pendingPuppetUids = ref<string[]>([])
const talismanPickerOpen = ref(false)
const pendingTalismanUids = ref<string[]>([])
const selectedSlot = ref<EquipmentSlot | null>(null)
const flashSlot = ref<EquipmentSlot | null>(null)

const state = computed(() => equipmentStore.slotsState)
const channelEnabled = computed(
  () => state.value?.channels.combat_equipment.enabled ?? false,
)

const isAvatarActor = computed(() => props.actor === 'avatar')

/** Left column around the silhouette. */
const DOLL_LEFT = computed((): EquipmentSlot[] => {
  const slots: EquipmentSlot[] = [
    'armor_head',
    'accessory_1',
    'armor_chest',
    'fabao_1',
    'fabao_2',
    'natal_fabao',
  ]
  if (!isAvatarActor.value) slots.push('fubao')
  return slots
})
/** Right column around the silhouette. */
const DOLL_RIGHT = computed((): EquipmentSlot[] => {
  const slots: EquipmentSlot[] = [
    'armor_hands',
    'armor_legs',
    'armor_shoes',
    'ring_1',
    'ring_2',
    'accessory_2',
  ]
  if (!isAvatarActor.value) slots.push('pet')
  return slots
})
/** Bottom-most row, centered. */
const DOLL_WEAPONS: EquipmentSlot[] = ['weapon_1', 'weapon_2']

const slotById = computed(() => {
  const map = new Map<string, EquipmentSlotPublic>()
  for (const s of state.value?.slots ?? []) {
    map.set(s.slot, s)
  }
  return map
})

const weaponShared = computed(() => {
  const w1 = slotById.value.get('weapon_1')
  const w2 = slotById.value.get('weapon_2')
  if (!w1?.item_uid || !w2?.item_uid) return false
  return w1.item_uid === w2.item_uid
})

const equippedCount = computed(
  () => (state.value?.slots ?? []).filter((s) => Boolean(s.item_uid)).length,
)
const pointerSlotTotal = computed(() => (state.value?.slots ?? []).length)

const allPuppets = computed((): PuppetLoadoutEntry[] => {
  const loadout = state.value?.puppet_loadout ?? []
  const bag = state.value?.bag_puppets ?? []
  return [...loadout, ...bag]
})

const savedPuppetUids = computed(() =>
  (state.value?.puppet_loadout ?? []).map((p) => p.item_uid),
)

const savedPuppetNames = computed(() =>
  (state.value?.puppet_loadout ?? []).map((p) => p.label_zh).join('、'),
)

const activePuppetUids = computed(() =>
  puppetPickerOpen.value ? pendingPuppetUids.value : savedPuppetUids.value,
)

const puppetLoadoutMax = computed(
  () => state.value?.puppet_sense?.max_count ?? 3,
)

const PUPPET_SENSE_HELP_FALLBACK =
  '上阵傀儡最多不得超过3个，神识消耗总量超过最大神识后，傀儡强度将会受到削弱'

const puppetSenseHelp = computed(
  () => state.value?.puppet_sense?.help_zh?.trim() || PUPPET_SENSE_HELP_FALLBACK,
)

/** 分母：角色面板神识容量（character.divine_sense.capacity）。 */
const characterSenseCap = computed(() => {
  const fromChar = characterStore.character?.divine_sense?.capacity
  if (typeof fromChar === 'number' && fromChar > 0) return fromChar
  return state.value?.puppet_sense?.capacity ?? 0
})

const livePuppetSense = computed(() => {
  const spec = state.value?.puppet_sense
  const selected = new Set(activePuppetUids.value)
  const fallbackCost = spec?.default_cost ?? 0
  let load = 0
  for (const p of allPuppets.value) {
    if (!selected.has(p.item_uid)) continue
    if (p.counts_toward_load === false) continue
    load += p.divine_sense_cost ?? fallbackCost
  }
  const cap = characterSenseCap.value
  const previewSpec = spec
    ? { ...spec, capacity: cap, soft_cap: cap }
    : spec
  return puppetSenseFromLoad(load, previewSpec)
})

const puppetSenseTagType = computed(() => {
  const zone = livePuppetSense.value.zone
  if (zone === 'critical') return 'danger'
  if (zone === 'overload') return 'warning'
  return 'success'
})

const selectedCell = computed(() => {
  if (!selectedSlot.value) return null
  return slotById.value.get(selectedSlot.value) ?? null
})

interface SlotCandidate {
  item_uid: string
  name: string
  worn: boolean
  stats?: Record<string, EquipmentStatPreview>
}

function statsPreviewOf(
  preview: Record<string, EquipmentStatPreview> | undefined,
): Record<string, EquipmentStatPreview> {
  return preview ?? {}
}

const slotCandidates = computed((): SlotCandidate[] => {
  const slot = selectedSlot.value
  if (!slot || !state.value) return []
  const cell = slotById.value.get(slot)
  const rows: SlotCandidate[] = []
  if (cell?.item_uid && cell.item_label_zh) {
    rows.push({
      item_uid: cell.item_uid,
      name: cell.item_label_zh,
      worn: true,
      stats: cell.stats_preview,
    })
  }
  for (const item of state.value.bag_equipment) {
    if (cell?.item_uid && item.item_uid === cell.item_uid) continue
    const compat = item.compatible_slots ?? []
    if (!compat.includes(slot)) continue
    rows.push({
      item_uid: item.item_uid,
      name: item.name,
      worn: false,
      stats: statsPreviewOf(item.stats_preview),
    })
  }
  return rows
})

const pickerCandidates = computed((): PoolCandidate[] => {
  const slotLabel = selectedCell.value?.slot_label_zh
  return slotCandidates.value.map((row) => ({
    key: row.item_uid,
    shortName: shortItemName(row.name),
    worn: row.worn,
    hover: hoverFromEquipment({
      name: row.name,
      slotLabelZh: slotLabel,
      stats: row.stats,
    }),
  }))
})

function slotHover(id: EquipmentSlot) {
  if (id === 'weapon_2' && weaponShared.value) {
    return hoverFromSlotPublic(slotById.value.get('weapon_1'))
  }
  return hoverFromSlotPublic(slotById.value.get(id))
}

async function onPickCandidate(item: PoolCandidate): Promise<void> {
  if (!selectedSlot.value) return
  if (item.worn) {
    await onUnequip(selectedSlot.value)
    return
  }
  await onEquip(item.key)
}

async function reload(): Promise<void> {
  const ok = await equipmentStore.refresh(props.actor)
  if (!ok) {
    throw new Error('加载装备失败')
  }
}

onMounted(() => {
  void reload().catch((e: unknown) => {
    const message = e instanceof Error ? e.message : '加载装备失败'
    ElMessage.error(message)
  })
})

watch(
  () => props.actor,
  () => {
    void reload().catch((e: unknown) => {
      const message = e instanceof Error ? e.message : '加载装备失败'
      ElMessage.error(message)
    })
  },
)

function slotCaption(id: EquipmentSlot): string {
  const cell = slotById.value.get(id)
  if (!cell) return '未知'
  if (id === 'weapon_2' && weaponShared.value) {
    const main = slotById.value.get('weapon_1')
    return main?.item_label_zh || cell.item_label_zh || cell.slot_label_zh
  }
  return cell.item_label_zh || cell.slot_label_zh
}

function onTogglePuppetPicker(): void {
  if (puppetPickerOpen.value) {
    puppetPickerOpen.value = false
    pendingPuppetUids.value = [...savedPuppetUids.value]
    return
  }
  pendingPuppetUids.value = [...savedPuppetUids.value]
  puppetPickerOpen.value = true
}

function isPuppetPending(uid: string): boolean {
  return pendingPuppetUids.value.includes(uid)
}

function onTogglePuppetSelect(uid: string): void {
  if (writeBlocked.value) return
  if (isPuppetPending(uid)) {
    pendingPuppetUids.value = pendingPuppetUids.value.filter((id) => id !== uid)
    return
  }
  if (pendingPuppetUids.value.length >= puppetLoadoutMax.value) {
    ElMessage.warning(`上阵傀儡最多不得超过${puppetLoadoutMax.value}个`)
    return
  }
  pendingPuppetUids.value = [...pendingPuppetUids.value, uid]
}

function onClickSlot(slot: EquipmentSlot): void {
  selectedSlot.value = selectedSlot.value === slot ? null : slot
}

async function onEquip(itemUid: string): Promise<void> {
  if (writeBlocked.value) return
  if (busy.value || !selectedSlot.value) {
    ElMessage.info('请先点选部位槽')
    return
  }
  busy.value = true
  const slot = selectedSlot.value
  try {
    const err = await equipmentStore.equip(slot, itemUid)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    selectedSlot.value = slot
    flashSlot.value = slot
    window.setTimeout(() => {
      flashSlot.value = null
    }, 400)
    emit('log', '装备已穿戴', 'success')
    ElMessage.success('装备已穿戴')
  } finally {
    busy.value = false
  }
}

async function onUnequip(slot: EquipmentSlot): Promise<void> {
  if (writeBlocked.value) return
  if (busy.value) return
  const wasTwoHand = weaponShared.value && (slot === 'weapon_1' || slot === 'weapon_2')
  busy.value = true
  try {
    const err = await equipmentStore.unequip(slot)
    if (err) {
      ElMessage.error(err)
      return
    }
    emit('log', wasTwoHand ? '已卸下双手武器' : '已卸下装备', 'info')
  } finally {
    busy.value = false
  }
}

async function onConfirmPuppetLoadout(): Promise<void> {
  if (writeBlocked.value) return
  if (busy.value) return
  busy.value = true
  try {
    const err = await equipmentStore.replacePuppets([...pendingPuppetUids.value])
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    puppetPickerOpen.value = false
    emit('log', '傀儡已上阵', 'success')
    ElMessage.success('已保存上阵傀儡')
  } finally {
    busy.value = false
  }
}

const avatarDeploy = computed(() => state.value?.avatar_deploy ?? null)

async function onToggleAvatarDeploy(value: boolean | string | number): Promise<void> {
  if (writeBlocked.value || busy.value) return
  busy.value = true
  try {
    const err = await equipmentStore.setAvatarDeployed(Boolean(value))
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('log', value ? '化身已上阵（占用神识）' : '化身已撤下', 'success')
  } finally {
    busy.value = false
  }
}

const allTalismans = computed((): TalismanLoadoutEntry[] => {
  const loadout = state.value?.talisman_loadout ?? []
  const bag = state.value?.bag_talismans ?? []
  return [...loadout, ...bag]
})

const savedTalismanUids = computed(() =>
  (state.value?.talisman_loadout ?? [])
    .map((row) => row.item_uid)
    .filter((uid): uid is string => Boolean(uid)),
)

const savedTalismanNames = computed(() =>
  (state.value?.talisman_loadout ?? []).map((row) => row.label_zh).join('、'),
)

function onToggleTalismanPicker(): void {
  if (talismanPickerOpen.value) {
    talismanPickerOpen.value = false
    pendingTalismanUids.value = [...savedTalismanUids.value]
    return
  }
  pendingTalismanUids.value = [...savedTalismanUids.value]
  talismanPickerOpen.value = true
}

function isTalismanPending(uid: string): boolean {
  return pendingTalismanUids.value.includes(uid)
}

function onToggleTalismanSelect(uid: string): void {
  if (writeBlocked.value) return
  if (isTalismanPending(uid)) {
    pendingTalismanUids.value = pendingTalismanUids.value.filter((id) => id !== uid)
    return
  }
  pendingTalismanUids.value = [...pendingTalismanUids.value, uid]
}

async function onConfirmTalismanLoadout(): Promise<void> {
  if (writeBlocked.value || busy.value) return
  busy.value = true
  try {
    const err = await equipmentStore.replaceTalismans([...pendingTalismanUids.value])
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    talismanPickerOpen.value = false
    emit('log', '符箓已加入战斗', 'success')
    ElMessage.success('已保存出战符箓')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="equip-panel" v-loading="equipmentStore.loading">
    <template #header>
      <div class="equip-header" @click="open = !open">
        <el-text tag="b" size="small">穿戴栏</el-text>
        <el-text size="small" type="info">
          已穿 {{ equippedCount }}/{{ pointerSlotTotal || 16 }}
        </el-text>
        <el-tag
          v-if="state && !channelEnabled"
          type="info"
          effect="plain"
          size="small"
          @click.stop
        >
          属性通道未启用（穿戴可见，战斗加成未入账）
        </el-tag>
        <el-text size="small" type="info" class="equip-toggle">
          {{ open ? '收起' : '展开' }}
        </el-text>
      </div>
    </template>

    <div v-show="open">
      <el-alert
        v-if="writeBlocked"
        :title="writeBlockReason"
        type="warning"
        show-icon
        :closable="false"
        class="equip-alert"
      />

      <template v-if="state">
        <div class="doll-board" :class="{ 'doll-board-avatar': isAvatarActor }">
          <div
            v-for="(id, idx) in DOLL_LEFT"
            :key="id"
            class="doll-slot-wrap"
            :style="{ gridColumn: 1, gridRow: idx + 1 }"
          >
            <el-tooltip
              effect="dark"
              placement="top"
              :show-after="200"
              popper-class="game-hover-tip item-hover-tip"
            >
              <template #content>
                <ItemHoverTip :model="slotHover(id)" />
              </template>
              <button
                type="button"
                class="doll-slot"
                :class="{
                  'slot-filled': Boolean(slotById.get(id)?.item_uid),
                  'slot-flash': flashSlot === id,
                  'slot-selected': selectedSlot === id,
                }"
                @click="onClickSlot(id)"
              >
                <span class="slot-caption">{{ slotCaption(id) }}</span>
              </button>
            </el-tooltip>
          </div>

          <div class="doll-silhouette" aria-hidden="true">
            <svg viewBox="0 0 80 200" class="silhouette-svg">
              <ellipse cx="40" cy="14" rx="6" ry="5" />
              <ellipse cx="40" cy="32" rx="13" ry="15" />
              <path d="M24 50 L40 58 L56 50 L68 148 L40 172 L12 148 Z" />
              <path d="M24 56 L8 102 L18 106 L30 72" />
              <path d="M56 56 L72 102 L62 106 L50 72" />
            </svg>
          </div>

          <div
            v-for="(id, idx) in DOLL_RIGHT"
            :key="id"
            class="doll-slot-wrap"
            :style="{ gridColumn: 3, gridRow: idx + 1 }"
          >
            <el-tooltip
              effect="dark"
              placement="top"
              :show-after="200"
              popper-class="game-hover-tip item-hover-tip"
            >
              <template #content>
                <ItemHoverTip :model="slotHover(id)" />
              </template>
              <button
                type="button"
                class="doll-slot"
                :class="{
                  'slot-filled': Boolean(slotById.get(id)?.item_uid),
                  'slot-flash': flashSlot === id,
                  'slot-selected': selectedSlot === id,
                }"
                @click="onClickSlot(id)"
              >
                <span class="slot-caption">{{ slotCaption(id) }}</span>
              </button>
            </el-tooltip>
          </div>

          <div class="doll-weapons">
            <el-text v-if="weaponShared" size="small" type="info">双手同装</el-text>
            <div class="weapon-row">
            <el-tooltip
              v-for="id in DOLL_WEAPONS"
              :key="id"
              effect="dark"
              placement="top"
              :show-after="200"
              popper-class="game-hover-tip item-hover-tip"
            >
              <template #content>
                <ItemHoverTip :model="slotHover(id)" />
              </template>
              <button
                type="button"
                class="doll-slot weapon-slot"
                :class="{
                  'slot-filled': Boolean(slotById.get(id)?.item_uid),
                  'slot-flash': flashSlot === id,
                  'slot-selected': selectedSlot === id,
                  'slot-two-hand-off': weaponShared && id === 'weapon_2',
                }"
                @click="onClickSlot(id)"
              >
                <span class="slot-caption">{{ slotCaption(id) }}</span>
              </button>
            </el-tooltip>
            </div>
          </div>
        </div>

        <PoolPickerGrid
          v-if="selectedCell"
          :title="`部位：${selectedCell.slot_label_zh}`"
          empty-text="此部位背包暂无可用装备"
          :items="pickerCandidates"
          :busy="busy || writeBlocked"
          @pick="onPickCandidate"
        />

        <div v-if="!isAvatarActor" class="deploy-board">
          <div class="avatar-row">
            <el-text size="small">化身上阵</el-text>
            <el-switch
              :model-value="Boolean(avatarDeploy?.deployed)"
              :disabled="busy || writeBlocked || !avatarDeploy?.has_avatar"
              size="small"
              @change="onToggleAvatarDeploy"
            />
            <el-text size="small" type="info">
              {{
                avatarDeploy?.has_avatar
                  ? `${avatarDeploy.name || '化身'} · 神识 ${avatarDeploy.cost}`
                  : '尚未凝练化身'
              }}
            </el-text>
          </div>
          <el-text size="small" type="info" class="deploy-help">
            {{ avatarDeploy?.help_zh || '化身、灵宠、傀儡的神识占用都在本栏设置；阵法页只布阵。' }}
          </el-text>
        </div>

        <div v-if="!isAvatarActor" class="puppet-board">
          <div class="puppet-toolbar">
            <div class="puppet-actions">
              <el-button
                size="small"
                :type="puppetPickerOpen ? 'primary' : 'default'"
                :disabled="busy"
                @click="onTogglePuppetPicker"
              >
                上阵傀儡（{{ savedPuppetUids.length }}/{{ puppetLoadoutMax }}）
              </el-button>
              <el-tooltip
                :content="puppetSenseHelp"
                placement="bottom-end"
                effect="dark"
                trigger="hover"
                :show-after="200"
                popper-class="game-hover-tip puppet-sense-tip"
              >
                <button
                  type="button"
                  class="puppet-sense-info"
                  aria-label="查看神识与上阵规则"
                >
                  <el-icon :size="14"><InfoFilled /></el-icon>
                </button>
              </el-tooltip>
            </div>
          </div>
          <el-text v-if="!puppetPickerOpen" size="small" type="info" class="puppet-saved">
            {{ savedPuppetNames || '尚未上阵傀儡' }}
          </el-text>
          <div v-if="puppetPickerOpen" class="slot-picker puppet-picker">
            <div v-if="!allPuppets.length" class="candidate-row empty-row">
              <el-text size="small" type="info">暂无可以上阵的傀儡</el-text>
            </div>
            <div
              v-for="p in allPuppets"
              :key="p.item_uid"
              class="candidate-row"
              :class="{ 'worn-row': isPuppetPending(p.item_uid) }"
            >
              <el-text size="small">{{ p.label_zh }}</el-text>
              <el-text size="small" type="info">
                神识占用 {{ p.divine_sense_cost ?? state?.puppet_sense?.default_cost ?? 0 }}
              </el-text>
              <el-button
                v-if="isPuppetPending(p.item_uid)"
                link
                type="danger"
                size="small"
                :disabled="busy || writeBlocked"
                @click="onTogglePuppetSelect(p.item_uid)"
              >
                取消选择
              </el-button>
              <el-button
                v-else
                size="small"
                :disabled="busy || writeBlocked || pendingPuppetUids.length >= puppetLoadoutMax"
                @click="onTogglePuppetSelect(p.item_uid)"
              >
                选择
              </el-button>
            </div>
            <el-button
              type="primary"
              size="small"
              :disabled="busy || writeBlocked"
              @click="onConfirmPuppetLoadout"
            >
              上阵
            </el-button>
            <div class="puppet-sense-live">
              <el-tag :type="puppetSenseTagType" size="small" effect="plain">
                傀儡能力发挥 {{ livePuppetSense.percent }}%（{{ livePuppetSense.zone_label_zh }}）
              </el-tag>
              <el-text size="small" type="info">
                神识占用 {{ livePuppetSense.load }} / {{ characterSenseCap }}
              </el-text>
            </div>
          </div>
        </div>

        <div v-if="!isAvatarActor" class="puppet-board">
          <div class="puppet-toolbar">
            <div class="puppet-actions">
              <el-button
                size="small"
                :type="talismanPickerOpen ? 'primary' : 'default'"
                :disabled="busy"
                @click="onToggleTalismanPicker"
              >
                上阵符箓（{{ savedTalismanUids.length }}）
              </el-button>
            </div>
          </div>
          <el-text v-if="!talismanPickerOpen" size="small" type="info" class="puppet-saved">
            {{ savedTalismanNames || '尚未上阵符箓' }}
          </el-text>
          <el-text size="small" type="info" class="deploy-help">
            {{ state?.talisman_loadout_note_zh || '加入战斗无件数上限；同种类不叠加，取最高，低效果符仍消耗。' }}
          </el-text>
          <div v-if="talismanPickerOpen" class="slot-picker puppet-picker">
            <div v-if="!allTalismans.length" class="candidate-row empty-row">
              <el-text size="small" type="info">暂无可以上阵的符箓</el-text>
            </div>
            <div
              v-for="row in allTalismans"
              :key="row.item_uid || String(row.inventory_item_id)"
              class="candidate-row"
              :class="{ 'worn-row': row.item_uid ? isTalismanPending(row.item_uid) : false }"
            >
              <el-text size="small">{{ row.label_zh }}</el-text>
              <el-button
                v-if="row.item_uid && isTalismanPending(row.item_uid)"
                link
                type="danger"
                size="small"
                :disabled="busy || writeBlocked"
                @click="onToggleTalismanSelect(row.item_uid)"
              >
                取消选择
              </el-button>
              <el-button
                v-else-if="row.item_uid"
                size="small"
                :disabled="busy || writeBlocked"
                @click="onToggleTalismanSelect(row.item_uid)"
              >
                选择
              </el-button>
            </div>
            <el-button
              type="primary"
              size="small"
              :disabled="busy || writeBlocked"
              @click="onConfirmTalismanLoadout"
            >
              上阵
            </el-button>
          </div>
        </div>
      </template>
    </div>
  </el-card>
</template>

<style scoped>
.equip-panel {
  --equip-slot-size: 52px;
}

.equip-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}

.equip-toggle {
  margin-left: auto;
}

.equip-alert {
  margin-bottom: 0.65rem;
}

.doll-board {
  display: grid;
  grid-template-columns: 52px minmax(64px, 1fr) 52px;
  grid-template-rows: repeat(7, 52px) auto;
  column-gap: 0.5rem;
  row-gap: 0.35rem;
  max-width: 280px;
  margin: 0 auto 0.65rem;
}

.doll-board-avatar {
  grid-template-rows: repeat(6, 52px) auto;
}

.doll-board-avatar .doll-silhouette {
  grid-row: 1 / 7;
}

.doll-silhouette {
  grid-column: 2;
  grid-row: 1 / 8;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
}

.silhouette-svg {
  width: 100%;
  height: 100%;
  max-height: 360px;
  fill: var(--el-text-color-placeholder);
  opacity: 0.45;
}

.doll-weapons {
  grid-column: 1 / -1;
  grid-row: 8;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding-top: 0.15rem;
}

.weapon-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
}

.doll-slot-wrap {
  width: var(--equip-slot-size);
  height: var(--equip-slot-size);
}

.doll-slot-wrap :deep(.el-tooltip__trigger) {
  display: block;
  width: 100%;
  height: 100%;
}

.doll-slot {
  width: var(--equip-slot-size);
  height: var(--equip-slot-size);
  padding: 0.15rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: box-shadow 0.4s ease, border-color 0.2s ease;
}

.doll-slot:hover {
  border-color: var(--el-color-primary-light-5);
}

.slot-filled {
  border-style: solid;
}

.slot-two-hand-off {
  border-color: var(--el-color-danger);
  border-style: solid;
}

.slot-two-hand-off:hover {
  border-color: var(--el-color-danger);
}

.slot-flash,
.slot-selected {
  box-shadow: 0 0 0 2px #c9930f;
}

.slot-caption {
  font-size: 11px;
  line-height: 1.15;
  text-align: center;
  color: var(--el-text-color-regular);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}

.slot-picker {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.65rem;
}

.picker-title {
  display: block;
}

.candidate-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  box-sizing: border-box;
  min-height: calc(var(--equip-slot-size) + 1rem);
  padding: 0.5rem 0.65rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
}

.candidate-row.empty-row {
  justify-content: center;
  align-items: center;
}

.worn-row {
  border-style: solid;
  border-color: #c9930f;
  box-shadow: 0 0 0 1px #c9930f;
}

.deploy-board {
  margin-bottom: 0.65rem;
}

.avatar-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.deploy-help {
  display: block;
  margin-top: 0.25rem;
}

.puppet-board {
  margin-bottom: 0.65rem;
}

.puppet-toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.puppet-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.puppet-saved {
  display: block;
  margin: 0.35rem 0;
}

.puppet-picker {
  margin-top: 0.35rem;
}

.puppet-sense-live {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.puppet-sense-info {
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

.puppet-sense-info:hover {
  color: var(--el-color-primary);
}

@media (max-width: 800px) {
  .equip-panel {
    --equip-slot-size: 48px;
  }

  .doll-board {
    max-width: 240px;
    grid-template-columns: 48px minmax(48px, 1fr) 48px;
    grid-template-rows: repeat(7, 48px) auto;
  }
}
</style>

<!-- tooltip 挂到 body，需非 scoped -->
<style>
.puppet-sense-tip {
  max-width: 18rem !important;
}

.puppet-sense-tip .tip-body {
  color: #f0f2f5;
  font-size: 12px;
}
</style>
