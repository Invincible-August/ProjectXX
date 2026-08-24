<script setup lang="ts">
/**
 * 未凝练：四个资源槽（灵力 / 灵石 / 化身功法 / 媒介）+ 凝练按钮。
 * 点槽从列表填入，与角色页装备栏交互一致。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PoolPickerGrid from '../character/PoolPickerGrid.vue'
import type { PoolCandidate } from '../../types/itemHover'
import { shortItemName } from '../../utils/itemHoverFormat'
import { useAvatarStore } from '../../stores/avatar'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

type SlotKey = 'cultivation' | 'stones' | 'technique' | 'medium'

const avatarStore = useAvatarStore()
const busy = ref(false)
const selectedSlot = ref<SlotKey | null>(null)
const cultivationFilled = ref(false)
const stonesFilled = ref(false)
const techniqueId = ref('')
const mediumItemId = ref('')

const gate = computed(() => avatarStore.features?.condense ?? null)

const cultivationCost = computed(() => gate.value?.cultivation_cost ?? 0)
const stoneCost = computed(() => gate.value?.spirit_stone_cost ?? 0)
const mediumQty = computed(() => gate.value?.medium_quantity ?? 1)

const techniqueName = computed(() => {
  const id = techniqueId.value
  return gate.value?.technique_candidates?.find((row) => row.id === id)?.name || ''
})
const mediumName = computed(() => {
  const id = mediumItemId.value
  return gate.value?.medium_candidates?.find((row) => row.item_id === id)?.name || ''
})

const realmOk = computed(() => Boolean(gate.value?.realm_ok) && !gate.value?.has_avatar)

const allFilled = computed(
  () =>
    cultivationFilled.value &&
    stonesFilled.value &&
    Boolean(techniqueId.value) &&
    Boolean(mediumItemId.value),
)

const condenseHint = computed(() => {
  if (!gate.value) return '正在同步凝练条件…'
  if (gate.value.has_avatar) return '已凝练化身'
  if (!gate.value.realm_ok) return gate.value.block_message || '未达凝练境界'
  if (!allFilled.value) return '请将灵力、灵石、化身功法、媒介填入槽位'
  return gate.value.block_message || '材料已填入，可凝练化身'
})

onMounted(async () => {
  if (!avatarStore.features?.condense) {
    await avatarStore.loadFeatures()
  }
})

function isSelected(slot: SlotKey): boolean {
  return selectedSlot.value === slot
}

function onClickSlot(slot: SlotKey): void {
  selectedSlot.value = selectedSlot.value === slot ? null : slot
}

const pickerTitle = computed(() => {
  switch (selectedSlot.value) {
    case 'cultivation':
      return '选择灵力'
    case 'stones':
      return '选择灵石'
    case 'technique':
      return '选择化身功法'
    case 'medium':
      return '选择媒介'
    default:
      return ''
  }
})

const pickerEmpty = computed(() => {
  switch (selectedSlot.value) {
    case 'cultivation':
      return '修为池不足'
    case 'stones':
      return '灵石不足'
    case 'technique':
      return '没有可用的化身功法'
    case 'medium':
      return '背包中没有可用媒介'
    default:
      return '请先点选槽位'
  }
})

const pickerItems = computed((): PoolCandidate[] => {
  const gateVal = gate.value
  const slot = selectedSlot.value
  if (!gateVal || !slot) return []
  if (slot === 'cultivation') {
    const have = gateVal.current_cultivation ?? 0
    const need = cultivationCost.value
    if (have < need) return []
    return [
      {
        key: 'cultivation',
        shortName: '灵力',
        worn: cultivationFilled.value,
        hover: {
          name: '灵力',
          subtitle: `${have} / 需 ${need}`,
          helpZh: '从本体修为池填入，凝练时扣除。',
        },
      },
    ]
  }
  if (slot === 'stones') {
    const have = gateVal.current_spirit_stones ?? 0
    const need = stoneCost.value
    if (have < need) return []
    return [
      {
        key: 'stones',
        shortName: '灵石',
        worn: stonesFilled.value,
        hover: {
          name: '灵石',
          subtitle: `${have} / 需 ${need}`,
          helpZh: '从本体灵石池填入，凝练时扣除。',
        },
      },
    ]
  }
  if (slot === 'technique') {
    return (gateVal.technique_candidates ?? []).map((row) => ({
      key: row.id,
      shortName: shortItemName(row.name),
      worn: techniqueId.value === row.id,
      hover: {
        name: row.name,
        subtitle: `Lv.${row.level}/${row.max_level}`,
        helpZh: '已学功法作为凝练触媒，不会被消耗。',
      },
    }))
  }
  return (gateVal.medium_candidates ?? [])
    .filter((row) => row.quantity >= mediumQty.value)
    .map((row) => ({
      key: row.item_id,
      shortName: shortItemName(row.name),
      worn: mediumItemId.value === row.item_id,
      hover: {
        name: row.name,
        subtitle: `持有 ${row.quantity} · 需 ${mediumQty.value}`,
        helpZh: '凝练媒介，成功后从背包扣除。',
      },
    }))
})

function onPick(item: PoolCandidate): void {
  const slot = selectedSlot.value
  if (!slot) return
  if (slot === 'cultivation') {
    cultivationFilled.value = !item.worn
  } else if (slot === 'stones') {
    stonesFilled.value = !item.worn
  } else if (slot === 'technique') {
    techniqueId.value = item.worn ? '' : item.key
  } else if (slot === 'medium') {
    mediumItemId.value = item.worn ? '' : item.key
  }
  selectedSlot.value = null
}

async function onCondense(): Promise<void> {
  if (busy.value || !allFilled.value || !realmOk.value) return
  busy.value = true
  try {
    const error = await avatarStore.condense({
      technique_id: techniqueId.value,
      medium_item_id: mediumItemId.value,
    })
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      await avatarStore.loadFeatures()
      return
    }
    ElMessage.success('化身凝练完成')
    emit('log', '化身凝练完成', 'success')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="condense-card">
    <div class="recipe-board">
      <div class="recipe-slots">
        <button
          type="button"
          class="recipe-cell"
          :class="{
            'slot-filled': cultivationFilled,
            'slot-selected': isSelected('cultivation'),
          }"
          @click="onClickSlot('cultivation')"
        >
          <span class="cell-label">灵力</span>
          <span class="cell-caption">
            {{ cultivationFilled ? String(cultivationCost) : '空' }}
          </span>
        </button>
        <button
          type="button"
          class="recipe-cell"
          :class="{
            'slot-filled': stonesFilled,
            'slot-selected': isSelected('stones'),
          }"
          @click="onClickSlot('stones')"
        >
          <span class="cell-label">灵石</span>
          <span class="cell-caption">
            {{ stonesFilled ? String(stoneCost) : '空' }}
          </span>
        </button>
        <button
          type="button"
          class="recipe-cell"
          :class="{
            'slot-filled': Boolean(techniqueId),
            'slot-selected': isSelected('technique'),
          }"
          @click="onClickSlot('technique')"
        >
          <span class="cell-label">化身功法</span>
          <span class="cell-caption">
            {{ techniqueId ? shortItemName(techniqueName) : '空' }}
          </span>
        </button>
        <button
          type="button"
          class="recipe-cell"
          :class="{
            'slot-filled': Boolean(mediumItemId),
            'slot-selected': isSelected('medium'),
          }"
          @click="onClickSlot('medium')"
        >
          <span class="cell-label">媒介</span>
          <span class="cell-caption">
            {{ mediumItemId ? shortItemName(mediumName) : '空' }}
          </span>
        </button>
      </div>

      <PoolPickerGrid
        v-if="selectedSlot"
        :title="pickerTitle"
        :empty-text="pickerEmpty"
        :items="pickerItems"
        :busy="busy"
        @pick="onPick"
      />
    </div>

    <el-text type="info" size="small" class="hint">{{ condenseHint }}</el-text>

    <el-button
      type="primary"
      :loading="busy"
      :disabled="!allFilled || !realmOk"
      @click="onCondense"
    >
      凝练化身
    </el-button>
  </el-card>
</template>

<style scoped>
.recipe-board {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
  margin-bottom: 0.85rem;
}

.recipe-slots {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.55rem;
}

.recipe-cell {
  width: 72px;
  min-height: 72px;
  padding: 0.35rem 0.2rem;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.2rem;
}

.slot-filled {
  border-style: solid;
}

.slot-selected {
  box-shadow: 0 0 0 2px #c9930f;
}

.cell-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.cell-caption {
  font-size: 12px;
  line-height: 1.15;
  text-align: center;
  color: var(--el-text-color-regular);
}

.hint {
  display: block;
  margin-bottom: 0.75rem;
}
</style>
