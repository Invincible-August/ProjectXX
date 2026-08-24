<template>
  <div class="sheet-grid">
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" size="small" @click="onAdd">新增</el-button>
        <el-button
          type="danger"
          size="small"
          plain
          :disabled="selectedRows.length === 0"
          @click="onBatchDelete"
        >
          批量删除（{{ selectedRows.length }}）
        </el-button>
        <el-button type="success" size="small" :loading="saving" :disabled="!dirty" @click="onSave">
          保存修改
        </el-button>
        <el-button size="small" :disabled="!dirty || saving" @click="onCancel">取消修改</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="dirty" type="warning" size="small" effect="plain">有未保存改动</el-tag>
        <el-tag v-else type="info" size="small" effect="plain">已与预览同步</el-tag>
        <el-text size="small" type="info">{{ rows.length }} 行</el-text>
      </div>
    </div>

    <el-table
      ref="tableRef"
      :data="rows"
      border
      stripe
      size="small"
      height="420"
      class="grid-table"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="42" fixed="left" />
      <el-table-column
        v-for="col in columns"
        :key="col.key"
        :prop="col.key"
        :label="col.label_zh"
        :min-width="colWidth(col)"
      >
        <template #header>
          <el-tooltip :content="col.help_zh || col.label_zh" placement="top">
            <span>{{ col.label_zh }}</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="selectOptions[col.key]"
            v-model="row[col.key]"
            size="small"
            filterable
            allow-create
            default-first-option
            style="width: 100%"
            @change="markDirty"
          >
            <el-option
              v-for="opt in selectOptions[col.key]"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-input
            v-else-if="col.value_type === 'bool'"
            v-model="row[col.key]"
            size="small"
            placeholder="true/false"
            @input="markDirty"
          />
          <el-input
            v-else
            v-model="row[col.key]"
            size="small"
            :type="col.key === 'description' ? 'textarea' : 'text'"
            :autosize="col.key === 'description' ? { minRows: 1, maxRows: 3 } : undefined"
            @input="markDirty"
          />
        </template>
      </el-table-column>
      <el-table-column label="行操作" width="72" fixed="right">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" @click="removeAt($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * Navicat 风格配置网格：勾选、批量删除、新增、保存/取消（本地脏状态）。
 * 保存通过父组件回调写入草稿；存储仍走 YAML 底表 + DB overlay，与后期入库兼容。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FieldMeta } from '../types/api'

export interface SelectOption {
  value: string
  label: string
}

const props = withDefaults(
  defineProps<{
    /** 列定义 */
    columns: FieldMeta[]
    /** 主键列（用于空行默认值提示） */
    primaryKeys?: string[]
    /** 初始行（来自 GET /sheets） */
    modelValue: Record<string, unknown>[]
    /** 某列下拉选项（如 category / rarity） */
    selectOptions?: Record<string, SelectOption[]>
    saving?: boolean
  }>(),
  {
    primaryKeys: () => [],
    selectOptions: () => ({}),
    saving: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [rows: Record<string, unknown>[]]
  save: [rows: Record<string, unknown>[]]
  cancel: []
}>()

const rows = ref<Record<string, unknown>[]>([])
const snapshot = ref('[]')
const dirty = ref(false)
const selectedRows = ref<Record<string, unknown>[]>([])
const tableRef = ref<{ clearSelection?: () => void } | null>(null)

const columns = computed(() => props.columns || [])

function cloneRows(source: Record<string, unknown>[]): Record<string, unknown>[] {
  return source.map((row) => ({ ...row }))
}

function serialize(source: Record<string, unknown>[]): string {
  return JSON.stringify(source)
}

function hydrate(source: Record<string, unknown>[]): void {
  rows.value = cloneRows(source)
  snapshot.value = serialize(rows.value)
  dirty.value = false
  selectedRows.value = []
  tableRef.value?.clearSelection?.()
}

watch(
  () => props.modelValue,
  (val) => {
    hydrate(val || [])
  },
  { immediate: true, deep: true },
)

function markDirty(): void {
  dirty.value = serialize(rows.value) !== snapshot.value
  emit('update:modelValue', rows.value)
}

function onSelectionChange(selection: Record<string, unknown>[]): void {
  selectedRows.value = selection
}

function emptyRow(): Record<string, unknown> {
  const row: Record<string, unknown> = {}
  for (const col of columns.value) {
    if (col.value_type === 'bool') row[col.key] = 'false'
    else if (col.value_type === 'float' || col.value_type === 'int') row[col.key] = ''
    else row[col.key] = ''
  }
  return row
}

function onAdd(): void {
  rows.value.push(emptyRow())
  markDirty()
}

function removeAt(index: number): void {
  rows.value.splice(index, 1)
  markDirty()
}

async function onBatchDelete(): Promise<void> {
  if (!selectedRows.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedRows.value.length} 行？保存并发布后才会覆盖线上/YAML 底表对应条目。`,
      '批量删除',
      { type: 'warning' },
    )
  } catch {
    return
  }
  const victim = new Set(selectedRows.value)
  rows.value = rows.value.filter((row) => !victim.has(row))
  selectedRows.value = []
  tableRef.value?.clearSelection?.()
  markDirty()
}

function onSave(): void {
  emit('save', cloneRows(rows.value))
}

async function onCancel(): Promise<void> {
  if (!dirty.value) return
  try {
    await ElMessageBox.confirm('放弃本地未保存改动，恢复为上次加载结果？', '取消修改', {
      type: 'warning',
    })
  } catch {
    return
  }
  rows.value = JSON.parse(snapshot.value) as Record<string, unknown>[]
  dirty.value = false
  selectedRows.value = []
  tableRef.value?.clearSelection?.()
  emit('update:modelValue', rows.value)
  emit('cancel')
  ElMessage.info('已取消本地修改')
}

/** 保存成功后由父组件调用，刷新快照 */
function acceptSaved(nextRows?: Record<string, unknown>[]): void {
  hydrate(nextRows ?? rows.value)
}

function colWidth(col: FieldMeta): number {
  if (col.key === 'description') return 220
  if (col.key === 'dao_id' || col.key === 'attacker' || col.key === 'defender') return 140
  if (col.key === 'label_zh') return 110
  return 100
}

defineExpose({ acceptSaved, markDirty, rows })
</script>

<style scoped>
.sheet-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.grid-table {
  width: 100%;
}
.grid-table :deep(.el-input__wrapper),
.grid-table :deep(.el-select__wrapper) {
  box-shadow: none;
  background: transparent;
}
.grid-table :deep(.el-table__cell) {
  padding: 4px 0;
}
</style>
