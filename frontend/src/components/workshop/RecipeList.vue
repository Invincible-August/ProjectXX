<script setup lang="ts">
/**
 * Workshop recipe card: filter form + table, then materials and start.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { TableInstance } from 'element-plus'
import CraftDaoUsageLine from './CraftDaoUsageLine.vue'
import ItemHoverTip from '../character/ItemHoverTip.vue'
import { CRAFT_ELEMENT_FILTERS, CRAFT_EQUIP_SLOT_FILTERS, CRAFT_TALISMAN_KIND_FILTERS } from '../../constants/craft'
import { useCraftStore } from '../../stores/craft'
import { useInventoryStore } from '../../stores/inventory'
import { useActivityGate } from '../../composables/useActivityGate'
import { useCharacterStore } from '../../stores/character'
import type { CraftBranch, CraftRecipe } from '../../types/craft'
import { recipeElementId, recipeEquipSlotGroup, recipeRequiredLevel, recipeTalismanKind } from '../../types/craft'
import { alertIfIdleBlocked } from '../../utils/idleBlockDialog'
import { hoverFromRecipe } from '../../utils/itemHoverFormat'

const props = defineProps<{
  branch: CraftBranch | string
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  started: []
}>()

const craftStore = useCraftStore()
const inventoryStore = useInventoryStore()
const characterStore = useCharacterStore()
const { canStartCraft, blockReason } = useActivityGate()
const busy = ref(false)
const selectedId = ref<string | null>(null)
/** 一次制造件数 */
const craftQty = ref(1)
/** Empty string = no element filter */
const elementFilter = ref('')
/** null = no level filter */
const levelFilter = ref<number | null>(null)
/** Empty string = no smithing slot-group filter */
const slotFilter = ref('')
/** Empty string = no talisman function filter */
const functionFilter = ref('')
const tableRef = ref<TableInstance>()

const showSlotFilter = computed(() => props.branch === 'smithing')
const showFunctionFilter = computed(() => props.branch === 'talisman')

const branchRecipes = computed(() =>
  craftStore.recipes.filter((r: CraftRecipe) => r.branch === props.branch),
)

const levelOptions = computed(() => {
  const levels = new Set<number>()
  for (const recipe of branchRecipes.value) {
    levels.add(recipeRequiredLevel(recipe))
  }
  return [...levels].sort((a, b) => a - b)
})

const filtered = computed(() =>
  branchRecipes.value.filter((recipe) => {
    if (elementFilter.value && recipeElementId(recipe) !== elementFilter.value) {
      return false
    }
    if (levelFilter.value != null && recipeRequiredLevel(recipe) !== levelFilter.value) {
      return false
    }
    if (showSlotFilter.value && slotFilter.value && recipeEquipSlotGroup(recipe) !== slotFilter.value) {
      return false
    }
    if (
      showFunctionFilter.value &&
      functionFilter.value &&
      recipeTalismanKind(recipe) !== functionFilter.value
    ) {
      return false
    }
    return true
  }),
)

const selected = computed(
  () => filtered.value.find((r) => r.recipe_id === selectedId.value) ?? null,
)

const emptyHint = computed(() => {
  if (branchRecipes.value.length === 0) return '该分支暂无配方'
  return '无符合筛选的配方'
})

watch(
  () => props.branch,
  () => {
    elementFilter.value = ''
    levelFilter.value = null
    slotFilter.value = ''
    functionFilter.value = ''
  },
)

watch(
  filtered,
  async (rows) => {
    if (!rows.some((r) => r.recipe_id === selectedId.value)) {
      selectedId.value = rows[0]?.recipe_id ?? null
    }
    await nextTick()
    const row = rows.find((r) => r.recipe_id === selectedId.value)
    tableRef.value?.setCurrentRow(row ?? undefined)
  },
  { immediate: true },
)

function heldQty(itemId: string): number {
  return inventoryStore.items
    .filter((row) => row.item_id === itemId)
    .reduce((sum, row) => sum + Number(row.quantity || 0), 0)
}

const staminaHave = computed(() => Number(characterStore.character?.battle_stamina?.left ?? 0))
const stonesHave = computed(() => Number(characterStore.character?.spirit_stones ?? 0))

const qty = computed(() => Math.min(99, Math.max(1, Math.floor(Number(craftQty.value) || 1))))

const needStones = computed(() => (selected.value?.spirit_stone_cost ?? 0) * qty.value)
const needStamina = computed(() => (selected.value?.stamina_cost ?? 0) * qty.value)
const needDuration = computed(() => (selected.value?.duration_seconds ?? 0) * qty.value)

function matNeed(base: number): number {
  return base * qty.value
}

function onRowClick(recipe: CraftRecipe): void {
  selectedId.value = recipe.recipe_id
}

function rowClassName({ row }: { row: CraftRecipe }): string {
  return row.locked ? 'is-locked' : ''
}

async function onStart(): Promise<void> {
  const recipe = selected.value
  if (busy.value || !recipe || recipe.locked) return
  const action =
    {
      alchemy: '炼丹',
      smithing: '炼器',
      talisman: '制符',
      puppet: '造傀儡',
    }[recipe.branch] || '工坊开工'
  if (await alertIfIdleBlocked(characterStore.character, action, 'either')) {
    emit('log', `修炼中无法${action}，请先停止修炼`, 'warning')
    return
  }
  if (!canStartCraft.value) {
    const msg = blockReason('start_craft') || '当前不可开工'
    ElMessage.warning(msg)
    emit('log', msg, 'warning')
    return
  }
  busy.value = true
  try {
    const error = await craftStore.start(recipe.recipe_id, undefined, qty.value)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    const qtyLabel = qty.value > 1 ? ` ×${qty.value}` : ''
    ElMessage.success(`已入队：${recipe.name}${qtyLabel}`)
    emit('log', `工坊入队：${recipe.name}${qtyLabel}（${craftStore.actor}）`, 'success')
    emit('started')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="recipe-list">
    <template #header>
      <el-text tag="b">配方</el-text>
    </template>

    <el-form class="recipe-filter" :inline="true" size="small" @submit.prevent>
      <el-form-item label="属性">
        <el-select
          v-model="elementFilter"
          clearable
          placeholder="全部"
          class="filter-select"
        >
          <el-option
            v-for="el in CRAFT_ELEMENT_FILTERS"
            :key="el.id"
            :label="el.label_zh"
            :value="el.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="等级">
        <el-select
          v-model="levelFilter"
          clearable
          placeholder="全部"
          class="filter-select"
        >
          <el-option
            v-for="lv in levelOptions"
            :key="lv"
            :label="String(lv)"
            :value="lv"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="showSlotFilter" label="部位">
        <el-select
          v-model="slotFilter"
          clearable
          placeholder="全部"
          class="filter-select"
        >
          <el-option
            v-for="slot in CRAFT_EQUIP_SLOT_FILTERS"
            :key="slot.id"
            :label="slot.label_zh"
            :value="slot.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="showFunctionFilter" label="功能">
        <el-select
          v-model="functionFilter"
          clearable
          placeholder="全部"
          class="filter-select"
        >
          <el-option
            v-for="kind in CRAFT_TALISMAN_KIND_FILTERS"
            :key="kind.id"
            :label="kind.label_zh"
            :value="kind.id"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <el-table
      v-if="filtered.length > 0"
      ref="tableRef"
      :data="filtered"
      size="small"
      highlight-current-row
      row-key="recipe_id"
      max-height="260"
      class="recipe-table"
      :row-class-name="rowClassName"
      empty-text="无符合筛选的配方"
      @row-click="onRowClick"
    >
      <el-table-column label="名称" min-width="108">
        <template #default="{ row }">
          <el-tooltip
            effect="dark"
            placement="right"
            :show-after="200"
            popper-class="game-hover-tip item-hover-tip craft-inspect-tip"
          >
            <template #content>
              <ItemHoverTip :model="hoverFromRecipe(row)" />
            </template>
            <el-text tag="b" size="small">{{ row.name }}</el-text>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="属性" width="64">
        <template #default="{ row }">
          <span
            v-if="row.inspect?.element"
            class="element-chip"
            :style="{ borderColor: row.inspect.element.border || '#909399' }"
          >
            {{ row.inspect.element.label_zh }}
          </span>
          <el-text v-else type="info" size="small">—</el-text>
        </template>
      </el-table-column>
      <el-table-column v-if="showSlotFilter" label="部位" width="72">
        <template #default="{ row }">
          <el-text size="small">{{ row.equip_slot_group_zh || '—' }}</el-text>
        </template>
      </el-table-column>
      <el-table-column v-if="showFunctionFilter" label="功能" width="72">
        <template #default="{ row }">
          <el-text size="small">{{ row.talisman_kind_zh || '—' }}</el-text>
        </template>
      </el-table-column>
      <el-table-column label="等级" width="58">
        <template #default="{ row }">
          {{ recipeRequiredLevel(row) }}
        </template>
      </el-table-column>
    </el-table>
    <div v-else class="empty">
      <el-text type="info" size="small">{{ emptyHint }}</el-text>
    </div>

    <div v-if="selected" class="recipe-detail">
      <el-text size="small" class="detail-title">所需材料（×{{ qty }}）</el-text>
      <div v-if="selected.materials.length === 0" class="mat-empty">
        <el-text type="info" size="small">无需材料</el-text>
      </div>
      <div
        v-for="mat in selected.materials"
        :key="mat.item_id"
        class="mat-row"
        :class="{ 'is-short': heldQty(mat.item_id) < matNeed(mat.quantity) }"
      >
        <span>{{ mat.label_zh || mat.item_id }}</span>
        <span>需 {{ matNeed(mat.quantity) }} / 持有 {{ heldQty(mat.item_id) }}</span>
      </div>
      <div class="mat-row" :class="{ 'is-short': stonesHave < needStones }">
        <span>灵石</span>
        <span>需 {{ needStones }} / 持有 {{ stonesHave }}</span>
      </div>

      <el-text size="small" class="detail-title stamina-title">所需体力</el-text>
      <div class="mat-row" :class="{ 'is-short': staminaHave < needStamina }">
        <span>体力</span>
        <span>需 {{ needStamina }} / 持有 {{ staminaHave }}</span>
      </div>
      <el-text size="small" type="info" class="lock-line">
        预计耗时 {{ needDuration }} 秒（单次 {{ selected.duration_seconds }}s × {{ qty }}）
      </el-text>
      <el-text v-if="selected.locked" type="warning" size="small" class="lock-line">
        {{ selected.lock_reason || '未解锁' }}
      </el-text>
    </div>

    <div class="recipe-footer">
      <el-input-number
        v-model="craftQty"
        :min="1"
        :max="99"
        size="small"
        controls-position="right"
        class="qty-input"
      />
      <el-button
        size="small"
        type="primary"
        :loading="busy"
        :disabled="!selected || selected.locked"
        @click="onStart"
      >
        入队
      </el-button>
      <CraftDaoUsageLine
        :model-value="craftStore.useDao"
        :load-preview="true"
        @update:model-value="craftStore.useDao = $event"
      />
    </div>
  </el-card>
</template>

<style scoped>
.recipe-filter {
  margin-bottom: 0.35rem;
}

.recipe-filter :deep(.el-form-item) {
  margin-bottom: 0.35rem;
  margin-right: 0.75rem;
}

.filter-select {
  width: 6.5rem;
}

.recipe-table {
  width: 100%;
}

.recipe-table :deep(.el-table__body tr.current-row > td.el-table__cell) {
  background: rgba(201, 162, 39, 0.12);
}

.recipe-table :deep(.el-table__body tr) {
  cursor: pointer;
}

.recipe-table :deep(tr.is-locked) {
  opacity: 0.55;
}

.element-chip {
  display: inline-block;
  min-width: 1.4rem;
  padding: 0 0.3rem;
  border: 1px solid;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.5;
  text-align: center;
}

.recipe-detail {
  margin-top: 0.75rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--el-border-color-lighter);
}

.detail-title {
  display: block;
  margin-bottom: 0.35rem;
  color: var(--el-text-color-secondary);
}

.stamina-title {
  margin-top: 0.65rem;
  padding-top: 0.45rem;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.mat-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 13px;
  line-height: 1.7;
}

.mat-row.is-short {
  color: var(--el-color-danger);
}

.mat-empty {
  margin-bottom: 0.2rem;
}

.lock-line {
  display: block;
  margin-top: 0.35rem;
}

.recipe-footer {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--el-border-color-lighter);
}

.qty-input {
  width: 7rem;
  flex-shrink: 0;
}

.empty {
  padding: 0.5rem 0;
}
</style>
