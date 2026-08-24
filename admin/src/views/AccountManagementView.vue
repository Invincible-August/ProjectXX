<template>
  <div class="accounts-page">
    <header class="page-head">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p class="sub">{{ pageDesc }}</p>
      </div>
      <div class="toolbar">
        <el-input
          v-model="keyword"
          clearable
          placeholder="邮箱 / 手机号 / user_id"
          class="search"
          @keyup.enter="onSearch"
        />
        <el-button type="primary" :loading="loading" @click="onSearch">搜索</el-button>
        <el-button :disabled="loading" @click="onReset">重置</el-button>
        <span class="page-size-label">每页</span>
        <el-select v-model="pageSize" style="width: 96px" @change="onPageSizeChange">
          <el-option v-for="n in pageSizeOptions" :key="n" :value="n" :label="String(n)" />
        </el-select>
      </div>
    </header>

    <div class="batch-bar">
      <span class="batch-hint">已选 {{ selectedRows.length }} 项</span>
      <el-button
        type="danger"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchBan(true)"
      >
        封号
      </el-button>
      <el-button
        type="success"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchBan(false)"
      >
        解封
      </el-button>
      <el-button
        type="warning"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchResetPassword"
      >
        重置密码
      </el-button>
      <el-button
        type="primary"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="openContactsBatch"
      >
        修改联系方式
      </el-button>
      <el-button
        type="success"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="openGrantBatch"
      >
        派发仙缘
      </el-button>
      <el-button
        type="danger"
        size="small"
        :disabled="!selectedRows.length || acting"
        @click="batchSoftDelete"
      >
        删除账号
      </el-button>
      <el-button
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchSetGm(true)"
      >
        设为GM
      </el-button>
      <el-button
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchSetGm(false)"
      >
        取消GM
      </el-button>
      <el-text type="info" size="small" class="gm-note">GM 功能暂未开放</el-text>
    </div>

    <div class="grid-wrap">
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="rows"
        border
        stripe
        size="small"
        height="520"
        class="navicat-grid"
        empty-text="暂无账号"
        row-key="id"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="42" fixed="left" />
        <el-table-column prop="id" label="数据库ID" width="96" fixed="left" />
        <el-table-column prop="user_id" label="user_id" width="110" />
        <el-table-column prop="email" label="邮箱" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.email || '—' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="120">
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column prop="fate_luck" label="剩余仙缘" width="90" align="right" />
        <el-table-column
          prop="total_recharge_amount"
          label="总打赏金额"
          width="110"
          align="right"
        />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_banned ? 'danger' : 'success'" size="small" effect="plain">
              {{ row.is_banned ? '无效' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="GM" width="64" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_gm" type="warning" size="small" effect="plain">GM</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="道号" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button
              v-if="row.character_id && row.character_name"
              link
              type="primary"
              @click="goCharacter(row)"
            >
              {{ row.character_name }}
            </el-button>
            <span v-else>未创角</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="360" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openTipCreate(row)">
              记录打赏
            </el-button>
            <el-button link type="info" size="small" @click="openRecords('tip', row)">
              查看打赏
            </el-button>
            <el-button link type="success" size="small" @click="openRecords('grant', row)">
              仙缘派发记录
            </el-button>
            <el-button link type="warning" size="small" @click="openRecords('ad', row)">
              广告观看记录
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, jumper"
        background
        @current-change="load"
      />
    </div>

    <el-dialog v-model="contactsVisible" title="修改邮箱 / 手机号" width="420px" destroy-on-close>
      <p v-if="contactsTargets.length > 1" class="dialog-hint">
        将写入选中的 {{ contactsTargets.length }} 个账号（联系方式全局唯一，批量时请谨慎）。
      </p>
      <el-form label-width="72px">
        <el-form-item label="邮箱">
          <el-input v-model="contactsForm.email" clearable placeholder="留空可清空" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="contactsForm.phone" clearable placeholder="留空可清空" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contactsVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitContacts">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="grantVisible" title="派发仙缘" width="380px" destroy-on-close>
      <p v-if="grantTargets.length > 1" class="dialog-hint">
        将对已创角的 {{ grantTargets.filter((r) => r.character_id).length }} /
        {{ grantTargets.length }} 个选中账号各派发相同数量。
      </p>
      <el-form label-width="88px">
        <el-form-item v-if="grantTargets.length === 1" label="当前仙缘">
          <el-text>{{ grantForm.current }}</el-text>
        </el-form-item>
        <el-form-item label="派发数量">
          <el-input-number v-model="grantForm.amount" :min="1" :max="999999999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitGrant">确认派发</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tipCreateVisible" title="记录打赏" width="480px" destroy-on-close>
      <el-form label-width="88px">
        <el-form-item label="账号">
          <el-text>user_id={{ tipPublicUid }}（库 id={{ tipDbId }}）</el-text>
        </el-form-item>
        <el-form-item :label="fieldLabel('tip_create', 'paid_at', '打赏时间')" required>
          <el-date-picker
            v-model="tipForm.paidAt"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            format="YYYY-MM-DD HH:mm:ss"
            placeholder="选择年月日时分秒"
          />
        </el-form-item>
        <el-form-item :label="fieldLabel('tip_create', 'channel', '路径')" required>
          <el-select v-model="tipForm.channel" filterable allow-create default-first-option>
            <el-option v-for="c in tipChannelPresets" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item :label="fieldLabel('tip_create', 'order_no', '订单号')" required>
          <el-input v-model="tipForm.orderNo" />
        </el-form-item>
        <el-form-item :label="fieldLabel('tip_create', 'amount', '金额')" required>
          <el-input-number v-model="tipForm.amount" :min="1" :max="999999999" />
        </el-form-item>
        <el-form-item :label="fieldLabel('tip_create', 'note', '备注')">
          <el-input v-model="tipForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tipCreateVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitTip">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="recordVisible"
      :title="recordTitle"
      width="720px"
      destroy-on-close
      @closed="onRecordClosed"
    >
      <p v-if="recordHint" class="record-hint">{{ recordHint }}</p>
      <el-table
        v-loading="recordLoading"
        :data="recordRows"
        border
        stripe
        size="small"
        height="360"
        class="navicat-grid"
        empty-text="暂无记录"
      >
        <el-table-column
          v-for="col in recordColumns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :min-width="col.minWidth || 100"
          :width="col.width"
          show-overflow-tooltip
        />
      </el-table>
      <div class="pager dialog-pager">
        <el-pagination
          v-model:current-page="recordPage"
          :page-size="recordPageSize"
          :total="recordTotal"
          layout="total, prev, pager, next"
          background
          @current-change="loadRecords"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * 玩家账号管理：勾选批量运营 + 行内流水；user_id 为对外账号号。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  banPlayer,
  createPlayerTip,
  fetchAdWatches,
  fetchFateLuckGrants,
  fetchPlayerAccounts,
  fetchPlayerOpsSchema,
  fetchPlayerTips,
  grantPlayerFateLuck,
  resetPlayerPassword,
  setPlayerGm,
  softDeletePlayer,
  updatePlayerContacts,
  type FieldMetaDto,
  type PlayerAccountRow,
  type PlayerOpsSchema,
} from '../api/players'

const router = useRouter()

type RecordKind = 'tip' | 'grant' | 'ad'

interface RecordColumn {
  prop: string
  label: string
  width?: number
  minWidth?: number
}

const schema = ref<PlayerOpsSchema | null>(null)
const loading = ref(false)
const acting = ref(false)
const rows = ref<PlayerAccountRow[]>([])
const selectedRows = ref<PlayerAccountRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pageSizeOptions = computed(() => schema.value?.page_sizes ?? [10, 20, 50, 100])
const tipChannelPresets = computed(() => schema.value?.tip_channel_presets ?? ['微信', '支付宝'])
const resetPasswordPlain = computed(() => schema.value?.reset_password_plaintext ?? '12345678')
const pageTitle = computed(() => schema.value?.title_zh ?? '玩家管理 · 账号管理')
const pageDesc = computed(() => schema.value?.description_zh ?? '玩家账号检索与运营操作')
const keyword = ref('')
const activeKeyword = ref('')

function fieldLabel(formKey: 'tip_create' | 'grant_fate_luck' | 'contacts', key: string, fallback: string) {
  const fields = schema.value?.forms?.[formKey] as FieldMetaDto[] | undefined
  return fields?.find((f) => f.key === key)?.label_zh || fallback
}

function sheetColumns(sheetId: string): RecordColumn[] {
  const sheet = schema.value?.sheets?.find((s) => s.sheet_id === sheetId)
  if (!sheet) return []
  return sheet.columns.map((col) => ({
    prop: col.key,
    label: col.label_zh,
    minWidth: 100,
  }))
}

function onSelectionChange(selection: PlayerAccountRow[]) {
  selectedRows.value = selection
}

function labelOf(row: PlayerAccountRow) {
  return row.user_id || `id=${row.id}`
}

function goCharacter(row: PlayerAccountRow) {
  if (!row.character_id) return
  void router.push({
    name: 'player-characters',
    query: {
      user_db_id: String(row.id),
      character_id: String(row.character_id),
      q: row.character_name || undefined,
    },
  })
}

const contactsVisible = ref(false)
const contactsTargets = ref<PlayerAccountRow[]>([])
const contactsForm = reactive({ email: '', phone: '' })

const grantVisible = ref(false)
const grantTargets = ref<PlayerAccountRow[]>([])
const grantForm = reactive({ amount: 100, current: 0 })

const tipCreateVisible = ref(false)
const tipDbId = ref<number | null>(null)
const tipPublicUid = ref('')
const tipForm = reactive({
  paidAt: '',
  channel: '微信',
  orderNo: '',
  amount: 1,
  note: '',
})

const recordVisible = ref(false)
const recordLoading = ref(false)
const recordKind = ref<RecordKind>('tip')
const recordDbId = ref<number | null>(null)
const recordPublicUid = ref('')
const recordRows = ref<Record<string, unknown>[]>([])
const recordTotal = ref(0)
const recordPage = ref(1)
const recordPageSize = ref(20)
const recordWatchCount = ref(0)

const recordTitle = computed(() => {
  const uid = recordPublicUid.value || recordDbId.value || ''
  if (recordKind.value === 'tip') return `打赏记录 · ${uid}`
  if (recordKind.value === 'grant') return `仙缘派发记录 · ${uid}`
  return `广告观看记录 · ${uid}（共 ${recordWatchCount.value} 次）`
})

const recordHint = computed(() => {
  if (recordKind.value === 'ad') {
    return schema.value?.note_zh || '广告系统尚未接入：当前仅可查看；接入后由回调写入。'
  }
  return ''
})

const recordColumns = computed((): RecordColumn[] => {
  if (recordKind.value === 'tip') return sheetColumns('tips')
  if (recordKind.value === 'grant') return sheetColumns('fate_luck_grants')
  return sheetColumns('ad_watches')
})

async function load() {
  loading.value = true
  try {
    const data = await fetchPlayerAccounts({
      q: activeKeyword.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = data.items
    total.value = data.total
    page.value = data.page
    pageSize.value = data.page_size
    selectedRows.value = []
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  activeKeyword.value = keyword.value.trim()
  page.value = 1
  void load()
}

function onReset() {
  keyword.value = ''
  activeKeyword.value = ''
  page.value = 1
  void load()
}

function onPageSizeChange() {
  page.value = 1
  void load()
}

async function batchBan(banned: boolean) {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(
      banned
        ? `确认封禁选中的 ${targets.length} 个账号？封禁后无法登录（提示：无效用户名）。`
        : `确认解封选中的 ${targets.length} 个账号？`,
      banned ? '批量封号' : '批量解封',
      { type: 'warning' },
    )
  } catch {
    return
  }
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await banPlayer(row.id, banned)
      ok += 1
    }
    ElMessage.success(banned ? `已封号 ${ok} 个` : `已解封 ${ok} 个`)
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `操作中断（已成功 ${ok}）`)
    await load()
  } finally {
    acting.value = false
  }
}

async function batchResetPassword() {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  const pwd = resetPasswordPlain.value
  try {
    await ElMessageBox.confirm(
      `确认将选中 ${targets.length} 个账号的密码重置为 ${pwd}？`,
      '批量重置密码',
      { type: 'warning' },
    )
  } catch {
    return
  }
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await resetPlayerPassword(row.id)
      ok += 1
    }
    ElMessage.success(`已重置 ${ok} 个账号密码为 ${pwd}`)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `操作中断（已成功 ${ok}）`)
  } finally {
    acting.value = false
  }
}

async function batchSoftDelete() {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(
      `确认软删选中的 ${targets.length} 个账号？不会物理删除，仅置 is_active=false；登录显示「无效用户名」。`,
      '删除账号',
      { type: 'warning' },
    )
  } catch {
    return
  }
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await softDeletePlayer(row.id)
      ok += 1
    }
    ElMessage.success(`已软删 ${ok} 个账号`)
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `操作中断（已成功 ${ok}）`)
    await load()
  } finally {
    acting.value = false
  }
}

async function batchSetGm(isGm: boolean) {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(
      isGm
        ? `确认将选中 ${targets.length} 个账号设为 GM？（功能暂未开放，仅改标记与 user_id 前缀为 G）`
        : `确认取消选中 ${targets.length} 个账号的 GM 标记？`,
      isGm ? '设为GM' : '取消GM',
      { type: 'warning' },
    )
  } catch {
    return
  }
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await setPlayerGm(row.id, isGm)
      ok += 1
    }
    ElMessage.success(isGm ? `已设 GM ${ok} 个` : `已取消 GM ${ok} 个`)
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `操作中断（已成功 ${ok}）`)
    await load()
  } finally {
    acting.value = false
  }
}

function openContactsBatch() {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  contactsTargets.value = targets
  if (targets.length === 1) {
    contactsForm.email = targets[0].email || ''
    contactsForm.phone = targets[0].phone || ''
  } else {
    contactsForm.email = ''
    contactsForm.phone = ''
  }
  contactsVisible.value = true
}

async function submitContacts() {
  const targets = contactsTargets.value
  if (!targets.length) return
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await updatePlayerContacts(row.id, {
        email: contactsForm.email,
        phone: contactsForm.phone,
      })
      ok += 1
    }
    ElMessage.success(`联系方式已更新（${ok}）`)
    contactsVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `保存中断（已成功 ${ok}）`)
    await load()
  } finally {
    acting.value = false
  }
}

function openGrantBatch() {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  const withChar = targets.filter((r) => r.character_id)
  if (!withChar.length) {
    ElMessage.warning('选中账号均未创角，无法派发仙缘')
    return
  }
  grantTargets.value = targets
  grantForm.current = targets.length === 1 ? targets[0].fate_luck : 0
  grantForm.amount = 100
  grantVisible.value = true
}

async function submitGrant() {
  const targets = grantTargets.value.filter((r) => r.character_id)
  if (!targets.length) return
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await grantPlayerFateLuck(row.id, grantForm.amount)
      ok += 1
    }
    ElMessage.success(`已派发仙缘 +${grantForm.amount} × ${ok}`)
    grantVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `派发中断（已成功 ${ok}）`)
    await load()
  } finally {
    acting.value = false
  }
}

function openTipCreate(row: PlayerAccountRow) {
  tipDbId.value = row.id
  tipPublicUid.value = labelOf(row)
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  tipForm.paidAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  tipForm.channel = tipChannelPresets.value[0] || '微信'
  tipForm.orderNo = ''
  tipForm.amount = 1
  tipForm.note = ''
  tipCreateVisible.value = true
}

async function submitTip() {
  if (tipDbId.value == null) return
  if (!tipForm.paidAt) {
    ElMessage.warning('请选择打赏时间')
    return
  }
  if (!tipForm.channel.trim()) {
    ElMessage.warning('请填写打赏路径')
    return
  }
  if (!tipForm.orderNo.trim()) {
    ElMessage.warning('请填写订单号')
    return
  }
  acting.value = true
  try {
    await createPlayerTip(tipDbId.value, {
      paid_at: tipForm.paidAt,
      channel: tipForm.channel.trim(),
      order_no: tipForm.orderNo.trim(),
      amount: tipForm.amount,
      note: tipForm.note || undefined,
    })
    ElMessage.success('打赏记录已保存')
    tipCreateVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    acting.value = false
  }
}

function openRecords(kind: RecordKind, row: PlayerAccountRow) {
  recordKind.value = kind
  recordDbId.value = row.id
  recordPublicUid.value = labelOf(row)
  recordPage.value = 1
  recordVisible.value = true
  void loadRecords()
}

async function loadRecords() {
  if (recordDbId.value == null) return
  recordLoading.value = true
  try {
    const uid = recordDbId.value
    const params = { page: recordPage.value, page_size: recordPageSize.value }
    if (recordKind.value === 'tip') {
      const data = await fetchPlayerTips(uid, params)
      recordRows.value = data.items as unknown as Record<string, unknown>[]
      recordTotal.value = data.total
    } else if (recordKind.value === 'grant') {
      const data = await fetchFateLuckGrants(uid, params)
      recordRows.value = data.items as unknown as Record<string, unknown>[]
      recordTotal.value = data.total
    } else {
      const data = await fetchAdWatches(uid, params)
      recordRows.value = data.items as unknown as Record<string, unknown>[]
      recordTotal.value = data.total
      recordWatchCount.value = data.watch_count ?? data.total
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载记录失败')
  } finally {
    recordLoading.value = false
  }
}

function onRecordClosed() {
  recordRows.value = []
  recordTotal.value = 0
  recordWatchCount.value = 0
}

onMounted(async () => {
  try {
    schema.value = await fetchPlayerOpsSchema()
    pageSize.value = schema.value.default_page_size
    recordPageSize.value = schema.value.default_page_size
  } catch {
    schema.value = null
  }
  void load()
})
</script>

<style scoped>
.accounts-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  height: 100%;
}
.page-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}
.page-head h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  color: #16352f;
}
.sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: #5b736d;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.batch-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f3f7f5;
  border: 1px solid #c5d4cf;
  border-radius: 2px;
}
.batch-hint {
  font-size: 13px;
  color: #243f39;
  margin-right: 4px;
  min-width: 72px;
}
.gm-note {
  margin-left: 4px;
}
.search {
  width: 260px;
}
.page-size-label {
  font-size: 13px;
  color: #5b736d;
  margin-left: 4px;
}
.grid-wrap {
  background: #fff;
  border: 1px solid #c5d4cf;
  border-radius: 2px;
  overflow: hidden;
}
.navicat-grid {
  --el-table-header-bg-color: #e8efec;
  --el-table-header-text-color: #243f39;
  --el-table-row-hover-bg-color: #f3f8f6;
  font-family: Consolas, 'Cascadia Mono', 'Sarasa Mono SC', monospace;
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0 8px;
}
.dialog-pager {
  margin-top: 12px;
  padding-bottom: 0;
}
.record-hint,
.dialog-hint {
  margin: 0 0 10px;
  font-size: 13px;
  color: #6a7f78;
}
</style>
