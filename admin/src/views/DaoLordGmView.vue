<template>
  <div class="gm-page" v-loading="booting">
    <header class="gm-head">
      <div class="gm-head-title">
        <span class="gm-badge">GM</span>
        <div>
          <h1>道主控制台</h1>
          <p>
            运行时干预与配置发布合一 · 已发布 v{{ meta?.published_version ?? 0 }}
            <el-tag v-if="meta?.risk === 'balance'" size="small" type="danger" effect="plain">
              高危域
            </el-tag>
          </p>
        </div>
      </div>
      <div class="gm-head-actions">
        <el-button :loading="loadingAll" @click="reloadAll">刷新全部</el-button>
        <el-button :loading="busy" @click="onValidate">校验草稿</el-button>
        <el-button type="primary" :loading="busy" @click="onSaveDraft">保存草稿</el-button>
        <el-button type="success" :loading="busy" @click="onPublish">发布配置</el-button>
        <el-button type="warning" plain :loading="busy" @click="onRollback">回滚 YAML</el-button>
      </div>
    </header>

    <!-- 上半：左右双栏，避免纵向堆叠过长 -->
    <div class="gm-grid">
      <!-- 左：运行时 GM 操作 -->
      <section class="gm-panel gm-ops">
        <div class="panel-hd">
          <div>
            <span class="panel-kicker">运行时 · 功能操作</span>
            <h2>道主之争 · 现场干预</h2>
          </div>
          <el-button size="small" :loading="loadingContest" @click="reloadContest">刷新赛会</el-button>
        </div>

        <div class="status-strip" v-if="contest">
          <div class="stat">
            <span class="stat-label">状态</span>
            <strong>{{ contest.status_label }}</strong>
          </div>
          <div class="stat">
            <span class="stat-label">阶段</span>
            <strong>{{ phaseZh }}</strong>
          </div>
          <div class="stat">
            <span class="stat-label">ETA</span>
            <strong>{{ contest.eta_label }}</strong>
          </div>
          <div class="stat">
            <span class="stat-label">报名</span>
            <strong>{{ contest.total_entrants }}</strong>
          </div>
          <div class="stat">
            <span class="stat-label">对阵</span>
            <strong>{{ contest.match_count ?? 0 }}</strong>
          </div>
        </div>
        <el-empty v-else description="暂无赛会" :image-size="48" />

        <div class="ops-btns">
          <el-button
            type="danger"
            :loading="forcing"
            :disabled="!canForceStart"
            @click="onForceStart"
          >
            立刻开赛
          </el-button>
          <el-button
            type="warning"
            :loading="advancing"
            :disabled="!canAdvanceArena"
            @click="onAdvanceArena"
          >
            跳过等待 · 进入战斗
          </el-button>
          <el-button type="primary" plain :loading="reopening" :disabled="!canReopen" @click="onReopen">
            重新开放报名
          </el-button>
        </div>

        <el-collapse class="hint-collapse">
          <el-collapse-item title="收口 / 再开 / 跳过说明" name="hints">
            <p><b>何时收口：</b>{{ hints?.settle_when_zh || defaultSettleHint }}</p>
            <p><b>如何再开：</b>{{ hints?.reopen_when_zh || defaultReopenHint }}</p>
            <p v-if="hints?.advance_arena_zh">
              <b>跳过等待：</b>{{ hints.advance_arena_zh }}
            </p>
          </el-collapse-item>
        </el-collapse>

        <div class="panel-hd seats-hd">
          <div>
            <span class="panel-kicker">运行时 · 席位</span>
            <h2>道主榜</h2>
          </div>
          <el-button size="small" :loading="loadingSeats" @click="reloadSeats">刷新榜单</el-button>
        </div>
        <el-table
          :data="seats"
          stripe
          border
          size="small"
          height="100%"
          class="seats-table"
          v-loading="loadingSeats"
        >
          <el-table-column prop="dao_label" label="大道" min-width="100" />
          <el-table-column prop="dao_id" label="ID" width="110" />
          <el-table-column label="道主" min-width="130">
            <template #default="{ row }">
              <span v-if="row.vacant || !row.lord_character_id" class="vacant">虚位以待</span>
              <span v-else>{{ row.lord_name || '—' }}（#{{ row.lord_character_id }}）</span>
            </template>
          </el-table-column>
          <el-table-column label="就任" width="150">
            <template #default="{ row }">{{ formatTime(row.claimed_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                type="danger"
                link
                :disabled="row.vacant || !row.lord_character_id || removing === row.dao_id"
                :loading="removing === row.dao_id"
                @click="onRemove(row)"
              >
                剔除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 右：系统 / 功能配置 -->
      <section class="gm-panel gm-cfg">
        <div class="panel-hd">
          <div>
            <span class="panel-kicker">配置发布</span>
            <h2>规则与赛会参数</h2>
          </div>
          <el-radio-group v-model="cfgLayer" size="small">
            <el-radio-button value="system">系统层面</el-radio-button>
            <el-radio-button value="feature">功能层面</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 系统层面：门槛 / 冷却 / 策略 / 特权 -->
        <div v-show="cfgLayer === 'system'" class="cfg-body">
          <p class="cfg-lead">世界规则：就任门槛、冷却、断线与特权默认值。改完保存草稿并发布。</p>
          <el-form label-width="128px" class="cfg-form" size="small">
            <div class="form-grid">
              <el-form-item label="就任最低道等级">
                <el-input-number v-model="systemForm.claim_min_level" :min="1" :max="99" />
              </el-form-item>
              <el-form-item label="挑战最低道等级">
                <el-input-number v-model="systemForm.challenge_min_level" :min="1" :max="99" />
              </el-form-item>
              <el-form-item label="胜方冷却秒">
                <el-input-number v-model="systemForm.win_seconds" :min="0" :max="86400" />
              </el-form-item>
              <el-form-item label="负方冷却秒">
                <el-input-number v-model="systemForm.lose_seconds" :min="0" :max="86400" />
              </el-form-item>
              <el-form-item label="弃权冷却秒">
                <el-input-number v-model="systemForm.abort_seconds" :min="0" :max="86400" />
              </el-form-item>
              <el-form-item label="断线宽限秒">
                <el-input-number v-model="systemForm.reconnect_grace_seconds" :min="0" :max="600" />
              </el-form-item>
              <el-form-item label="无快照策略">
                <el-select v-model="systemForm.missing_snapshot_policy" style="width: 100%">
                  <el-option label="拒绝 (reject)" value="reject" />
                  <el-option label="弱 NPC (weak_npc)" value="weak_npc" />
                </el-select>
              </el-form-item>
              <el-form-item label="单道同时一战">
                <el-switch v-model="systemForm.single_challenge_per_dao" />
              </el-form-item>
              <el-form-item label="天技特权默认">
                <el-switch v-model="systemForm.heavenly_skill_unlocked" />
              </el-form-item>
              <el-form-item label="秘境特权默认">
                <el-switch v-model="systemForm.can_open_secret_realm" />
              </el-form-item>
            </div>
          </el-form>
        </div>

        <!-- 功能层面：赛会日程 + 擂台节奏 -->
        <div v-show="cfgLayer === 'feature'" class="cfg-body">
          <p class="cfg-lead">道主之争功能：每日报名窗、开打时刻与擂台分阶段节奏。</p>
          <el-form label-width="128px" class="cfg-form" size="small">
            <div class="form-grid">
              <el-form-item label="时区">
                <el-input v-model="featureForm.tz" placeholder="Asia/Shanghai" />
              </el-form-item>
              <el-form-item label="报名开始">
                <el-time-select
                  v-model="featureForm.registration_start"
                  start="00:00"
                  step="00:05"
                  end="23:55"
                  placeholder="HH:MM"
                />
              </el-form-item>
              <el-form-item label="报名结束">
                <el-time-select
                  v-model="featureForm.registration_end"
                  start="00:00"
                  step="00:05"
                  end="23:55"
                  placeholder="HH:MM"
                />
              </el-form-item>
              <el-form-item label="开打时刻">
                <el-time-select
                  v-model="featureForm.fight_at"
                  start="00:00"
                  step="00:05"
                  end="23:55"
                  placeholder="HH:MM"
                />
              </el-form-item>
              <el-form-item label="分阶段擂台">
                <el-switch v-model="featureForm.staging_enabled" />
              </el-form-item>
              <el-form-item label="RSVP 秒">
                <el-input-number v-model="featureForm.rsvp_seconds" :min="5" :max="600" />
              </el-form-item>
              <el-form-item label="首轮倒计时秒">
                <el-input-number
                  v-model="featureForm.arena_first_round_countdown_seconds"
                  :min="5"
                  :max="600"
                />
              </el-form-item>
              <el-form-item label="轮间休息秒">
                <el-input-number v-model="featureForm.round_gap_seconds" :min="0" :max="600" />
              </el-form-item>
              <el-form-item label="整备秒">
                <el-input-number v-model="featureForm.live_adjust_seconds" :min="0" :max="600" />
              </el-form-item>
              <el-form-item label="直播准备秒">
                <el-input-number v-model="featureForm.live_prep_seconds" :min="3" :max="600" />
              </el-form-item>
              <el-form-item label="对战直播秒">
                <el-input-number v-model="featureForm.live_playback_seconds" :min="5" :max="3600" />
              </el-form-item>
              <el-form-item label="DEV 假定在线">
                <el-switch v-model="featureForm.dev_assume_online" />
              </el-form-item>
            </div>
          </el-form>
        </div>

        <div class="cfg-foot">
          <el-button type="primary" size="small" :loading="busy" @click="applyFormsToDraftAndSave">
            写入当前层 → 草稿
          </el-button>
          <el-button size="small" :loading="busy" @click="syncFormsFromDraft">从草稿重载表单</el-button>
          <el-text size="small" type="info">保存后须点右上角「发布配置」才进玩家服</el-text>
        </div>
      </section>
    </div>

    <!-- 下半：字段说明 + 当前生效 合并为分类表格 -->
    <section class="gm-panel gm-ref">
      <div class="panel-hd">
        <div>
          <span class="panel-kicker">对照表</span>
          <h2>字段说明 · 当前生效</h2>
        </div>
        <div class="ref-tools">
          <el-radio-group v-model="refLayer" size="small">
            <el-radio-button value="system">系统层面</el-radio-button>
            <el-radio-button value="feature">功能层面</el-radio-button>
            <el-radio-button value="all">全部</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="fieldFilter"
            clearable
            size="small"
            placeholder="筛选路径 / 中文 / 说明"
            style="width: 220px"
          />
          <el-text size="small" type="info">{{ coverageTitle }}</el-text>
        </div>
      </div>
      <el-table :data="filteredRefRows" border stripe size="small" height="240" class="ref-table">
        <el-table-column label="分类" width="88">
          <template #default="{ row }">
            <el-tag :type="row.layer === 'system' ? 'info' : 'success'" size="small" effect="plain">
              {{ row.layer === 'system' ? '系统' : '功能' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="配置路径" min-width="180" show-overflow-tooltip />
        <el-table-column prop="label_zh" label="中文名" width="130" show-overflow-tooltip />
        <el-table-column prop="help_zh" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="当前生效" min-width="160">
          <template #default="{ row }">
            <code class="eff-val">{{ formatSample(row.effective) }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="value_kind" label="类型" width="80" />
        <el-table-column label="注释" width="72">
          <template #default="{ row }">
            <el-tag :type="row.documented ? 'success' : 'warning'" size="small">
              {{ row.documented ? '是' : '待补' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-collapse class="adv-collapse">
        <el-collapse-item title="高级：JSON 草稿 / YAML 底表 / 发布历史" name="adv">
          <el-tabs v-model="advTab">
            <el-tab-pane label="JSON 草稿" name="draft">
              <el-input v-model="draftText" type="textarea" :rows="12" class="mono" />
            </el-tab-pane>
            <el-tab-pane label="YAML 底表" name="yaml">
              <pre class="json">{{ yamlText }}</pre>
            </el-tab-pane>
            <el-tab-pane label="发布历史" name="revisions">
              <el-table :data="revisions" size="small" border max-height="280">
                <el-table-column prop="version" label="版本" width="80" />
                <el-table-column prop="action" label="动作" width="100" />
                <el-table-column prop="note" label="说明" />
                <el-table-column prop="published_at" label="时间" width="200" />
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-collapse-item>
      </el-collapse>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * GM 风格道主控制台：运行时干预（开赛/剔除）与 dao_lord 配置发布合并为一页。
 * 字段说明与当前生效合并为分类对照表（系统层面 / 功能层面）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  advanceDaoContestArena,
  fetchDaoContest,
  fetchDaoLords,
  forceStartDaoContest,
  reopenDaoContest,
  removeDaoLord,
  type DaoContestOpsHints,
  type DaoContestOpsPayload,
  type DaoLordSeatRow,
} from '../api/ops'
import {
  fetchDomains,
  fetchDomainSchema,
  fetchDraft,
  fetchEffective,
  fetchRevisions,
  publishDomain,
  rollbackDomain,
  saveDraft,
  validateDraft,
} from '../api/config'
import type { DomainEditSchema, DomainSummary, FieldCatalogRow } from '../types/api'

const DOMAIN_ID = 'dao_lord'

const booting = ref(true)
const loadingAll = ref(false)
const loadingSeats = ref(false)
const loadingContest = ref(false)
const busy = ref(false)
const forcing = ref(false)
const reopening = ref(false)
const advancing = ref(false)
const removing = ref<string | null>(null)

const seats = ref<DaoLordSeatRow[]>([])
const contest = ref<DaoContestOpsPayload['contest'] | null>(null)
const hints = ref<DaoContestOpsHints | null>(null)

const meta = ref<DomainSummary | null>(null)
const schema = ref<DomainEditSchema | null>(null)
const draftText = ref('{}')
const effectivePayload = ref<Record<string, unknown>>({})
const yamlText = ref('')
const revisions = ref<Array<Record<string, unknown>>>([])

const cfgLayer = ref<'system' | 'feature'>('feature')
const refLayer = ref<'system' | 'feature' | 'all'>('all')
const fieldFilter = ref('')
const advTab = ref('draft')

const defaultSettleHint =
  '无人报名→取消；有人报名则 RSVP→擂台各轮结束后 settled。到点或「立刻开赛」关闭报名。'
const defaultReopenHint =
  '须回到报名中：下一业务日自动新开，或点「重新开放报名」清空本场后再「立刻开赛」。'

const systemForm = ref({
  claim_min_level: 1,
  challenge_min_level: 1,
  win_seconds: 300,
  lose_seconds: 600,
  abort_seconds: 180,
  reconnect_grace_seconds: 45,
  missing_snapshot_policy: 'reject',
  single_challenge_per_dao: true,
  heavenly_skill_unlocked: false,
  can_open_secret_realm: false,
})

const featureForm = ref({
  tz: 'Asia/Shanghai',
  registration_start: '18:00',
  registration_end: '19:55',
  fight_at: '20:00',
  staging_enabled: true,
  rsvp_seconds: 60,
  arena_first_round_countdown_seconds: 30,
  round_gap_seconds: 30,
  live_adjust_seconds: 60,
  live_prep_seconds: 15,
  live_playback_seconds: 90,
  dev_assume_online: false,
})

const phaseLabelMap: Record<string, string> = {
  rsvp: '入席确认',
  round_countdown: '开赛倒计时',
  round_gap: '轮间休息',
  adjust: '整备',
  playing: '对战演出',
  idle: '已收口',
}

const canForceStart = computed(
  () => Boolean(hints.value?.can_force_start ?? contest.value?.status === 'registration'),
)
const canReopen = computed(() => Boolean(hints.value?.can_reopen ?? Boolean(contest.value)))
const canAdvanceArena = computed(
  () =>
    Boolean(
      hints.value?.can_advance_arena ??
        (contest.value?.status === 'rsvp' || contest.value?.status === 'arena'),
    ),
)

const phaseZh = computed(() => {
  const phase = hints.value?.current_phase || contest.value?.phase
  if (!phase) return '—'
  return phaseLabelMap[phase] || phase
})

const coverageTitle = computed(() => {
  const cov = schema.value?.field_coverage
  if (!cov) return ''
  return `覆盖 ${cov.documented_paths}/${cov.total_paths}（${(cov.coverage_ratio * 100).toFixed(0)}%）`
})

interface RefRow extends FieldCatalogRow {
  layer: 'system' | 'feature'
  effective: unknown
}

/** contest.* 归功能层面；其余道主规则归系统层面 */
function classifyPath(path: string): 'system' | 'feature' {
  if (path === 'contest' || path.startsWith('contest.')) return 'feature'
  return 'system'
}

function getByPath(root: Record<string, unknown>, path: string): unknown {
  const parts = path.split('.')
  let cur: unknown = root
  for (const part of parts) {
    if (cur === null || cur === undefined || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[part]
  }
  return cur
}

const refRows = computed((): RefRow[] => {
  const catalog = schema.value?.field_catalog ?? []
  return catalog.map((row) => ({
    ...row,
    layer: classifyPath(row.path),
    effective: getByPath(effectivePayload.value, row.path),
  }))
})

const filteredRefRows = computed(() => {
  const q = fieldFilter.value.trim().toLowerCase()
  return refRows.value.filter((row) => {
    if (refLayer.value !== 'all' && row.layer !== refLayer.value) return false
    if (!q) return true
    return (
      row.path.toLowerCase().includes(q) ||
      row.label_zh.toLowerCase().includes(q) ||
      row.help_zh.toLowerCase().includes(q)
    )
  })
})

function formatTime(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

function formatSample(sample: unknown): string {
  if (sample === null || sample === undefined) return '—'
  if (typeof sample === 'object') return JSON.stringify(sample)
  return String(sample)
}

function parseDraft(): Record<string, unknown> {
  const raw = JSON.parse(draftText.value || '{}') as unknown
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('草稿须为 JSON object')
  }
  return raw as Record<string, unknown>
}

function syncFormsFromDraft(): void {
  try {
    const draft = parseDraft()
    const base =
      Object.keys(draft).length > 0
        ? draft
        : (effectivePayload.value as Record<string, unknown>)

    const cd =
      base.cooldown && typeof base.cooldown === 'object' && !Array.isArray(base.cooldown)
        ? (base.cooldown as Record<string, unknown>)
        : {}
    const priv =
      base.privileges_default &&
      typeof base.privileges_default === 'object' &&
      !Array.isArray(base.privileges_default)
        ? (base.privileges_default as Record<string, unknown>)
        : {}
    const contestCfg =
      base.contest && typeof base.contest === 'object' && !Array.isArray(base.contest)
        ? (base.contest as Record<string, unknown>)
        : {}

    systemForm.value = {
      claim_min_level: Number(base.claim_min_level ?? 1),
      challenge_min_level: Number(base.challenge_min_level ?? 1),
      win_seconds: Number(cd.win_seconds ?? 300),
      lose_seconds: Number(cd.lose_seconds ?? 600),
      abort_seconds: Number(cd.abort_seconds ?? 180),
      reconnect_grace_seconds: Number(base.reconnect_grace_seconds ?? 45),
      missing_snapshot_policy: String(base.missing_snapshot_policy || 'reject'),
      single_challenge_per_dao: Boolean(base.single_challenge_per_dao ?? true),
      heavenly_skill_unlocked: Boolean(priv.heavenly_skill_unlocked ?? false),
      can_open_secret_realm: Boolean(priv.can_open_secret_realm ?? false),
    }

    featureForm.value = {
      tz: String(contestCfg.tz || 'Asia/Shanghai'),
      registration_start: String(contestCfg.registration_start || '18:00'),
      registration_end: String(contestCfg.registration_end || '19:55'),
      fight_at: String(contestCfg.fight_at || '20:00'),
      staging_enabled: Boolean(contestCfg.staging_enabled ?? true),
      rsvp_seconds: Number(contestCfg.rsvp_seconds ?? 60),
      arena_first_round_countdown_seconds: Number(
        contestCfg.arena_first_round_countdown_seconds ?? 30,
      ),
      round_gap_seconds: Number(contestCfg.round_gap_seconds ?? 30),
      live_adjust_seconds: Number(contestCfg.live_adjust_seconds ?? 60),
      live_prep_seconds: Number(contestCfg.live_prep_seconds ?? 15),
      live_playback_seconds: Number(contestCfg.live_playback_seconds ?? 90),
      dev_assume_online: Boolean(contestCfg.dev_assume_online ?? false),
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '读取草稿失败')
  }
}

/** 将当前可见层表单合并进草稿对象（保留未在表单中的键） */
function mergeFormsIntoDraft(draft: Record<string, unknown>): Record<string, unknown> {
  const next = { ...draft }
  if (cfgLayer.value === 'system') {
    const prevCd =
      next.cooldown && typeof next.cooldown === 'object' && !Array.isArray(next.cooldown)
        ? { ...(next.cooldown as Record<string, unknown>) }
        : {}
    const prevPriv =
      next.privileges_default &&
      typeof next.privileges_default === 'object' &&
      !Array.isArray(next.privileges_default)
        ? { ...(next.privileges_default as Record<string, unknown>) }
        : {}
    next.claim_min_level = systemForm.value.claim_min_level
    next.challenge_min_level = systemForm.value.challenge_min_level
    next.reconnect_grace_seconds = systemForm.value.reconnect_grace_seconds
    next.missing_snapshot_policy = systemForm.value.missing_snapshot_policy
    next.single_challenge_per_dao = systemForm.value.single_challenge_per_dao
    next.cooldown = {
      ...prevCd,
      win_seconds: systemForm.value.win_seconds,
      lose_seconds: systemForm.value.lose_seconds,
      abort_seconds: systemForm.value.abort_seconds,
    }
    next.privileges_default = {
      ...prevPriv,
      heavenly_skill_unlocked: systemForm.value.heavenly_skill_unlocked,
      can_open_secret_realm: systemForm.value.can_open_secret_realm,
    }
  } else {
    const start = String(featureForm.value.registration_start || '').trim()
    const end = String(featureForm.value.registration_end || '').trim()
    const fight = String(featureForm.value.fight_at || '').trim()
    const hhmm = /^\d{1,2}:\d{2}$/
    if (!hhmm.test(start) || !hhmm.test(end) || !hhmm.test(fight)) {
      throw new Error('报名开始/结束与开打时刻须为 HH:MM')
    }
    const prevContest =
      next.contest && typeof next.contest === 'object' && !Array.isArray(next.contest)
        ? { ...(next.contest as Record<string, unknown>) }
        : {}
    next.contest = {
      ...prevContest,
      tz: featureForm.value.tz.trim() || 'Asia/Shanghai',
      registration_start: start,
      registration_end: end,
      fight_at: fight,
      staging_enabled: featureForm.value.staging_enabled,
      rsvp_seconds: featureForm.value.rsvp_seconds,
      arena_first_round_countdown_seconds: featureForm.value.arena_first_round_countdown_seconds,
      round_gap_seconds: featureForm.value.round_gap_seconds,
      live_adjust_seconds: featureForm.value.live_adjust_seconds,
      live_prep_seconds: featureForm.value.live_prep_seconds,
      live_playback_seconds: featureForm.value.live_playback_seconds,
      dev_assume_online: featureForm.value.dev_assume_online,
    }
  }
  return next
}

async function applyFormsToDraftAndSave(): Promise<void> {
  busy.value = true
  try {
    const merged = mergeFormsIntoDraft(parseDraft())
    draftText.value = JSON.stringify(merged, null, 2)
    await saveDraft(DOMAIN_ID, merged)
    ElMessage.success(
      cfgLayer.value === 'system'
        ? '系统层面已写入草稿；请再发布'
        : '功能层面（赛会）已写入草稿；请再发布',
    )
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    busy.value = false
  }
}

async function reloadSeats(): Promise<void> {
  loadingSeats.value = true
  try {
    const data = await fetchDaoLords()
    seats.value = data.seats || []
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '榜单加载失败')
  } finally {
    loadingSeats.value = false
  }
}

async function reloadContest(): Promise<void> {
  loadingContest.value = true
  try {
    const data = await fetchDaoContest()
    contest.value = data.contest
    hints.value = data.ops_hints || null
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '赛会加载失败')
  } finally {
    loadingContest.value = false
  }
}

async function reloadConfig(): Promise<void> {
  const [domains, draft, effective, revs, schemaData] = await Promise.all([
    fetchDomains(),
    fetchDraft(DOMAIN_ID),
    fetchEffective(DOMAIN_ID),
    fetchRevisions(DOMAIN_ID),
    fetchDomainSchema(DOMAIN_ID),
  ])
  meta.value = domains.domains.find((d) => d.domain_id === DOMAIN_ID) || null
  schema.value = schemaData
  draftText.value = JSON.stringify(draft.payload ?? {}, null, 2)
  effectivePayload.value = (effective.payload || {}) as Record<string, unknown>
  yamlText.value = JSON.stringify(effective.yaml_base, null, 2)
  revisions.value = revs.revisions
  syncFormsFromDraft()
}

async function reloadAll(): Promise<void> {
  loadingAll.value = true
  try {
    await Promise.all([reloadSeats(), reloadContest(), reloadConfig()])
  } finally {
    loadingAll.value = false
  }
}

async function onSaveDraft(): Promise<void> {
  busy.value = true
  try {
    await saveDraft(DOMAIN_ID, parseDraft())
    ElMessage.success('草稿已保存')
    await reloadConfig()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    busy.value = false
  }
}

async function onValidate(): Promise<void> {
  busy.value = true
  try {
    const res = await validateDraft(DOMAIN_ID, parseDraft())
    ElMessage.success(String((res as { message?: string }).message || '校验通过'))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '校验失败')
  } finally {
    busy.value = false
  }
}

async function onPublish(): Promise<void> {
  try {
    await ElMessageBox.confirm('高危域：确认发布道主配置到玩家服？', '发布确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  busy.value = true
  try {
    // 先把当前层表单并入草稿，避免只改表单未点「写入」就发布漏改
    const merged = mergeFormsIntoDraft(parseDraft())
    draftText.value = JSON.stringify(merged, null, 2)
    await saveDraft(DOMAIN_ID, merged)
    await publishDomain(DOMAIN_ID, 'gm_console', true)
    ElMessage.success('已发布')
    await reloadConfig()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '发布失败')
  } finally {
    busy.value = false
  }
}

async function onRollback(): Promise<void> {
  try {
    await ElMessageBox.confirm('清除覆盖层，玩家服回到纯 YAML？', '回滚', { type: 'warning' })
  } catch {
    return
  }
  busy.value = true
  try {
    await rollbackDomain(DOMAIN_ID, 0, true)
    ElMessage.success('已回滚到 YAML')
    await reloadConfig()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '回滚失败')
  } finally {
    busy.value = false
  }
}

async function onForceStart(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确认立刻开赛？将关闭报名并进入入席确认（RSVP）与擂台分阶段。',
      '立刻开赛',
      { type: 'warning', confirmButtonText: '确认开赛', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  forcing.value = true
  try {
    const data = await forceStartDaoContest('admin_ops')
    contest.value = data.contest
    hints.value = data.ops_hints || null
    ElMessage.success(data.message || data.contest?.status_label || '已开赛')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '开赛失败')
  } finally {
    forcing.value = false
  }
}

async function onAdvanceArena(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确认跳过当前等待？将立刻推进至对战演出（或收口）。',
      '跳过等待 · 进入战斗',
      { type: 'warning', confirmButtonText: '确认跳过', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  advancing.value = true
  try {
    const data = await advanceDaoContestArena('admin_ops_advance', true)
    contest.value = data.contest
    hints.value = data.ops_hints || null
    ElMessage.success(data.message || '已推进赛程')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '推进失败')
  } finally {
    advancing.value = false
  }
}

async function onReopen(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确认重新开放报名？将清空本场全部报名与对阵战报。道主席位不变。',
      '重新开放报名',
      { type: 'warning', confirmButtonText: '确认重置', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  reopening.value = true
  try {
    const data = await reopenDaoContest('admin_ops_reopen')
    contest.value = data.contest
    hints.value = data.ops_hints || null
    ElMessage.success(data.message || '已重新开放报名')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '重置失败')
  } finally {
    reopening.value = false
  }
}

async function onRemove(row: DaoLordSeatRow): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认剔除「${row.dao_label}」道主「${row.lord_name || row.lord_character_id}」？`,
      '剔除道主',
      { type: 'warning', confirmButtonText: '确认剔除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  let note: string | undefined
  try {
    const { value } = await ElMessageBox.prompt('可选填写运营备注', '剔除备注', {
      confirmButtonText: '提交',
      cancelButtonText: '跳过备注',
      inputPlaceholder: '例如：违规处理',
    })
    note = value
  } catch {
    note = undefined
  }
  removing.value = row.dao_id
  try {
    const data = await removeDaoLord(row.dao_id, note)
    ElMessage.success(data.message || '已剔除')
    await reloadSeats()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '剔除失败')
  } finally {
    removing.value = null
  }
}

onMounted(async () => {
  try {
    await reloadAll()
  } finally {
    booting.value = false
  }
})
</script>

<style scoped>
.gm-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: calc(100vh - 48px);
}

.gm-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.gm-head-title {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.gm-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: linear-gradient(145deg, #1a4a40, #0f2e28);
  color: #b8e6d8;
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.gm-head h1 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #14332c;
}

.gm-head p {
  margin: 0;
  color: #5c564c;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gm-head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.gm-grid {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 14px;
  align-items: stretch;
  min-height: 0;
}

.gm-panel {
  background: #fff;
  border: 1px solid #d9e4df;
  border-radius: 12px;
  padding: 14px 16px 16px;
  box-shadow: 0 1px 0 rgba(20, 51, 44, 0.04);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.gm-ops {
  max-height: min(62vh, 640px);
}

.panel-hd {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}

.panel-kicker {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6a8a80;
  margin-bottom: 2px;
}

.panel-hd h2 {
  margin: 0;
  font-size: 16px;
  color: #1a3530;
}

.status-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.stat {
  background: linear-gradient(180deg, #f3f8f6, #eaf3ef);
  border: 1px solid #d5e4de;
  border-radius: 8px;
  padding: 8px 10px;
  min-width: 0;
}

.stat-label {
  display: block;
  font-size: 11px;
  color: #6a7f78;
  margin-bottom: 2px;
}

.stat strong {
  font-size: 13px;
  color: #14332c;
  word-break: break-all;
}

.ops-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.hint-collapse {
  margin-bottom: 8px;
  border: none;
}

.hint-collapse :deep(.el-collapse-item__header) {
  height: 36px;
  font-size: 12px;
  color: #6a7f78;
  border: none;
  background: transparent;
}

.hint-collapse :deep(.el-collapse-item__wrap) {
  border: none;
}

.hint-collapse p {
  margin: 4px 0;
  font-size: 12px;
  line-height: 1.5;
  color: #4a5c56;
}

.seats-hd {
  margin-top: 4px;
}

.seats-table {
  flex: 1 1 auto;
  min-height: 180px;
}

.vacant {
  color: #8a9490;
}

.cfg-lead {
  margin: 0 0 10px;
  font-size: 12px;
  color: #5c6b66;
}

.cfg-body {
  flex: 1 1 auto;
  overflow: auto;
  min-height: 0;
  padding-right: 4px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 8px;
}

.cfg-form :deep(.el-form-item) {
  margin-bottom: 10px;
}

.cfg-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px solid #e6eeea;
}

.gm-ref {
  flex: 0 0 auto;
}

.ref-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

.eff-val {
  font-size: 12px;
  color: #1f4d42;
  word-break: break-all;
}

.adv-collapse {
  margin-top: 10px;
  border: none;
}

.adv-collapse :deep(.el-collapse-item__header) {
  border: none;
  font-size: 13px;
  color: #4a635c;
}

.adv-collapse :deep(.el-collapse-item__wrap) {
  border: none;
}

.mono :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.json {
  margin: 0;
  padding: 12px;
  background: #0f1f1c;
  color: #d7ebe6;
  border-radius: 8px;
  font-size: 12px;
  max-height: 280px;
  overflow: auto;
}

@media (max-width: 1100px) {
  .gm-grid {
    grid-template-columns: 1fr;
  }

  .gm-ops {
    max-height: none;
  }

  .status-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
