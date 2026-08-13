<script setup lang="ts">
/**
 * 双修工作台：邀约→宽衣→开始→结算；双修台 / 时长榜。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useCharacterStore } from '../../stores/character'
import { useDualCultivationStore } from '../../stores/dualCultivation'
import type {
  DualBondKind,
  DualGender,
  DualInviteTarget,
} from '../../types/dualCultivation'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const dualStore = useDualCultivationStore()
const characterStore = useCharacterStore()

const busy = ref(false)
const techniqueId = ref('')
const genderPick = ref<DualGender>('male')
const tab = ref<'session' | 'ranks'>('session')
const activeBoard = ref('duration_total')
const nowMs = ref(Date.now())

const pickDialogVisible = ref(false)
const pickKind = ref<DualBondKind>('companion')
const selectedTarget = ref<DualInviteTarget | null>(null)

let pollTimer: number | null = null
let countdownTimer: number | null = null

const myCharacterId = computed(() => characterStore.character?.id ?? null)

const boardKeys = computed(() =>
  dualStore.ranks ? Object.keys(dualStore.ranks.boards) : [],
)

const currentBoard = computed(() => {
  if (!dualStore.ranks) return null
  return dualStore.ranks.boards[activeBoard.value] || null
})

const pickDialogTitle = computed(() =>
  pickKind.value === 'vessel' ? '选择炉鼎' : '选择道侣',
)

const pickList = computed((): DualInviteTarget[] => {
  const targets = dualStore.inviteTargets
  if (!targets) return []
  return pickKind.value === 'vessel' ? targets.vessels : targets.companions
})

const session = computed(() => dualStore.session)

const isInvitee = computed(() => {
  const s = session.value
  const cid = myCharacterId.value
  if (!s || !cid) return false
  return Number(s.invitee.character_id) === Number(cid)
})

const isInviter = computed(() => {
  const s = session.value
  const cid = myCharacterId.value
  if (!s || !cid) return false
  return Number(s.inviter.character_id) === Number(cid)
})

const effectiveStatus = computed(() => {
  const st = session.value?.status || ''
  return st === 'confirmed' ? 'accepted' : st
})

const canAcceptInvite = computed(
  () => effectiveStatus.value === 'inviting' && isInvitee.value,
)

const canRejectOrCancelInvite = computed(() => {
  if (effectiveStatus.value !== 'inviting') return false
  if (isInvitee.value && session.value?.bond_kind === 'vessel') return false
  return isInvitee.value || isInviter.value
})

const canUndress = computed(
  () =>
    Boolean(session.value?.can_undress) ||
    (effectiveStatus.value === 'accepted' && isInvitee.value),
)

const canStart = computed(
  () =>
    Boolean(session.value?.can_start) ||
    (session.value?.status === 'undressed' && isInviter.value),
)

const inviteCountdown = computed(() => {
  const exp = session.value?.invite_expire_at
  if (!exp || effectiveStatus.value !== 'inviting') return ''
  const left = Math.max(0, Math.ceil((new Date(exp).getTime() - nowMs.value) / 1000))
  return left > 0 ? `邀约剩余 ${left}s` : '邀约即将超时'
})

const undressCountdown = computed(() => {
  const exp = session.value?.undress_expire_at
  if (!exp || effectiveStatus.value !== 'accepted') return ''
  const left = Math.max(0, Math.ceil((new Date(exp).getTime() - nowMs.value) / 1000))
  return left > 0 ? `宽衣剩余 ${left}s` : '宽衣即将超时'
})

const settleSummary = computed(
  () => session.value?.settle_summary ?? dualStore.lastSummary,
)

function startPollers(): void {
  stopPollers()
  if (!dualStore.hasActiveSession) return
  pollTimer = window.setInterval(() => {
    void dualStore.refreshMe()
  }, 5000)
  countdownTimer = window.setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
}

function stopPollers(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
  if (countdownTimer !== null) {
    window.clearInterval(countdownTimer)
    countdownTimer = null
  }
}

async function run(fn: () => Promise<string | null>, okHint?: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await fn()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(okHint || dualStore.lastMessage || '完成')
    emit('log', dualStore.lastMessage || okHint || '完成', 'success')
  } finally {
    busy.value = false
  }
}

function openPickDialog(kind: DualBondKind): void {
  pickKind.value = kind
  pickDialogVisible.value = true
}

function pickTarget(item: DualInviteTarget): void {
  selectedTarget.value = item
  pickDialogVisible.value = false
  ElMessage.success(`双修对象：${item.peer_name}`)
}

function clearTarget(): void {
  selectedTarget.value = null
}

onMounted(async () => {
  await dualStore.refreshMe()
  if (dualStore.techniques.length && !techniqueId.value) {
    techniqueId.value = dualStore.techniques[0].technique_id
  }
  await dualStore.loadRanks()
  if (dualStore.ranks?.primary_board) {
    activeBoard.value = dualStore.ranks.primary_board
  } else if (boardKeys.value.length) {
    activeBoard.value = boardKeys.value[0]
  }
  startPollers()
  emit('log', '双修工作台已就绪', 'info')
})

onUnmounted(() => {
  stopPollers()
  const s = session.value
  const cid = myCharacterId.value
  // 道侣：宽衣阶段离开双修台 = 终态取消；炉鼎宽衣可超时自动点击，离开不取消
  if (
    s &&
    cid &&
    s.bond_kind !== 'vessel' &&
    (effectiveStatus.value === 'accepted' || s.status === 'confirmed') &&
    Number(s.invitee.character_id) === Number(cid)
  ) {
    void dualStore.cancel(s.session_id)
  }
})

watch(
  () => dualStore.techniques,
  (list) => {
    if (list.length && !techniqueId.value) {
      techniqueId.value = list[0].technique_id
    }
  },
)

watch(
  () => dualStore.hasActiveSession,
  () => startPollers(),
)

/** 倒计时归零时立刻拉 me，触发服务端惰性过期（道侣超时取消 / 炉鼎自动推进） */
watch(
  () => [inviteCountdown.value, undressCountdown.value] as const,
  ([inviteLeft, undressLeft]) => {
    if (
      inviteLeft === '邀约即将超时' ||
      undressLeft === '宽衣即将超时'
    ) {
      void dualStore.refreshMe()
    }
  },
)
</script>

<template>
  <div class="dual-panel">
    <div class="sub-nav">
      <el-button
        size="small"
        :type="tab === 'session' ? 'primary' : 'default'"
        @click="tab = 'session'"
      >
        双修台
      </el-button>
      <el-button
        size="small"
        :type="tab === 'ranks' ? 'primary' : 'default'"
        @click="tab = 'ranks'"
      >
        时长榜
      </el-button>
    </div>

    <el-card v-if="dualStore.me?.needs_gender" shadow="never">
      <template #header>
        <el-text tag="b">补全道途阴阳</el-text>
      </template>
      <el-text size="small" type="info" class="hint">
        进双修与上榜前须选定性别；选定后不可自行更改。
      </el-text>
      <el-radio-group v-model="genderPick" size="small">
        <el-radio-button value="male">乾道（男）</el-radio-button>
        <el-radio-button value="female">坤道（女）</el-radio-button>
      </el-radio-group>
      <el-button
        type="primary"
        size="small"
        class="mt"
        :loading="busy"
        @click="run(() => dualStore.chooseGender(genderPick), '阴阳已定')"
      >
        确认
      </el-button>
    </el-card>

    <template v-else-if="tab === 'session'">
      <el-card shadow="never">
        <template #header>
          <el-text tag="b">当前阴阳</el-text>
        </template>
        <el-text>{{ dualStore.me?.gender_label_zh || '—' }}</el-text>
      </el-card>

      <el-card v-if="session" shadow="never" class="mt">
        <template #header>
          <el-text tag="b">进行中双修</el-text>
        </template>
        <el-text>
          {{ session.technique_label }} ·
          {{ session.status_label_zh || session.status }}
          <el-tag v-if="session.auto_forced" size="small" type="warning" class="ml">
            自动推进
          </el-tag>
        </el-text>
        <el-text size="small" type="info" class="hint">
          {{ session.inviter.name }} ↔ {{ session.invitee.name }}
          ·
          {{ session.bond_kind === 'vessel' ? '炉鼎' : '道侣' }}
        </el-text>
        <el-text v-if="inviteCountdown" size="small" type="warning" class="hint">
          {{ inviteCountdown }}
        </el-text>
        <el-text v-if="undressCountdown" size="small" type="warning" class="hint">
          {{ undressCountdown }}
        </el-text>

        <div v-if="session.status === 'settled' && settleSummary" class="summary-box">
          <el-text tag="b">本场摘要</el-text>
          <el-text size="small" class="hint">
            {{ settleSummary.log_zh || '双修已完成' }}
          </el-text>
          <el-text size="small">
            抽插 {{ settleSummary.insert_count ?? '—' }} 次 · 时长
            {{ settleSummary.duration_sec ?? '—' }} 秒（按秒上榜）
          </el-text>
        </div>

        <div class="actions">
          <el-button
            v-if="canAcceptInvite"
            size="small"
            type="primary"
            :loading="busy"
            @click="run(() => dualStore.confirm(session!.session_id))"
          >
            接受邀约
          </el-button>
          <el-button
            v-if="canUndress"
            size="small"
            type="primary"
            :loading="busy"
            @click="run(() => dualStore.undress(session!.session_id), '已宽衣')"
          >
            宽衣解带
          </el-button>
          <el-text
            v-if="effectiveStatus === 'accepted' && isInvitee"
            size="small"
            type="info"
            class="hint"
          >
            {{
              session.bond_kind === 'vessel'
                ? '请宽衣解带；超时将自动宽衣'
                : '请宽衣解带；超时或离开本页将取消'
            }}
          </el-text>
          <el-text
            v-if="effectiveStatus === 'accepted' && isInviter"
            size="small"
            type="info"
          >
            对方已接受，等待宽衣解带…
          </el-text>
          <el-text
            v-if="session.status === 'undressed' && isInviter"
            size="small"
            type="success"
          >
            对方已宽衣，可点击开始
          </el-text>
          <el-button
            v-if="canStart"
            size="small"
            type="success"
            :loading="busy"
            @click="run(() => dualStore.start(session!.session_id))"
          >
            开始
          </el-button>
          <el-text
            v-if="session.status === 'undressed' && isInvitee"
            size="small"
            type="info"
          >
            已宽衣，等待对方开始
          </el-text>
          <el-button
            v-if="canRejectOrCancelInvite"
            size="small"
            :loading="busy"
            @click="run(() => dualStore.cancel(session!.session_id))"
          >
            {{ isInvitee ? '拒绝' : '取消' }}
          </el-button>
          <el-button
            v-else-if="
              ['accepted', 'undressed', 'confirmed'].includes(session.status) &&
              (isInviter || (isInvitee && session.bond_kind !== 'vessel'))
            "
            size="small"
            :loading="busy"
            @click="run(() => dualStore.cancel(session!.session_id))"
          >
            取消
          </el-button>
        </div>
      </el-card>

      <el-card v-else-if="settleSummary" shadow="never" class="mt">
        <template #header>
          <el-text tag="b">上一场摘要</el-text>
        </template>
        <el-text size="small" class="hint">
          {{ settleSummary.log_zh || '双修已完成' }}
        </el-text>
        <el-text size="small">
          抽插 {{ settleSummary.insert_count ?? '—' }} 次 · 时长
          {{ settleSummary.duration_sec ?? '—' }} 秒（按秒上榜）
        </el-text>
      </el-card>

      <div v-if="!session" class="invite-stage mt">
        <div class="invite-main">
          <div class="invite-title-row">
            <el-text tag="b">发起双修</el-text>
            <el-text size="small" type="info">
              {{ dualStore.inviteTargets?.hint_zh || '仅可从道侣或炉鼎中选择' }}
            </el-text>
          </div>
          <label class="field-label">功法</label>
          <el-select v-model="techniqueId" size="small" placeholder="选择功法" class="full">
            <el-option
              v-for="t in dualStore.techniques"
              :key="t.technique_id"
              :label="`${t.label}（${t.mode_label_zh || (t.mode === 'mutual_gain' ? '双增' : t.mode === 'extract' ? '索取' : '传功')}）`"
              :value="t.technique_id"
            />
          </el-select>
          <label class="field-label">双修对象</label>
          <div class="target-box">
            <div class="target-row">
              <el-text v-if="selectedTarget" tag="b">
                {{ selectedTarget.peer_name }}
                <el-tag size="small" class="ml">
                  {{ selectedTarget.bond_kind === 'vessel' ? '炉鼎' : '道侣' }}
                </el-tag>
              </el-text>
              <el-text v-else type="info" size="small">请从右侧快捷选择</el-text>
              <el-button
                v-if="selectedTarget"
                size="small"
                text
                type="danger"
                @click="clearTarget"
              >
                清除
              </el-button>
            </div>
          </div>
          <el-button
            type="primary"
            size="small"
            class="mt"
            :loading="busy"
            :disabled="!techniqueId || !selectedTarget"
            @click="
              run(() =>
                dualStore.invite(
                  techniqueId,
                  selectedTarget!.peer_character_id,
                  (selectedTarget!.bond_kind as DualBondKind) || 'companion',
                ),
              )
            "
          >
            发送邀约
          </el-button>
        </div>
        <aside class="invite-side">
          <el-button size="small" @click="openPickDialog('companion')">道侣</el-button>
          <el-button size="small" @click="openPickDialog('vessel')">炉鼎</el-button>
        </aside>
      </div>
    </template>

    <el-card v-else shadow="never">
      <template #header>
        <el-text tag="b">时长榜</el-text>
      </template>
      <el-text size="small" type="info" class="hint">
        主榜为累计双修秒数前 100；角色位分榜按主动/承纳时长统计。
      </el-text>
      <el-radio-group v-model="activeBoard" size="small" class="boards">
        <el-radio-button v-for="k in boardKeys" :key="k" :value="k">
          {{ dualStore.ranks?.boards[k]?.label_zh || k }}
        </el-radio-button>
      </el-radio-group>
      <el-text v-if="currentBoard" size="small" type="info" class="hint">
        本人：第 {{ currentBoard.my_rank ?? '—' }} 名 ·
        {{ currentBoard.my_score }}{{ currentBoard.score_unit_zh || '秒' }}（门槛
        {{ currentBoard.min_score }}）
      </el-text>
      <el-table
        v-if="currentBoard"
        :data="currentBoard.entries"
        size="small"
        empty-text="尚无上榜"
      >
        <el-table-column prop="rank" label="名次" width="70" />
        <el-table-column prop="name" label="道号" />
        <el-table-column prop="score" :label="`时长(${currentBoard.score_unit_zh || '秒'})`" width="110" />
      </el-table>
      <el-button size="small" class="mt" @click="dualStore.loadRanks()">刷新</el-button>
    </el-card>

    <el-dialog
      v-model="pickDialogVisible"
      :title="pickDialogTitle"
      width="420px"
      append-to-body
      destroy-on-close
    >
      <el-empty
        v-if="!pickList.length"
        :description="
          pickKind === 'vessel'
            ? '暂无炉鼎（玩法口子已开，暂不可直接邀请添加）'
            : '暂无道侣，请先在道友页结交道侣'
        "
        :image-size="48"
      />
      <div v-else class="pick-grid">
        <button
          v-for="item in pickList"
          :key="item.bond_id"
          type="button"
          class="pick-card"
          @click="pickTarget(item)"
        >
          <el-text tag="b">{{ item.peer_name }}</el-text>
          <el-text size="small" type="info">
            {{ item.online ? '在线' : '离线' }}
            <template v-if="item.peer_major_realm_name">
              · {{ item.peer_major_realm_name }}
            </template>
          </el-text>
        </button>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.dual-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.sub-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.hint {
  display: block;
  margin: 0.35rem 0 0.6rem;
}
.mt {
  margin-top: 0.5rem;
}
.ml {
  margin-left: 0.35rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  margin-top: 0.6rem;
}
.summary-box {
  margin-top: 0.5rem;
  padding: 0.4rem 0.5rem;
  background: var(--el-fill-color-light);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.boards {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}
.invite-stage {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.75rem;
  align-items: start;
  padding: 0.75rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-bg-color);
}
.invite-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}
.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--el-text-color-secondary);
  margin: 0.35rem 0 0.2rem;
}
.invite-main {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}
.invite-side {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  align-items: stretch;
  min-width: 4.5rem;
}
.invite-side :deep(.el-button) {
  margin: 0;
  width: 100%;
}
.full {
  width: 100%;
}
.target-box {
  padding: 0.45rem 0.55rem;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.target-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;
}
.pick-card {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  align-items: flex-start;
  text-align: left;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}
.pick-card:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-fill-color-light);
}
@media (max-width: 640px) {
  .invite-stage {
    grid-template-columns: 1fr;
  }
  .invite-side {
    flex-direction: row;
    flex-wrap: wrap;
  }
  .invite-side :deep(.el-button) {
    width: auto;
  }
}
</style>
