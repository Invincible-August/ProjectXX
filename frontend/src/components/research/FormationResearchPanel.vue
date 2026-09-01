<script setup lang="ts">
/**
 * Formation research designer (M8 R3): materials → paint blueprint → finalize.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import FormationBoard from '../formation/FormationBoard.vue'
import { fetchBoardMetaApi } from '../../api/formation'
import { usePlayWriteGate } from '../../composables/usePlayWriteGate'
import { useResearchStore } from '../../stores/research'
import { useInventoryStore } from '../../stores/inventory'
import type { BoardMeta, FormationTerrainCell } from '../../types/formation'
import type { FormationBlueprintDraft } from '../../types/research'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const router = useRouter()
const researchStore = useResearchStore()
const inventoryStore = useInventoryStore()
const { writeBlocked } = usePlayWriteGate()

const selectedIds = ref<string[]>([])
const qty = ref(1)
const labelZh = ref('')
const busy = ref(false)
const dirty = ref(false)
const boardMeta = ref<BoardMeta | null>(null)
const brush = ref<'obstacle' | 'ravine' | 'erase' | 'mask'>('obstacle')
const deployMode = ref('free_own')
const terrain = ref<FormationTerrainCell[]>([])
const maskCells = ref<[number, number][]>([])

const catalog = computed(() => researchStore.catalog)
const session = computed(() => researchStore.session)
const formCfg = computed(() => catalog.value?.formation)
const ownX = computed(() => new Set(boardMeta.value?.zones.own_x ?? [0, 1, 2]))
const materials = computed(() => formCfg.value?.allowed_materials ?? [])
const anyMaterialHeld = computed(() => materials.value.some((id) => materialQty(id) > 0))

watch(dirty, (v) => {
  researchStore.hasUnsavedFormationDraft = v
})

onUnmounted(() => {
  researchStore.hasUnsavedFormationDraft = false
})

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try {
    await ElMessageBox.confirm('阵法草案未保存，确定离开？', '未保存', {
      confirmButtonText: '放弃修改',
      cancelButtonText: '留下',
    })
    return true
  } catch {
    return false
  }
})

const MODE_LABELS: Record<string, string> = {
  default: '默认区',
  free_own: '己方半区自选',
  mask: '掩码区',
  fixed: '固定格',
}

const obstacleCap = computed(() => {
  const brushCfg = (formCfg.value?.terrain_layout as { brush?: { max_obstacles?: number } } | undefined)
    ?.brush
  return Number(brushCfg?.max_obstacles ?? 3)
})
const ravineCap = computed(() => {
  const brushCfg = (formCfg.value?.terrain_layout as { brush?: { max_ravines?: number } } | undefined)
    ?.brush
  return Number(brushCfg?.max_ravines ?? 1)
})

const obstacleCount = computed(
  () => terrain.value.filter((c) => c.type === 'obstacle').length,
)
const ravineCount = computed(() => terrain.value.filter((c) => c.type === 'ravine').length)

const deployCells = computed<[number, number][]>(() => {
  const meta = boardMeta.value
  if (!meta) return []
  const blocked = new Set(terrain.value.map((c) => `${c.x},${c.y}`))
  if (deployMode.value === 'mask') {
    return maskCells.value.filter(([x, y]) => !blocked.has(`${x},${y}`))
  }
  if (deployMode.value === 'default') {
    return (meta.default_deploy_cells || []).filter(([x, y]) => !blocked.has(`${x},${y}`))
  }
  const cells: [number, number][] = []
  for (const x of meta.zones.own_x) {
    for (let y = 0; y < meta.size; y += 1) {
      if (!blocked.has(`${x},${y}`)) cells.push([x, y])
    }
  }
  return cells
})

function materialQty(itemId: string): number {
  return inventoryStore.items
    .filter((i) => i.item_id === itemId)
    .reduce((sum, i) => sum + Number(i.quantity || 0), 0)
}

function materialLabel(itemId: string): string {
  const row = inventoryStore.items.find((i) => i.item_id === itemId)
  return row?.name || itemId
}

function toggleMaterial(id: string): void {
  if (writeBlocked.value) return
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter((x) => x !== id)
  } else {
    selectedIds.value = [...selectedIds.value, id]
  }
}

function applyBlueprint(bp: FormationBlueprintDraft | null | undefined): void {
  if (!bp) return
  deployMode.value = bp.deploy?.mode || formCfg.value?.default_deploy_mode || 'free_own'
  terrain.value = (bp.terrain || []).map((c) => ({
    x: c.x,
    y: c.y,
    type: c.type,
    subtype: c.subtype || (c.type === 'obstacle' ? 'destructible' : ''),
  }))
  maskCells.value = (bp.deploy?.cells || []).map((c) => [Number(c[0]), Number(c[1])]) as [
    number,
    number,
  ][]
  dirty.value = false
}

function currentBlueprint(): Record<string, unknown> {
  return {
    deploy: {
      mode: deployMode.value,
      cells: deployMode.value === 'mask' ? maskCells.value : [],
      add_cells: [],
      exclude_cells: [],
      allow_neutral: false,
    },
    terrain_layout: formCfg.value?.terrain_layout || { mode: 'brush' },
    terrain: terrain.value.map((c) => ({
      x: c.x,
      y: c.y,
      type: c.type,
      subtype: c.subtype || '',
    })),
    force_shifts: [],
    environment: null,
    weather: null,
    effect: null,
  }
}

watch(
  () => session.value?.blueprint,
  (bp) => {
    if (session.value?.kind === 'formation') applyBlueprint(bp)
  },
)

onMounted(async () => {
  await inventoryStore.load()
  const envelope = await fetchBoardMetaApi()
  if (envelope.code === 0 && envelope.data) {
    boardMeta.value = envelope.data
  }
  if (session.value?.kind === 'formation') {
    applyBlueprint(session.value.blueprint)
  }
})

async function onCreate(): Promise<void> {
  if (writeBlocked.value) return
  if (!formCfg.value) return
  if (!selectedIds.value.length) {
    ElMessage.info('请选择至少一种材料')
    return
  }
  busy.value = true
  try {
    const err = await researchStore.create({
      kind: 'formation',
      materials: selectedIds.value.map((item_id) => ({ item_id, quantity: qty.value })),
      spends: { cultivation_points: formCfg.value.spend.cultivation_points },
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    emit('log', '阵法草案已开启', 'success')
    applyBlueprint(researchStore.session?.blueprint)
    await inventoryStore.load()
  } finally {
    busy.value = false
  }
}

function onCellClick(x: number, y: number): void {
  if (writeBlocked.value) return
  if (!session.value || session.value.kind !== 'formation') return
  if (!ownX.value.has(x)) {
    ElMessage.info('只能在己方半区落笔')
    emit('log', '敌区/中立不可刷地形', 'warning')
    return
  }
  if (brush.value === 'mask') {
    if (deployMode.value !== 'mask') {
      ElMessage.info('涂区仅在掩码模式下可用')
      return
    }
    dirty.value = true
    const key = `${x},${y}`
    const exists = maskCells.value.some(([mx, my]) => `${mx},${my}` === key)
    maskCells.value = exists
      ? maskCells.value.filter(([mx, my]) => `${mx},${my}` !== key)
      : [...maskCells.value, [x, y]]
    return
  }
  dirty.value = true
  if (brush.value === 'erase') {
    terrain.value = terrain.value.filter((c) => !(c.x === x && c.y === y))
    return
  }
  const type = brush.value
  const existing = terrain.value.find((c) => c.x === x && c.y === y)
  if (type === 'obstacle' && obstacleCount.value >= obstacleCap.value && existing?.type !== 'obstacle') {
    ElMessage.warning('障碍已达预算')
    return
  }
  if (type === 'ravine' && ravineCount.value >= ravineCap.value && existing?.type !== 'ravine') {
    ElMessage.warning('沟壑已达预算')
    return
  }
  terrain.value = [
    ...terrain.value.filter((c) => !(c.x === x && c.y === y)),
    { x, y, type, subtype: type === 'obstacle' ? 'destructible' : '' },
  ]
}

async function onSaveDraft(): Promise<void> {
  if (writeBlocked.value) return
  if (!session.value) return
  busy.value = true
  try {
    const err = await researchStore.saveDraft(currentBlueprint())
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    dirty.value = false
    ElMessage.success('草案已保存')
    emit('log', '阵法草案已保存', 'success')
  } finally {
    busy.value = false
  }
}

async function onFinalize(): Promise<void> {
  if (writeBlocked.value) return
  if (!labelZh.value.trim()) {
    ElMessage.info('请先填写中文名称')
    return
  }
  try {
    await ElMessageBox.confirm('定稿后不可再改此稿，只能另开新研。', '确认定稿', {
      type: 'warning',
      confirmButtonText: '定稿',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  busy.value = true
  try {
    const saveErr = await researchStore.saveDraft(currentBlueprint())
    if (saveErr) {
      ElMessage.error(saveErr)
      return
    }
    const err = await researchStore.finalize(labelZh.value.trim())
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success('阵法定稿成功')
    emit('log', '自研阵已可出战', 'success')
    labelZh.value = ''
    dirty.value = false
    researchStore.clearSession()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b" size="small">阵法设计器</el-text>
    </template>
    <el-text size="small" type="info">{{ formCfg?.help_zh }}</el-text>
    <el-alert
      class="hint"
      type="info"
      :closable="false"
      title="定稿后地形冻结，出战页只摆棋子"
    />

    <template v-if="!session || session.kind !== 'formation'">
      <el-text size="small" type="info">材料（当前持有）</el-text>
      <div class="bag">
        <el-check-tag
          v-for="id in materials"
          :key="id"
          :checked="selectedIds.includes(id)"
          :disabled="writeBlocked"
          @change="toggleMaterial(id)"
        >
          {{ materialLabel(id) }} ×{{ materialQty(id) }}
        </el-check-tag>
        <el-text v-if="!materials.length" size="small" type="info">暂无可用材料配置</el-text>
        <el-text v-else-if="!anyMaterialHeld" size="small" type="warning">
          背包暂无自研材料，可去工坊炼制或由运营后台发放
        </el-text>
      </div>
      <div class="row">
        <el-input-number v-model="qty" :min="1" :max="99" size="small" :disabled="writeBlocked" />
        <el-button
          type="primary"
          size="small"
          :disabled="busy || writeBlocked"
          @click="onCreate"
        >
          开启草案
        </el-button>
      </div>
    </template>

    <template v-else>
      <div class="designer">
        <div class="tools">
          <el-select
            v-model="deployMode"
            size="small"
            :disabled="writeBlocked"
            @change="dirty = true"
          >
            <el-option
              v-for="mode in formCfg?.allowed_deploy_modes ?? ['free_own']"
              :key="mode"
              :value="mode"
              :label="MODE_LABELS[mode] || mode"
            />
          </el-select>
          <el-text size="small" type="info">当前：{{ MODE_LABELS[deployMode] || deployMode }}</el-text>
          <el-tag size="small" :type="obstacleCount >= obstacleCap ? 'warning' : 'info'">
            障碍 {{ obstacleCount }}/{{ obstacleCap }}
          </el-tag>
          <el-tag size="small" :type="ravineCount >= ravineCap ? 'warning' : 'info'">
            沟壑 {{ ravineCount }}/{{ ravineCap }}
          </el-tag>
          <el-button-group>
            <el-button
              size="small"
              :type="brush === 'obstacle' ? 'primary' : 'default'"
              :disabled="writeBlocked"
              @click="brush = 'obstacle'"
            >
              障碍
            </el-button>
            <el-button
              size="small"
              :type="brush === 'ravine' ? 'primary' : 'default'"
              :disabled="writeBlocked"
              @click="brush = 'ravine'"
            >
              沟壑
            </el-button>
            <el-button
              size="small"
              :type="brush === 'erase' ? 'primary' : 'default'"
              :disabled="writeBlocked"
              @click="brush = 'erase'"
            >
              擦除
            </el-button>
            <el-button
              v-if="deployMode === 'mask'"
              size="small"
              :type="brush === 'mask' ? 'primary' : 'default'"
              :disabled="writeBlocked"
              @click="brush = 'mask'"
            >
              涂区
            </el-button>
          </el-button-group>
          <el-input
            v-model="labelZh"
            size="small"
            maxlength="16"
            placeholder="定稿中文名"
            :disabled="writeBlocked"
          />
          <el-button size="small" :disabled="busy || writeBlocked" @click="onSaveDraft">
            保存草案
          </el-button>
          <el-button type="primary" size="small" :disabled="busy || writeBlocked" @click="onFinalize">
            定稿
          </el-button>
          <el-button size="small" @click="router.push('/formation')">去阵法</el-button>
        </div>
        <FormationBoard
          v-if="boardMeta"
          :meta="boardMeta"
          :units="[]"
          :terrain="terrain"
          :selected-uid="null"
          :deploy-cells="deployCells"
          @cell-click="onCellClick"
        />
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.hint {
  margin: 0.5rem 0;
}
.bag,
.row,
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  margin: 0.5rem 0;
}
.designer {
  display: grid;
  grid-template-columns: minmax(200px, 260px) 1fr;
  gap: 0.75rem;
}
.tools {
  flex-direction: column;
  align-items: stretch;
}
@media (max-width: 800px) {
  .designer {
    grid-template-columns: 1fr;
  }
}
</style>
