<template>
  <div>
    <header class="head">
      <h1>道主运营</h1>
      <p>
        道主榜剔除、道主之争立刻开赛 / 跳过等待 / 重新开放报名。干预须 publisher / admin，写入审计。
      </p>
    </header>

    <el-card shadow="never" class="block">
      <template #header>道主之争赛会</template>
      <el-alert
        v-if="contest"
        type="info"
        :closable="false"
        show-icon
        :title="contestSummaryTitle"
      />
      <el-empty v-else description="暂无赛会" :image-size="40" />

      <el-alert
        class="hints"
        type="warning"
        :closable="false"
        show-icon
        title="收口与再次开赛"
      >
        <p>
          <b>何时收口：</b>{{ hints?.settle_when_zh || defaultSettleHint }}
        </p>
        <p>
          <b>如何再开：</b>{{ hints?.reopen_when_zh || defaultReopenHint }}
        </p>
        <p v-if="hints?.advance_arena_zh">
          <b>跳过等待：</b>{{ hints.advance_arena_zh }}
        </p>
      </el-alert>

      <div class="toolbar">
        <el-button :loading="loadingContest" @click="reloadContest">刷新赛会</el-button>
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
        <el-button
          type="primary"
          plain
          :loading="reopening"
          :disabled="!canReopen"
          @click="onReopen"
        >
          重新开放报名
        </el-button>
      </div>
      <el-text size="small" type="info">
        「立刻开赛」仅报名中可用；「跳过等待」在 RSVP/擂台进行中可用（跳过整备/倒计时/轮间/直播）；「重新开放报名」清空本场便于联调。
      </el-text>
    </el-card>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="剔除后该道无主；进行中的该道挑战会强制结束。"
      style="margin: 16px 0"
    />

    <div class="toolbar">
      <el-button type="primary" :loading="loading" @click="reload">刷新榜单</el-button>
    </div>

    <el-table :data="seats" stripe border v-loading="loading">
      <el-table-column prop="dao_label" label="大道" min-width="120" />
      <el-table-column prop="dao_id" label="ID" width="140" />
      <el-table-column label="道主" min-width="140">
        <template #default="{ row }">
          <span v-if="row.vacant || !row.lord_character_id">虚位以待</span>
          <span v-else>{{ row.lord_name || '—' }}（#{{ row.lord_character_id }}）</span>
        </template>
      </el-table-column>
      <el-table-column label="就任" width="180">
        <template #default="{ row }">
          {{ formatTime(row.claimed_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            :disabled="row.vacant || !row.lord_character_id || removing === row.dao_id"
            :loading="removing === row.dao_id"
            @click="onRemove(row)"
          >
            剔除道主
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * 运营：道主榜剔除 + 赛会立刻开赛 / 跳过等待 / 重新开放报名。
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

const seats = ref<DaoLordSeatRow[]>([])
const loading = ref(false)
const loadingContest = ref(false)
const forcing = ref(false)
const reopening = ref(false)
const advancing = ref(false)
const removing = ref<string | null>(null)
const contest = ref<DaoContestOpsPayload['contest'] | null>(null)
const hints = ref<DaoContestOpsHints | null>(null)

const defaultSettleHint =
  '无人报名→取消；有人报名则 RSVP→擂台各轮结束后 settled。到点或「立刻开赛」关闭报名。'
const defaultReopenHint =
  '须回到报名中：下一业务日自动新开，或点「重新开放报名」清空本场后再「立刻开赛」。'

const canForceStart = computed(
  () => Boolean(hints.value?.can_force_start ?? contest.value?.status === 'registration'),
)
const canReopen = computed(
  () => Boolean(hints.value?.can_reopen ?? Boolean(contest.value)),
)
const canAdvanceArena = computed(
  () =>
    Boolean(
      hints.value?.can_advance_arena ??
        (contest.value?.status === 'rsvp' || contest.value?.status === 'arena'),
    ),
)

const phaseLabelMap: Record<string, string> = {
  rsvp: '入席确认',
  round_countdown: '开赛倒计时',
  round_gap: '轮间休息',
  adjust: '整备',
  playing: '对战演出',
  idle: '已收口',
}

const contestSummaryTitle = computed(() => {
  const c = contest.value
  if (!c) return ''
  const phase = hints.value?.current_phase || c.phase
  const phaseZh = phase ? phaseLabelMap[phase] || phase : '—'
  return `${c.status_label} · 阶段 ${phaseZh} · ${c.eta_label} · 已报名 ${c.total_entrants} 人 · 对阵 ${c.match_count ?? 0}`
})

function formatTime(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

async function reload(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchDaoLords()
    seats.value = data.seats || []
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
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

async function onForceStart(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确认立刻开赛？将关闭报名并进入入席确认（RSVP）与擂台分阶段；有人报名才会打比赛，无人则取消本场。',
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
      '确认跳过当前等待？将立刻结束入席确认/开赛倒计时/整备/轮间/直播倒计时，并推进至对战演出（或收口）。已在演出中时会跳过本场直播进入下一阶段。',
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
      '确认重新开放报名？将清空本场全部报名与对阵战报，并把报名/开打时刻拉到近未来，便于反复联调。道主席位不变。',
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
      `确认剔除「${row.dao_label}」道主「${row.lord_name || row.lord_character_id}」？席位将变为虚位以待。`,
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
    await reload()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '剔除失败')
  } finally {
    removing.value = null
  }
}

onMounted(() => {
  void reload()
  void reloadContest()
})
</script>

<style scoped>
.head h1 {
  margin: 0 0 6px;
}
.head p {
  margin: 0 0 18px;
  color: #5c564c;
}
.toolbar {
  margin: 12px 0;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.block {
  margin-bottom: 8px;
}
.hints {
  margin-top: 12px;
}
.hints p {
  margin: 4px 0;
  line-height: 1.5;
}
</style>
