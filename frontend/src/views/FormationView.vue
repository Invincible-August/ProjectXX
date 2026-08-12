<script setup lang="ts">
/**
 * 布阵页（M3 · /formation）：7×7 编辑器 + 预设三槽 + 阵法 + 快照更新。
 *
 * 交互约定（前端设计 §6.1）：
 * - 点 Bench 棋子选中 → 点绿色合法格落子；点己方棋子选中 → 点空合法格移动；
 * - 非法格 toast 提示；保存由服务端权威校验（40041/42/43/44）；
 * - isDirty 时切槽 / 离开页需确认；保存成功明示「未自动更新防守快照」。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import FormationBoard from '../components/formation/FormationBoard.vue'
import FormationPicker from '../components/formation/FormationPicker.vue'
import FormationPresetBar from '../components/formation/FormationPresetBar.vue'
import SnapshotUpdateBar from '../components/formation/SnapshotUpdateBar.vue'
import UnitBench from '../components/formation/UnitBench.vue'
import { useFormationStore } from '../stores/formation'
import { useCharacterStore } from '../stores/character'
import type { BenchUnit } from '../types/formation'

const route = useRoute()
const router = useRouter()
const formationStore = useFormationStore()
const characterStore = useCharacterStore()

/**
 * 仅擂台整备入口（?from=dao-arena）显示「回擂台」；日常布阵不显示。
 */
const fromDaoArena = computed(() => route.query.from === 'dao-arena')

/** M5：渡劫中化身 Bench 灰置文案（服务端 disabled_reason 优先） */
const tribulationAvatarHint = computed(
  () => characterStore.character?.status === 'tribulation',
)

/** 回擂台（整备完成后返回赛会演出页）。 */
async function goBackToArena(): Promise<void> {
  if (formationStore.isDirty) {
    try {
      await ElMessageBox.confirm('布阵草稿未保存，确定回擂台？', '未保存', {
        confirmButtonText: '放弃修改并回去',
        cancelButtonText: '留下',
      })
    } catch {
      return
    }
  }
  await router.push('/dao-lord/arena')
}

const loadError = ref('')
const saving = ref(false)
/** 当前选中的棋子 uid（Bench 点击或棋盘点击己方棋子） */
const selectedUid = ref<string | null>(null)
/** 选中棋子的种类（落子时带上） */
const selectedKind = ref<string>('main')
/** 选中棋子的持有物引用（灵宠 / 化身 / 真傀儡保存校验用） */
const selectedRefId = ref<number | undefined>(undefined)

/** 当前草稿阵法的地形格 */
const draftTerrain = computed(() => formationStore.draftFormation?.terrain ?? [])

/** 阵法地形禁停格 key 集合 */
const blockedKeys = computed(
  () =>
    new Set(
      draftTerrain.value
        .filter((c) => c.type === 'obstacle' || c.type === 'ravine' || c.type === 'seal')
        .map((c) => `${c.x},${c.y}`),
    ),
)

/** 有效可部署格（服务端解析；缺省回退 board-meta） */
const effectiveDeployCells = computed<[number, number][]>(() => {
  const fromFormation = formationStore.draftFormation?.effective_deploy_cells
  if (fromFormation && fromFormation.length > 0) {
    return fromFormation
  }
  return formationStore.boardMeta?.default_deploy_cells ?? []
})

/** 部署合法格 key 集合（与高亮同源） */
const deployKeys = computed(
  () => new Set(effectiveDeployCells.value.map(([x, y]) => `${x},${y}`)),
)

/** 部署模式展示文案 */
const deployModeLabel = computed(() => {
  const mode = formationStore.draftFormation?.deploy?.mode ?? 'default'
  const labels: Record<string, string> = {
    default: '默认区',
    fixed: '固定格',
    free_own: '己方半区自由',
    mask: '掩码区',
  }
  return labels[mode] ?? mode
})

/** 当前阵法生效的上阵上限（优先服务端 max_units_effective） */
const effectiveMaxUnits = computed(() => {
  const fromServer = formationStore.draftFormation?.max_units_effective
  if (typeof fromServer === 'number' && fromServer >= 0) {
    return fromServer
  }
  const formCap = formationStore.draftFormation?.max_units_formation
  const base = formationStore.maxUnits
  if (formCap == null) {
    return Math.min(base, effectiveDeployCells.value.length || base)
  }
  return Math.min(base, formCap, effectiveDeployCells.value.length || formCap)
})

/** 移位预览文案 */
const forceShiftHint = computed(() => {
  const shifts = formationStore.draftFormation?.force_shifts ?? []
  if (!shifts.length) return ''
  return shifts
    .map((s) => `(${s.from[0]},${s.from[1]})→(${s.to[0]},${s.to[1]})`)
    .join('；')
})

/**
 * 换阵后清洗不在新区 / 禁停格上的棋子；本体尽量挪到合法格。
 */
function pruneUnitsForCurrentDeploy(): void {
  const zone = new Set(effectiveDeployCells.value.map(([x, y]) => `${x},${y}`))
  const blocked = blockedKeys.value
  const before = formationStore.draft.units.length
  const oldMain = formationStore.draft.units.find((u) => u.unit_kind === 'main')

  let kept = formationStore.draft.units.filter((u) => {
    const key = `${u.x},${u.y}`
    return zone.has(key) && !blocked.has(key)
  })

  // 本体被洗掉：挪到锚点或首个空合法格
  if (oldMain && !kept.some((u) => u.unit_kind === 'main')) {
    const anchor = formationStore.boardMeta?.default_anchor_unit
    const candidates: [number, number][] = []
    if (anchor) candidates.push([anchor.x, anchor.y])
    candidates.push(...effectiveDeployCells.value)
    for (const [x, y] of candidates) {
      const key = `${x},${y}`
      if (!zone.has(key) || blocked.has(key)) continue
      if (kept.some((u) => u.x === x && u.y === y)) continue
      kept = [{ ...oldMain, x, y }, ...kept]
      break
    }
  }

  const limit = Math.max(effectiveMaxUnits.value, 0)
  // 超员时本体优先保留
  const main = kept.find((u) => u.unit_kind === 'main')
  const others = kept.filter((u) => u.unit_kind !== 'main')
  const ordered = main ? [main, ...others] : others
  formationStore.draft.units = ordered.slice(0, limit)

  const dropped = before - formationStore.draft.units.length
  if (dropped > 0) {
    ElMessage.warning(`换阵后 ${dropped} 个棋子不在可部署区，已自动撤下`)
  }
}

// 切换阵法 id 时清洗非法占位
watch(
  () => formationStore.draft.formation_id,
  (next, prev) => {
    if (!prev || next === prev) return
    if (!formationStore.boardMeta) return
    pruneUnitsForCurrentDeploy()
    selectedUid.value = null
    selectedKind.value = 'main'
    selectedRefId.value = undefined
  },
)

/** Bench 选中棋子。 */
function onSelectBench(unit: BenchUnit): void {
  selectedUid.value = unit.unit_uid
  selectedKind.value = unit.unit_kind
  selectedRefId.value = unit.ref_id
}

/**
 * 棋盘点击：优先选中己方棋子；已有选中则尝试落子 / 移动。
 */
function onCellClick(x: number, y: number): void {
  const key = `${x},${y}`
  const occupied = formationStore.draft.units.find((u) => u.x === x && u.y === y)

  // 点到己方棋子 → 切换选中（带回 ref_id）
  if (occupied && occupied.unit_uid !== selectedUid.value) {
    selectedUid.value = occupied.unit_uid
    selectedKind.value = occupied.unit_kind
    selectedRefId.value =
      occupied.ref_id ??
      formationStore.bench.find((b) => b.unit_uid === occupied.unit_uid)?.ref_id
    return
  }
  // 再次点击已选中的非本体棋子 → 撤下（解决无化身残留无法从 Bench 撤下）
  if (
    occupied &&
    occupied.unit_uid === selectedUid.value &&
    occupied.unit_kind !== 'main'
  ) {
    formationStore.remove(occupied.unit_uid)
    selectedUid.value = null
    selectedKind.value = 'main'
    selectedRefId.value = undefined
    ElMessage.success('已撤下')
    return
  }
  if (!selectedUid.value) {
    ElMessage.info('请先在左侧选择要上阵的棋子')
    return
  }
  // 合法性即时反馈（权威校验仍在服务端保存时执行）
  if (!deployKeys.value.has(key)) {
    ElMessage.warning('该格不在可部署区内')
    return
  }
  if (blockedKeys.value.has(key)) {
    ElMessage.warning('该格被阵法地形占用，不可停留')
    return
  }
  if (
    !occupied &&
    !formationStore.draft.units.some((u) => u.unit_uid === selectedUid.value) &&
    formationStore.draft.units.length >= effectiveMaxUnits.value
  ) {
    ElMessage.warning(`上阵数量已达上限（${effectiveMaxUnits.value}）`)
    return
  }
  // 落子时若选中态缺 ref_id，再从 Bench 补一次（避免灵宠保存 40057）
  const refId =
    selectedRefId.value ??
    formationStore.bench.find((b) => b.unit_uid === selectedUid.value)?.ref_id
  formationStore.place(
    {
      unit_uid: selectedUid.value,
      unit_kind: selectedKind.value,
      ref_id: refId,
    },
    x,
    y,
  )
}

/** 切换预设槽（脏草稿需确认）。 */
async function onSelectSlot(slot: number): Promise<void> {
  if (slot === formationStore.activeSlot) return
  if (formationStore.isDirty) {
    try {
      await ElMessageBox.confirm('当前草稿未保存，切换预设将丢弃修改。继续？', '未保存', {
        confirmButtonText: '丢弃并切换',
        cancelButtonText: '留在本槽',
      })
    } catch {
      return
    }
  }
  formationStore.selectSlot(slot)
  selectedUid.value = null
  selectedKind.value = 'main'
  selectedRefId.value = undefined
}

/** 保存当前草稿。 */
async function onSave(): Promise<void> {
  saving.value = true
  try {
    const error = await formationStore.save()
    if (error) {
      ElMessage.error(error)
      return
    }
    ElMessage.success('预设已保存（未自动更新防守快照）')
  } finally {
    saving.value = false
  }
}

// 离开页守卫：脏草稿确认
onBeforeRouteLeave(async () => {
  if (!formationStore.isDirty) return true
  try {
    await ElMessageBox.confirm('布阵草稿未保存，确定离开？', '未保存', {
      confirmButtonText: '放弃修改',
      cancelButtonText: '留下',
    })
    return true
  } catch {
    return false
  }
})

onMounted(async () => {
  loadError.value = ''
  const error = await formationStore.load()
  if (error) {
    loadError.value = error
    return
  }
  // ?slot=N 打开指定槽
  const slotQuery = Number(route.query.slot)
  if (Number.isInteger(slotQuery) && slotQuery >= 0 && slotQuery <= 2) {
    formationStore.selectSlot(slotQuery)
  }
})
</script>

<template>
  <div class="formation-page">
    <AuthSessionBar />

    <div class="formation-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-button
        v-if="fromDaoArena"
        type="primary"
        size="small"
        @click="goBackToArena"
      >
        回擂台
      </el-button>
      <el-text tag="b" size="large">布阵</el-text>
      <el-text v-if="fromDaoArena" type="warning" size="small">
        擂台改的是进攻预设（及实时面板）；开打瞬间双方现场锁定，无需先刷防守快照 · 设好后点「回擂台」
      </el-text>
      <el-text v-else type="info" size="small">M3 · 预设三槽 · 阵法 · 防守快照</el-text>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="formation-alert"
    />

    <el-alert
      v-if="tribulationAvatarHint"
      title="渡劫中：化身不可上阵（Bench 将灰置）"
      type="warning"
      show-icon
      :closable="false"
      class="formation-alert"
    />

    <el-skeleton v-if="formationStore.loading" animated :rows="6" />

    <template v-else-if="formationStore.boardMeta">
      <div class="formation-toolbar">
        <FormationPresetBar
          :presets="formationStore.presets"
          :active-slot="formationStore.activeSlot"
          @select="onSelectSlot"
        />
        <div class="toolbar-right">
          <el-input
            v-model="formationStore.draft.name"
            size="small"
            maxlength="20"
            class="preset-name"
            placeholder="预设名"
          />
          <el-select v-model="formationStore.draft.role" size="small" class="role-select">
            <el-option value="attack" label="进攻" />
            <el-option value="defense" label="防守" />
            <el-option value="temp" label="临时" />
          </el-select>
          <FormationPicker
            v-model="formationStore.draft.formation_id"
            :formations="formationStore.formations"
            :array-craft-level="characterStore.character?.array_craft_level ?? 0"
          />
          <el-button
            type="primary"
            size="small"
            :loading="saving"
            :disabled="!formationStore.isDirty"
            @click="onSave"
          >
            保存
          </el-button>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="formation-alert"
        :title="`部署模式：${deployModeLabel} · 可部署 ${effectiveDeployCells.length} 格 · 上阵上限 ${effectiveMaxUnits}`"
        :description="
          forceShiftHint
            ? `开战移位预览：${forceShiftHint}（源空则无效）`
            : undefined
        "
      />

      <div class="formation-grid">
        <UnitBench
          :bench="formationStore.bench"
          :units="formationStore.draft.units"
          :selected-uid="selectedUid"
          :max-units="effectiveMaxUnits"
          @select="onSelectBench"
          @remove="formationStore.remove"
        />
        <FormationBoard
          :meta="formationStore.boardMeta"
          :units="formationStore.draft.units"
          :terrain="draftTerrain"
          :selected-uid="selectedUid"
          :deploy-cells="effectiveDeployCells"
          @cell-click="onCellClick"
        />
      </div>

      <SnapshotUpdateBar class="formation-snapshot" />
    </template>
  </div>
</template>

<style scoped>
.formation-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.formation-title {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
  flex-wrap: wrap;
}

.formation-alert {
  margin-bottom: 1rem;
}

.formation-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.preset-name {
  width: 140px;
}

.role-select {
  width: 100px;
}

.formation-grid {
  display: grid;
  grid-template-columns: minmax(200px, 260px) 1fr;
  gap: 1rem;
  align-items: start;
  margin-bottom: 1rem;
}

.formation-snapshot {
  margin-top: 0.5rem;
}

@media (max-width: 800px) {
  .formation-grid {
    grid-template-columns: 1fr;
  }
}
</style>
