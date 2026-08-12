<script setup lang="ts">
/**
 * 工坊配方列表：五分支 Tab + 开工。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useCraftStore } from '../../stores/craft'
import { useActivityGate } from '../../composables/useActivityGate'
import type { CraftBranch, CraftRecipe } from '../../types/craft'

const props = defineProps<{
  initialBranch?: string
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
  started: []
}>()

const craftStore = useCraftStore()
const { canStartCraft, blockReason } = useActivityGate()
const busy = ref(false)
const activeBranch = ref<string>(props.initialBranch || 'alchemy')

const branchTabs: { key: CraftBranch | string; label: string }[] = [
  { key: 'alchemy', label: '炼丹' },
  { key: 'smithing', label: '炼器' },
  { key: 'talisman', label: '符箓' },
  { key: 'array', label: '阵法' },
  { key: 'puppet', label: '傀儡' },
]

watch(
  () => props.initialBranch,
  (b) => {
    if (b) activeBranch.value = b
  },
)

const filtered = computed(() =>
  craftStore.recipes.filter((r: CraftRecipe) => r.branch === activeBranch.value),
)

/** 修炼中不可开工提示 */
const craftBlockHint = computed(() => blockReason('start_craft'))

async function onStart(recipe: CraftRecipe): Promise<void> {
  if (busy.value || recipe.locked) return
  if (!canStartCraft.value) {
    const msg = craftBlockHint.value || '当前不可开工，请先停止修炼'
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
      <el-text tag="b">配方队列</el-text>
    </template>

    <el-alert
      v-if="craftBlockHint"
      :title="craftBlockHint"
      type="warning"
      :closable="false"
      show-icon
      class="eff-hint"
    />

    <el-text type="warning" size="small" class="note">
      此处为配方队列；大厅 Idle「制造业」仅涨经验池。修炼与工坊互斥：须先停止修炼才能开工，工坊进行中不可再修炼。
      环境锁定：点「开工」瞬间锁定时辰/天气写入任务（不是进工坊页那一刻）；任务进行中世界天气再滚也不改本单效率。
    </el-text>

    <el-tabs v-model="activeBranch" size="small">
      <el-tab-pane
        v-for="tab in branchTabs"
        :key="tab.key"
        :name="tab.key"
        :label="tab.label"
      />
    </el-tabs>

    <div v-if="filtered.length === 0" class="empty">
      <el-text type="info" size="small">该分支暂无配方</el-text>
    </div>

    <div v-for="recipe in filtered" :key="recipe.recipe_id" class="recipe-item">
      <div class="recipe-head">
        <el-text tag="b" size="small">{{ recipe.name }}</el-text>
        <el-tag v-if="recipe.locked" size="small" type="info">
          {{ recipe.lock_reason || '未解锁' }}
        </el-tag>
      </div>
      <el-text size="small" type="info">
        {{ recipe.duration_seconds }}s · 灵石 {{ recipe.spirit_stone_cost }} · 体力
        {{ recipe.stamina_cost }}
        <template v-if="recipe.fail_chance > 0">
          · 失败率 {{ Math.round(recipe.fail_chance * 100) }}%
        </template>
      </el-text>
      <el-text v-if="recipe.materials.length" size="small" type="info" class="mats">
        材料：
        <span v-for="(m, i) in recipe.materials" :key="m.item_id">
          {{ m.item_id }}×{{ m.quantity }}<template v-if="i < recipe.materials.length - 1">、</template>
        </span>
      </el-text>
      <el-button
        size="small"
        type="primary"
        :loading="busy"
        :disabled="recipe.locked || !canStartCraft"
        @click="onStart(recipe)"
      >
        开工（{{ craftStore.actor === 'main' ? '本体' : '化身' }}）
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.eff-hint,
.note {
  margin-bottom: 0.5rem;
}

.note {
  display: block;
}

.recipe-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 0.5rem 0.65rem;
  margin-bottom: 0.5rem;
  transition: border-color 0.15s ease;
}

.recipe-item:hover {
  border-color: var(--el-color-primary-light-5);
}

.recipe-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.mats {
  display: block;
  margin: 0.25rem 0;
}

.empty {
  padding: 0.5rem 0;
}
</style>
