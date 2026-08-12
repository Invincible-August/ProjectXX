<template>
  <div>
    <header class="head">
      <div>
        <h1>{{ title }}</h1>
        <p>
          域 <code>{{ domainId }}</code>
          · 风险 {{ meta?.risk || '-' }}
          · 已发布 v{{ meta?.published_version ?? 0 }}
        </p>
      </div>
      <div class="actions">
        <el-button @click="load" :loading="loading">重新加载</el-button>
        <el-button @click="onValidate" :loading="busy">校验</el-button>
        <el-button type="primary" @click="onSave" :loading="busy">保存 JSON 草稿</el-button>
        <el-button type="success" @click="onPublish" :loading="busy">发布</el-button>
        <el-button type="warning" @click="onClear" :loading="busy">回滚到 YAML</el-button>
      </div>
    </header>

    <el-alert
      v-if="schema?.dual_write_rule"
      type="success"
      :closable="false"
      :title="schema.dual_write_rule"
      style="margin-bottom: 12px"
    />

    <el-alert
      v-if="meta?.risk === 'balance' || meta?.risk === 'facility'"
      :type="meta?.risk === 'balance' ? 'warning' : 'info'"
      :closable="false"
      :title="
        meta?.risk === 'balance'
          ? '高危域：发布/回滚需二次确认（confirm_high_risk）。'
          : '设施域：开关发布后玩家 /facilities 与灵兽宗桩即时反映。'
      "
      style="margin-bottom: 12px"
    />

    <el-tabs v-model="tab">
      <el-tab-pane v-if="isDaoLordDomain" label="赛会日程" name="contest">
        <el-alert
          type="success"
          :closable="false"
          title="设置道主之争每日报名窗与开打时刻（配置时区）。保存后须再点右上角「发布」才会进线上服。"
          style="margin-bottom: 12px"
        />
        <el-form label-width="140px" class="contest-form" style="max-width: 520px">
          <el-form-item label="时区">
            <el-input v-model="contestForm.tz" placeholder="Asia/Shanghai" />
          </el-form-item>
          <el-form-item label="报名开始">
            <el-time-select
              v-model="contestForm.registration_start"
              start="00:00"
              step="00:05"
              end="23:55"
              placeholder="HH:MM"
            />
          </el-form-item>
          <el-form-item label="报名结束">
            <el-time-select
              v-model="contestForm.registration_end"
              start="00:00"
              step="00:05"
              end="23:55"
              placeholder="HH:MM"
            />
          </el-form-item>
          <el-form-item label="开打时刻">
            <el-time-select
              v-model="contestForm.fight_at"
              start="00:00"
              step="00:05"
              end="23:55"
              placeholder="HH:MM"
            />
          </el-form-item>
          <el-form-item label="直播准备秒">
            <el-input-number v-model="contestForm.live_prep_seconds" :min="3" :max="600" />
          </el-form-item>
          <el-form-item label="对战直播秒">
            <el-input-number v-model="contestForm.live_playback_seconds" :min="5" :max="3600" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="busy" @click="onSaveContestSchedule">
              保存赛会日程到草稿
            </el-button>
            <el-button :loading="busy" @click="syncContestFormFromDraft">从草稿重载</el-button>
          </el-form-item>
        </el-form>
        <p class="hint">
          <strong>立刻开赛 / 剔除道主</strong>在左侧「大道与道主 → 道主运营」。
          本页只改报名/开打时刻；改完请「保存赛会日程」再「发布」。
        </p>
        <div class="entry-toolbar">
          <el-button type="warning" @click="goDaoLordOps">打开道主运营（立刻开赛 / 剔除）</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="字段说明" name="fields">
        <el-alert
          type="info"
          :closable="false"
          :title="coverageTitle"
          style="margin-bottom: 10px"
        />
        <el-input
          v-model="fieldFilter"
          clearable
          placeholder="按路径 / 中文名 / 说明筛选"
          style="margin-bottom: 10px; max-width: 420px"
        />
        <el-table :data="filteredCatalog" border stripe size="small" max-height="520">
          <el-table-column prop="path" label="配置路径" min-width="220" />
          <el-table-column prop="label_zh" label="中文名" width="140" />
          <el-table-column prop="help_zh" label="说明" min-width="240" />
          <el-table-column prop="value_kind" label="类型" width="90" />
          <el-table-column label="已注释" width="88">
            <template #default="{ row }">
              <el-tag :type="row.documented ? 'success' : 'warning'" size="small">
                {{ row.documented ? '是' : '待补' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="样例" min-width="120">
            <template #default="{ row }">
              <code class="sample">{{ formatSample(row.sample) }}</code>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane v-if="supportsSheets" label="表格编辑" name="sheets">
        <p class="hint">
          面向非编码运营：改表后点「保存表格→草稿」，后端会 format 成域 JSON。会 coding 的同事也可切到「JSON 覆盖」。
        </p>
        <div class="entry-toolbar">
          <el-button size="small" type="primary" :loading="busy" @click="onSaveSheets">
            保存表格 → 草稿
          </el-button>
          <el-button size="small" @click="onExportJson">导出生效 JSON</el-button>
          <el-button size="small" @click="showJsonImport = true">导入 JSON/YAML</el-button>
        </div>
        <el-collapse v-model="openSheets">
          <el-collapse-item
            v-for="sheet in sheetViews"
            :key="sheet.sheet_id"
            :name="sheet.sheet_id"
            :title="`${sheet.title_zh}（${sheet.sheet_id}）`"
          >
            <p class="hint">{{ sheet.description_zh }}</p>
            <div class="entry-toolbar">
              <el-button size="small" @click="addSheetRow(sheet.sheet_id)">新增行</el-button>
            </div>
            <el-table :data="sheet.rows" border stripe size="small" max-height="360">
              <el-table-column
                v-for="col in sheet.columns"
                :key="col.key"
                :prop="col.key"
                :label="col.label_zh"
                min-width="120"
              >
                <template #header>
                  <el-tooltip :content="col.help_zh" placement="top">
                    <span>{{ col.label_zh }}</span>
                  </el-tooltip>
                </template>
                <template #default="{ row }">
                  <el-input
                    v-if="col.value_type === 'bool'"
                    v-model="row[col.key]"
                    size="small"
                    placeholder="true/false"
                  />
                  <el-input v-else v-model="row[col.key]" size="small" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="88" fixed="right">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="removeSheetRow(sheet.sheet_id, $index)">
                    删行
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>

      <el-tab-pane v-if="supportsEntries" label="表格编辑（条目）" name="entries">
        <el-alert
          v-if="entryFieldHelp.length"
          type="success"
          :closable="false"
          title="下列为条目字段中文说明（编辑弹窗也会展示）。全量路径见「字段说明」页。"
          style="margin-bottom: 10px"
        />
        <el-table
          v-if="entryFieldHelp.length"
          :data="entryFieldHelp"
          size="small"
          border
          style="margin-bottom: 12px"
          max-height="180"
        >
          <el-table-column prop="key" label="字段键" width="160" />
          <el-table-column prop="label_zh" label="中文名" width="140" />
          <el-table-column prop="help_zh" label="说明" />
        </el-table>
        <div class="entry-toolbar">
          <el-button size="small" type="primary" @click="openNewEntry">新增条目</el-button>
          <el-button size="small" @click="onExportCsv">导出 CSV</el-button>
          <el-button size="small" @click="showCsvImport = true">导入 CSV</el-button>
          <el-button size="small" @click="onExportJson">导出生效 JSON</el-button>
          <el-button size="small" @click="showJsonImport = true">导入 JSON/YAML</el-button>
        </div>
        <el-table :data="entryRows" border stripe size="small" max-height="480">
          <el-table-column prop="id" label="ID" width="180" />
          <el-table-column prop="name" label="名称" width="160" />
          <el-table-column prop="summary" label="摘要" />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button link type="primary" @click="editEntry(row.id)">编辑</el-button>
              <el-button
                link
                type="danger"
                :disabled="!row.inDraft"
                @click="removeEntry(row.id)"
              >
                撤草稿
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="JSON 覆盖" name="draft">
        <p class="hint">
          面向会 coding 的运营：直接写 JSON。完整中文说明请看「字段说明」页（覆盖本域全部可配置路径）。
        </p>
        <el-input
          v-model="draftText"
          type="textarea"
          :rows="22"
          class="mono"
          placeholder='partial overlay，例如 {"species":{"new_fox":{...}}}'
        />
      </el-tab-pane>
      <el-tab-pane label="当前生效" name="effective">
        <pre class="json">{{ effectiveText }}</pre>
      </el-tab-pane>
      <el-tab-pane label="YAML 底表" name="yaml">
        <pre class="json">{{ yamlText }}</pre>
      </el-tab-pane>
      <el-tab-pane label="历史" name="revisions">
        <el-table :data="revisions" size="small" border>
          <el-table-column prop="version" label="版本" width="80" />
          <el-table-column prop="action" label="动作" width="100" />
          <el-table-column prop="note" label="说明" />
          <el-table-column prop="published_at" label="时间" width="200" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="entryDialog" :title="entryDialogTitle" width="720px">
      <el-alert
        v-if="entryFieldHelp.length"
        type="info"
        :closable="false"
        title="下列为推荐字段中文说明；高级仍可用 JSON。"
        style="margin-bottom: 10px"
      />
      <el-table
        v-if="entryFieldHelp.length"
        :data="entryFieldHelp"
        size="small"
        border
        style="margin-bottom: 12px"
      >
        <el-table-column prop="key" label="字段" width="140" />
        <el-table-column prop="label_zh" label="中文" width="120" />
        <el-table-column prop="help_zh" label="说明" />
      </el-table>
      <el-form label-width="88px">
        <el-form-item label="条目 ID">
          <el-input v-model="editingId" :disabled="Boolean(editingOriginalId)" />
        </el-form-item>
        <el-form-item label="定义 JSON">
          <el-input v-model="editingBodyText" type="textarea" :rows="14" class="mono" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="entryDialog = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveEntry">写入草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showCsvImport" title="导入 CSV → 草稿" width="640px">
      <el-input v-model="importText" type="textarea" :rows="12" class="mono" />
      <template #footer>
        <el-button @click="showCsvImport = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="doImportCsv">合并导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showJsonImport" title="导入 JSON/YAML → 草稿" width="640px">
      <el-radio-group v-model="importFmt" style="margin-bottom: 8px">
        <el-radio-button value="json">JSON</el-radio-button>
        <el-radio-button value="yaml">YAML</el-radio-button>
      </el-radio-group>
      <el-input v-model="importText" type="textarea" :rows="12" class="mono" />
      <template #footer>
        <el-button @click="showJsonImport = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="doImportJson">合并导入</el-button>
      </template>
    </el-dialog>

    <p v-if="message" class="msg">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteEntry,
  exportDomain,
  exportEntriesCsv,
  fetchDomains,
  fetchDomainSchema,
  fetchDraft,
  fetchEffective,
  fetchEntries,
  fetchRevisions,
  fetchSheets,
  importDomain,
  importEntriesCsv,
  publishDomain,
  rollbackDomain,
  saveDraft,
  saveSheets,
  upsertEntry,
  validateDraft,
} from '../api/config'
import type { DomainEditSchema, DomainSummary, FieldMeta, SheetView } from '../types/api'

const props = defineProps<{ domainId: string }>()
const router = useRouter()

const loading = ref(false)
const busy = ref(false)
const tab = ref('fields')
const draftText = ref('{}')
const effectiveText = ref('')
const yamlText = ref('')
const message = ref('')
const meta = ref<DomainSummary | null>(null)
const schema = ref<DomainEditSchema | null>(null)
const revisions = ref<Array<Record<string, unknown>>>([])
const entries = ref<Record<string, Record<string, unknown>>>({})
const draftEntryIds = ref<string[]>([])
const sheetViews = ref<SheetView[]>([])
const openSheets = ref<string[]>([])
const fieldFilter = ref('')

const entryDialog = ref(false)
const editingId = ref('')
const editingOriginalId = ref('')
const editingBodyText = ref('{}')
const showCsvImport = ref(false)
const showJsonImport = ref(false)
const importText = ref('')
const importFmt = ref<'json' | 'yaml'>('json')

const title = computed(() => meta.value?.title || props.domainId)
const isDaoLordDomain = computed(() => props.domainId === 'dao_lord')

const contestForm = ref({
  tz: 'Asia/Shanghai',
  registration_start: '18:00',
  registration_end: '19:55',
  fight_at: '20:00',
  live_prep_seconds: 15,
  live_playback_seconds: 90,
})

const supportsEntries = computed(
  () =>
    Boolean(schema.value?.supports_entries) ||
    Boolean(meta.value?.supports_entries) ||
    Boolean(schema.value?.edit_modes?.includes('entries')),
)
const supportsSheets = computed(
  () =>
    Boolean(schema.value?.supports_sheets) ||
    Boolean(meta.value?.supports_sheets) ||
    Boolean(schema.value?.sheets?.length),
)
const entryDialogTitle = computed(() =>
  editingOriginalId.value ? `编辑 ${editingOriginalId.value}` : '新增条目',
)
const entryFieldHelp = computed(() => schema.value?.entry_fields ?? [])
const fieldCatalog = computed(() => schema.value?.field_catalog ?? [])
const coverageTitle = computed(() => {
  const cov = schema.value?.field_coverage
  if (!cov) return '本页列出当前生效配置中的全部可配置路径及中文说明。'
  return `字段中文覆盖：${cov.documented_paths}/${cov.total_paths}（覆盖率 ${(cov.coverage_ratio * 100).toFixed(1)}%）；未注释项请补 admin_field_catalog。`
})
const filteredCatalog = computed(() => {
  const q = fieldFilter.value.trim().toLowerCase()
  const rows = fieldCatalog.value
  if (!q) return rows
  return rows.filter(
    (row) =>
      row.path.toLowerCase().includes(q) ||
      row.label_zh.toLowerCase().includes(q) ||
      row.help_zh.toLowerCase().includes(q),
  )
})

const entryRows = computed(() =>
  Object.entries(entries.value).map(([id, body]) => ({
    id,
    name: String(body.name ?? body.title ?? ''),
    summary: summarize(body),
    inDraft: draftEntryIds.value.includes(id),
  })),
)

function goDaoLordOps() {
  void router.push({ name: 'ops-dao-lords' })
}

function syncContestFormFromDraft() {
  try {
    const draft = parseDraft()
    const contest =
      draft.contest && typeof draft.contest === 'object' && !Array.isArray(draft.contest)
        ? (draft.contest as Record<string, unknown>)
        : {}
    // 草稿为空时回落生效配置
    let base: Record<string, unknown> = contest
    if (!Object.keys(contest).length) {
      try {
        const eff = JSON.parse(effectiveText.value || '{}') as Record<string, unknown>
        const c = eff.contest
        if (c && typeof c === 'object' && !Array.isArray(c)) {
          base = c as Record<string, unknown>
        }
      } catch {
        /* ignore */
      }
    }
    contestForm.value = {
      tz: String(base.tz || 'Asia/Shanghai'),
      registration_start: String(base.registration_start || '18:00'),
      registration_end: String(base.registration_end || '19:55'),
      fight_at: String(base.fight_at || '20:00'),
      live_prep_seconds: Number(base.live_prep_seconds ?? 15),
      live_playback_seconds: Number(base.live_playback_seconds ?? 90),
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '读取草稿失败')
  }
}

async function onSaveContestSchedule() {
  busy.value = true
  try {
    const start = String(contestForm.value.registration_start || '').trim()
    const end = String(contestForm.value.registration_end || '').trim()
    const fight = String(contestForm.value.fight_at || '').trim()
    const hhmm = /^\d{1,2}:\d{2}$/
    if (!hhmm.test(start) || !hhmm.test(end) || !hhmm.test(fight)) {
      throw new Error('报名开始/结束与开打时刻须为 HH:MM（请用时间选择器）')
    }
    const draft = parseDraft()
    const prev =
      draft.contest && typeof draft.contest === 'object' && !Array.isArray(draft.contest)
        ? { ...(draft.contest as Record<string, unknown>) }
        : {}
    draft.contest = {
      ...prev,
      tz: contestForm.value.tz.trim() || 'Asia/Shanghai',
      registration_start: start,
      registration_end: end,
      fight_at: fight,
      live_prep_seconds: Number(contestForm.value.live_prep_seconds),
      live_playback_seconds: Number(contestForm.value.live_playback_seconds),
    }
    draftText.value = JSON.stringify(draft, null, 2)
    await saveDraft(props.domainId, draft)
    ElMessage.success('赛会日程已写入草稿；请再点「发布」生效')
    message.value = '赛会日程草稿已保存'
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存赛会日程失败')
  } finally {
    busy.value = false
  }
}

function formatSample(sample: unknown): string {
  if (sample === null || sample === undefined) return ''
  if (typeof sample === 'object') return JSON.stringify(sample)
  return String(sample)
}

function summarize(body: Record<string, unknown>): string {
  if (typeof body.note === 'string' && body.note) return body.note
  if (typeof body.summary === 'string' && body.summary) return body.summary
  if (body.enabled !== undefined) return `enabled=${String(body.enabled)}`
  return JSON.stringify(body).slice(0, 80)
}

function parseDraft(): Record<string, unknown> {
  const raw = JSON.parse(draftText.value || '{}') as unknown
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('草稿须为 JSON object')
  }
  return raw as Record<string, unknown>
}

function emptyRow(columns: FieldMeta[]): Record<string, unknown> {
  const row: Record<string, unknown> = {}
  for (const col of columns) {
    row[col.key] = col.value_type === 'bool' ? 'false' : ''
  }
  return row
}

function addSheetRow(sheetId: string) {
  const sheet = sheetViews.value.find((item) => item.sheet_id === sheetId)
  if (!sheet) return
  sheet.rows.push(emptyRow(sheet.columns))
}

function removeSheetRow(sheetId: string, index: number) {
  const sheet = sheetViews.value.find((item) => item.sheet_id === sheetId)
  if (!sheet) return
  sheet.rows.splice(index, 1)
}

async function load() {
  loading.value = true
  message.value = ''
  try {
    const [domains, draft, effective, revs, schemaData] = await Promise.all([
      fetchDomains(),
      fetchDraft(props.domainId),
      fetchEffective(props.domainId),
      fetchRevisions(props.domainId),
      fetchDomainSchema(props.domainId),
    ])
    meta.value = domains.domains.find((d) => d.domain_id === props.domainId) || null
    schema.value = schemaData
    draftText.value = JSON.stringify(draft.payload ?? {}, null, 2)
    effectiveText.value = JSON.stringify(effective.payload, null, 2)
    yamlText.value = JSON.stringify(effective.yaml_base, null, 2)
    revisions.value = revs.revisions

    const wantSheets =
      Boolean(schemaData.supports_sheets) ||
      Boolean(meta.value?.supports_sheets) ||
      Boolean(schemaData.sheets?.length)
    const wantEntries =
      Boolean(schemaData.supports_entries) ||
      Boolean(meta.value?.supports_entries) ||
      Boolean(schemaData.edit_modes?.includes('entries'))

    if (wantSheets) {
      const sheetData = await fetchSheets(props.domainId)
      sheetViews.value = sheetData.sheets.map((sheet) => ({
        ...sheet,
        rows: sheet.rows.map((row) => ({ ...row })),
      }))
      openSheets.value = sheetViews.value.slice(0, 2).map((s) => s.sheet_id)
      tab.value = 'sheets'
    } else if (props.domainId === 'dao_lord') {
      tab.value = 'contest'
    } else if (wantEntries) {
      tab.value = 'entries'
    } else {
      tab.value = 'fields'
    }

    if (props.domainId === 'dao_lord') {
      syncContestFormFromDraft()
    }

    if (wantEntries) {
      const ent = await fetchEntries(props.domainId)
      entries.value = ent.entries
      draftEntryIds.value = ent.draft_entry_ids
    } else {
      entries.value = {}
      draftEntryIds.value = []
    }
    if (!wantSheets) {
      sheetViews.value = []
    }
  } catch (err) {
    message.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function onSaveSheets() {
  busy.value = true
  try {
    const payload = sheetViews.value.map((sheet) => ({
      sheet_id: sheet.sheet_id,
      rows: sheet.rows,
    }))
    await saveSheets(props.domainId, payload, true)
    ElMessage.success('表格已 format 为 JSON 并写入草稿')
    await load()
    tab.value = 'draft'
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存表格失败')
  } finally {
    busy.value = false
  }
}

async function onValidate() {
  busy.value = true
  try {
    const payload = parseDraft()
    const res = await validateDraft(props.domainId, payload)
    ElMessage.success(String((res as { message?: string }).message || '校验通过'))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '校验失败')
  } finally {
    busy.value = false
  }
}

async function onSave() {
  busy.value = true
  try {
    const payload = parseDraft()
    await saveDraft(props.domainId, payload)
    ElMessage.success('草稿已保存')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    busy.value = false
  }
}

async function onPublish() {
  const highRisk = meta.value?.risk === 'balance'
  try {
    await ElMessageBox.confirm(
      highRisk ? '高危域：确认发布并写入玩家服？' : '确认将草稿发布到玩家服？',
      '发布确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  busy.value = true
  try {
    await publishDomain(props.domainId, '', highRisk)
    ElMessage.success('已发布')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '发布失败')
  } finally {
    busy.value = false
  }
}

async function onClear() {
  const highRisk = meta.value?.risk === 'balance'
  try {
    await ElMessageBox.confirm('清除覆盖层，玩家服回到纯 YAML？', '回滚', { type: 'warning' })
  } catch {
    return
  }
  busy.value = true
  try {
    await rollbackDomain(props.domainId, 0, highRisk)
    ElMessage.success('已回滚到 YAML')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '回滚失败')
  } finally {
    busy.value = false
  }
}

function openNewEntry() {
  editingOriginalId.value = ''
  editingId.value = ''
  const seed: Record<string, unknown> = { name: '' }
  for (const field of entryFieldHelp.value) {
    if (field.key === 'name') continue
    if (field.value_type === 'bool') seed[field.key] = false
    else if (field.value_type === 'int' || field.value_type === 'float') seed[field.key] = 0
    else if (field.value_type === 'json') seed[field.key] = {}
    else seed[field.key] = ''
  }
  editingBodyText.value = JSON.stringify(seed, null, 2)
  entryDialog.value = true
}

function editEntry(id: string) {
  editingOriginalId.value = id
  editingId.value = id
  editingBodyText.value = JSON.stringify(entries.value[id] ?? {}, null, 2)
  entryDialog.value = true
}

async function saveEntry() {
  busy.value = true
  try {
    const id = editingId.value.trim()
    if (!id) throw new Error('条目 ID 不能为空')
    const body = JSON.parse(editingBodyText.value || '{}') as Record<string, unknown>
    await upsertEntry(props.domainId, id, body)
    entryDialog.value = false
    ElMessage.success('已写入草稿')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '写入失败')
  } finally {
    busy.value = false
  }
}

async function removeEntry(id: string) {
  busy.value = true
  try {
    await deleteEntry(props.domainId, id)
    ElMessage.success('已从草稿撤除')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '撤除失败')
  } finally {
    busy.value = false
  }
}

async function onExportCsv() {
  try {
    const data = await exportEntriesCsv(props.domainId)
    await navigator.clipboard.writeText(data.content)
    ElMessage.success('CSV 已复制到剪贴板')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导出失败')
  }
}

async function onExportJson() {
  try {
    const data = await exportDomain(props.domainId, 'effective', 'json')
    await navigator.clipboard.writeText(data.content)
    ElMessage.success('生效 JSON 已复制到剪贴板')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导出失败')
  }
}

async function doImportCsv() {
  busy.value = true
  try {
    await importEntriesCsv(props.domainId, importText.value, 'merge')
    showCsvImport.value = false
    importText.value = ''
    ElMessage.success('CSV 已合并进草稿')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导入失败')
  } finally {
    busy.value = false
  }
}

async function doImportJson() {
  busy.value = true
  try {
    await importDomain(props.domainId, importText.value, importFmt.value, 'merge')
    showJsonImport.value = false
    importText.value = ''
    ElMessage.success('已合并进草稿')
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导入失败')
  } finally {
    busy.value = false
  }
}

watch(
  () => props.domainId,
  () => {
    void load()
  },
  { immediate: true },
)
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.head h1 {
  margin: 0 0 4px;
}
.head p {
  margin: 0;
  color: #5c564c;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.entry-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.mono :deep(textarea) {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
}
.json {
  max-height: 520px;
  overflow: auto;
  background: #f7f4ee;
  padding: 12px;
  font-size: 12px;
}
.hint {
  color: #5c564c;
  font-size: 12px;
}
.msg {
  color: #a33;
}
.sample {
  font-size: 11px;
  color: #5c564c;
}
</style>
