<script setup lang="ts">
/**
 * Maple-style craft list: select a recipe, show materials, craft at the bottom.
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CraftDaoUsageLine from './CraftDaoUsageLine.vue'
import ItemHoverTip from '../character/ItemHoverTip.vue'
import { useCraftStore } from '../../stores/craft'
import { useInventoryStore } from '../../stores/inventory'
import { useActivityGate } from '../../composables/useActivityGate'
import { useCharacterStore } from '../../stores/character'
import type { CraftBranch, CraftRecipe } from '../../types/craft'
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

const filtered = computed(() =>
  craftStore.recipes.filter((r: CraftRecipe) => r.branch === props.branch),
)

const selected = computed(
  () => filtered.value.find((r) => r.recipe_id === selectedId.value) ?? null,
)

watch(
  filtered,
  (rows) => {
    if (rows.some((r) => r.recipe_id === selectedId.value)) return
    selectedId.value = rows[0]?.recipe_id ?? null
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

function selectRecipe(recipe: CraftRecipe): void {
  selectedId.value = recipe.recipe_id
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
    const error = await craftStore.start(recipe.recipe_id)
    if (error) {
      ElMessage.error(error)
      emit('log', error, 'warning')
      return
    }
    ElMessage.success(`已开工：${recipe.name}`)
    emit('log', `工坊开工：${recipe.name}（${craftStore.actor}）`, 'success')
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

    <div v-if="filtered.length === 0" class="empty">
      <el-text type="info" size="small">该分支暂无配方</el-text>
    </div>

    <div v-else class="recipe-scroll">
      <el-tooltip
        v-for="recipe in filtered"
        :key="recipe.recipe_id"
        effect="dark"
        placement="right"
        :show-after="200"
        popper-class="game-hover-tip item-hover-tip craft-inspect-tip"
      >
        <template #content>
          <ItemHoverTip :model="hoverFromRecipe(recipe)" />
        </template>
        <button
          type="button"
          class="recipe-item"
          :class="{ 'is-locked': recipe.locked, 'is-selected': recipe.recipe_id === selectedId }"
          @click="selectRecipe(recipe)"
        >
          <el-text tag="b" size="small">{{ recipe.name }}</el-text>
        </button>
      </el-tooltip>
    </div>

    <div v-if="selected" class="recipe-detail">
      <el-text size="small" class="detail-title">所需材料</el-text>
      <div v-if="selected.materials.length === 0" class="mat-empty">
        <el-text type="info" size="small">无需材料</el-text>
      </div>
      <div
        v-for="mat in selected.materials"
        :key="mat.item_id"
        class="mat-row"
        :class="{ 'is-short': heldQty(mat.item_id) < mat.quantity }"
      >
        <span>{{ mat.label_zh || mat.item_id }}</span>
        <span>需 {{ mat.quantity }} / 持有 {{ heldQty(mat.item_id) }}</span>
      </div>
      <div class="mat-row" :class="{ 'is-short': stonesHave < selected.spirit_stone_cost }">
        <span>灵石</span>
        <span>需 {{ selected.spirit_stone_cost }} / 持有 {{ stonesHave }}</span>
      </div>

      <el-text size="small" class="detail-title stamina-title">所需体力</el-text>
      <div class="mat-row" :class="{ 'is-short': staminaHave < selected.stamina_cost }">
        <span>体力</span>
        <span>需 {{ selected.stamina_cost }} / 持有 {{ staminaHave }}</span>
      </div>
      <el-text v-if="selected.locked" type="warning" size="small" class="lock-line">
        {{ selected.lock_reason || '未解锁' }}
      </el-text>
    </div>

    <div class="recipe-footer">
      <el-button
        size="small"
        type="primary"
        :loading="busy"
        :disabled="!selected || selected.locked"
        @click="onStart"
      >
        开工
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
.recipe-scroll {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: 16rem;
  overflow-y: auto;
}

.recipe-scroll :deep(.el-tooltip__trigger) {
  display: block;
  width: 100%;
}

.recipe-item {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 0.45rem 0.65rem;
  background: transparent;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.recipe-item:hover {
  border-color: var(--el-color-primary-light-5);
}

.recipe-item.is-selected {
  border-color: #c9a227;
  background: rgba(201, 162, 39, 0.1);
}

.recipe-item.is-locked {
  opacity: 0.55;
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

.empty {
  padding: 0.5rem 0;
}
</style>
