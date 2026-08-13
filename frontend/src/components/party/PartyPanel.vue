<script setup lang="ts">
/**
 * 队伍 / 团队面板：建队、邮件式邀请、倒计时应答、转团队、踢人。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchPartyInviteOptions } from '../../api/chat'
import { useCharacterStore } from '../../stores/character'
import { useChatStore } from '../../stores/chat'
import type { PartyInviteItem, PartyMemberItem } from '../../types/chat'
import { parseUtcMs } from '../../utils/parseUtc'

type PickKind = 'friend' | 'sect' | 'mentor'

interface PickItem {
  character_id: number
  name: string
  online?: boolean
  rank_label_zh?: string
  role?: string
}

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const characterStore = useCharacterStore()

const busy = ref(false)
const inviteName = ref('')
const expandedId = ref<number | null>(null)
const pickOpen = ref(false)
const pickKind = ref<PickKind>('friend')
const pickList = ref<PickItem[]>([])
const pickLoading = ref(false)
const tickNow = ref(Date.now())
let tickTimer: number | null = null

const myId = computed(() => Number(characterStore.character?.id || 0))
const party = computed(() => chatStore.party)
const isLeader = computed(() => {
  const p = party.value
  if (!p || !myId.value) return false
  return Number(p.leader_character_id) === myId.value
})
const isTeam = computed(() => party.value?.kind === 'team')
const memberCapLabel = computed(() => {
  const p = party.value
  if (!p) return ''
  return `${p.member_count ?? p.members?.length ?? 0} / ${p.max_members ?? (isTeam.value ? 40 : 5)}`
})
const leaderLabel = computed(() => party.value?.leader_label_zh || (isTeam.value ? '团长' : '队长'))
const kindLabel = computed(() => party.value?.kind_label_zh || (isTeam.value ? '团队' : '队伍'))

const pickTitle = computed(() => {
  if (pickKind.value === 'friend') return '选择道友'
  if (pickKind.value === 'sect') return '选择同门'
  return '选择师徒'
})

onMounted(async () => {
  tickTimer = window.setInterval(() => {
    tickNow.value = Date.now()
  }, 1000)
  const err = await chatStore.refreshPartyMe()
  if (err) emit('log', err, 'warning')
  const q = route.query.invite
  if (typeof q === 'string' && q.trim()) {
    inviteName.value = q.trim()
  }
})

onUnmounted(() => {
  if (tickTimer != null) {
    window.clearInterval(tickTimer)
    tickTimer = null
  }
})

watch(
  () => route.query.invite,
  (q) => {
    if (typeof q === 'string' && q.trim()) inviteName.value = q.trim()
  },
)

watch(
  () => [chatStore.pendingInvites.length, chatStore.outgoingInvites.length],
  () => {
    // 倒计时归零后刷新，清理过期邀请
    const all = [...chatStore.pendingInvites, ...chatStore.outgoingInvites]
    const anyExpired = all.some((inv) => remainSec(inv) <= 0 && inv.expires_at)
    if (anyExpired) void chatStore.refreshPartyMe()
  },
)

function remainSec(inv: PartyInviteItem): number {
  if (!inv.expires_at) return 999
  const end = parseUtcMs(inv.expires_at)
  if (!Number.isFinite(end)) return 999
  return Math.max(0, Math.ceil((end - tickNow.value) / 1000))
}

function formatCountdown(inv: PartyInviteItem): string {
  const s = remainSec(inv)
  if (!inv.expires_at) return '—'
  if (s <= 0) return '已超时'
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}:${String(r).padStart(2, '0')}` : `${r}s`
}

async function run(fn: () => Promise<string | null>, okHint: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await fn()
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(okHint)
    emit('log', okHint, 'success')
  } finally {
    busy.value = false
  }
}

function onCreate(): Promise<void> {
  return run(() => chatStore.createParty(), '队伍已创建')
}

function onInvite(): Promise<void> {
  return run(() => chatStore.inviteToParty(inviteName.value), '邀请已发出')
}

function onLeave(): Promise<void> {
  return run(() => chatStore.leaveParty(), '已离队')
}

const canConvertToParty = computed(() => {
  const p = party.value
  if (!p || !isLeader.value || !isTeam.value) return false
  const n = Number(p.member_count ?? p.members?.length ?? 0)
  const partyCap = Number(chatStore.partyLimits?.party_max_members ?? 5)
  return n <= partyCap
})

function onConvert(): Promise<void> {
  return run(() => chatStore.convertToTeam(), '已转换为团队')
}

function onConvertToParty(): Promise<void> {
  return run(() => chatStore.convertToParty(), '已转回队伍')
}

function onKick(m: PartyMemberItem): Promise<void> {
  return run(
    () =>
      chatStore.kickFromParty({
        peer_character_id: m.character_id,
        peer_name: m.name,
      }),
    `已将「${m.name}」移出${kindLabel.value}`,
  )
}

function onAccept(id: number): Promise<void> {
  return run(() => chatStore.acceptPartyInvite(id), '已加入队伍')
}

function onReject(id: number): Promise<void> {
  return run(() => chatStore.rejectPartyInvite(id), '已拒绝邀请')
}

async function openPickDialog(kind: PickKind): Promise<void> {
  pickKind.value = kind
  pickOpen.value = true
  pickLoading.value = true
  try {
    const envelope = await fetchPartyInviteOptions()
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '加载可选名单失败')
      pickList.value = []
      return
    }
    const data = envelope.data
    if (kind === 'friend') pickList.value = data.friends || []
    else if (kind === 'sect') pickList.value = data.sect_members || []
    else pickList.value = data.mentor_peers || []
  } finally {
    pickLoading.value = false
  }
}

const OFFLINE_TIP = '道友不在本界'

function pickTarget(item: PickItem): void {
  if (!item.online) {
    ElMessage.warning(OFFLINE_TIP)
    emit('log', `「${item.name}」${OFFLINE_TIP}`, 'warning')
    return
  }
  inviteName.value = item.name
  pickOpen.value = false
}

function toggleExpand(id: number): void {
  expandedId.value = expandedId.value === id ? null : id
}

function techLine(m: PartyMemberItem): string {
  const list = m.technique_summary || []
  if (!list.length) return '无'
  return list
    .map((t) => `${t.name || t.id || '功法'}${t.level != null ? ` Lv${t.level}` : ''}`)
    .join('、')
}

function mentorRoleLabel(role?: string): string {
  if (role === 'master') return '师傅'
  if (role === 'disciple') return '弟子'
  return ''
}
</script>

<template>
  <el-card shadow="never" class="party-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">{{ kindLabel }}</el-text>
        <el-button size="small" @click="router.push('/social?mode=friends')">道友</el-button>
      </div>
    </template>

    <el-divider content-position="left">待处理邀请</el-divider>
    <el-empty
      v-if="!chatStore.pendingInvites.length"
      description="暂无组队邀请"
      :image-size="40"
    />
    <div v-else class="list">
      <div
        v-for="inv in chatStore.pendingInvites"
        :key="inv.id"
        class="row invite-row-card"
      >
        <div class="invite-main">
          <el-text>「{{ inv.inviter_name }}」邀请你入队</el-text>
          <el-tag
            size="small"
            :type="remainSec(inv) <= 10 ? 'danger' : 'info'"
          >
            {{ formatCountdown(inv) }}
          </el-tag>
        </div>
        <div class="actions">
          <el-button
            size="small"
            type="success"
            :loading="busy"
            :disabled="remainSec(inv) <= 0"
            @click="onAccept(inv.id)"
          >
            接受
          </el-button>
          <el-button
            size="small"
            type="danger"
            :loading="busy"
            :disabled="remainSec(inv) <= 0"
            @click="onReject(inv.id)"
          >
            拒绝
          </el-button>
        </div>
      </div>
    </div>

    <template v-if="chatStore.outgoingInvites.length">
      <el-divider content-position="left">已发出邀请</el-divider>
      <div class="list">
        <div
          v-for="inv in chatStore.outgoingInvites"
          :key="`out-${inv.id}`"
          class="row invite-row-card"
        >
          <el-text size="small">等待「{{ inv.invitee_name || inv.invitee_id }}」确认</el-text>
          <el-tag size="small" :type="remainSec(inv) <= 10 ? 'danger' : 'warning'">
            {{ formatCountdown(inv) }}
          </el-tag>
        </div>
      </div>
    </template>

    <template v-if="!party">
      <el-divider content-position="left">创建队伍</el-divider>
      <el-text size="small" type="info" class="hint">
        队伍最多 5 人；超过需转换为团队（最多 40 人）。邀请 1 分钟内未处理视为拒绝。
      </el-text>
      <el-button type="primary" size="small" :loading="busy" @click="onCreate">
        创建队伍
      </el-button>
    </template>

    <template v-else>
      <el-divider content-position="left">
        我的{{ kindLabel }} · #{{ party.id }}
        <el-tag v-if="isLeader" size="small" type="warning" class="leader-tag">
          {{ leaderLabel }}
        </el-tag>
        <el-tag size="small" type="info" class="leader-tag">{{ memberCapLabel }}</el-tag>
      </el-divider>

      <div class="toolbar">
        <el-button
          v-if="isLeader && !isTeam"
          size="small"
          type="warning"
          plain
          :loading="busy"
          @click="onConvert"
        >
          转换为团队
        </el-button>
        <el-button
          v-if="canConvertToParty"
          size="small"
          type="primary"
          plain
          :loading="busy"
          @click="onConvertToParty"
        >
          转回队伍
        </el-button>
        <el-button size="small" type="danger" plain :loading="busy" @click="onLeave">
          离队
        </el-button>
      </div>

      <el-alert
        v-if="isTeam && party.restrictions?.summary_zh"
        :title="party.restrictions.summary_zh"
        type="warning"
        :closable="false"
        show-icon
        class="team-alert"
      />

      <div v-if="isLeader" class="invite-stage">
        <div class="invite-main">
          <el-text size="small" type="info" class="invite-hint">
            {{ leaderLabel }}邀请（须道友/同门/师徒且对方在线；1 分钟超时）
          </el-text>
          <label class="field-label">道号</label>
          <div class="invite-row">
            <el-input
              v-model="inviteName"
              size="small"
              placeholder="输入道号，或右侧快捷选择"
              clearable
              @keyup.enter="onInvite"
            />
            <el-button type="primary" size="small" :loading="busy" @click="onInvite">
              邀请
            </el-button>
          </div>
        </div>
        <aside class="invite-side">
          <el-button size="small" @click="openPickDialog('friend')">道友</el-button>
          <el-button size="small" @click="openPickDialog('sect')">宗门</el-button>
          <el-button size="small" @click="openPickDialog('mentor')">师徒</el-button>
        </aside>
      </div>

      <div class="list members">
        <div
          v-for="m in party.members"
          :key="m.character_id"
          class="member-card"
        >
          <div class="member-top" @click="toggleExpand(m.character_id)">
            <span class="presence-dot" :class="{ on: m.online }" />
            <el-text tag="b">{{ m.name }}</el-text>
            <el-tag v-if="m.is_leader" size="small" type="warning">{{ leaderLabel }}</el-tag>
            <el-tag size="small" type="info">
              {{ m.major_realm_name || m.major_realm || '—' }}
            </el-tag>
            <el-text size="small" type="info">{{ m.status_name || m.status || '' }}</el-text>
            <el-button
              v-if="isLeader && !m.is_leader"
              size="small"
              type="danger"
              plain
              :loading="busy"
              @click.stop="onKick(m)"
            >
              踢出
            </el-button>
          </div>
          <div v-if="expandedId === m.character_id" class="member-detail">
            <div>修为：{{ m.cultivation_points ?? 0 }}</div>
            <div>攻 / 血：{{ m.base_atk ?? 0 }} / {{ m.base_hp ?? 0 }}</div>
            <div>功法：{{ techLine(m) }}</div>
            <div>
              体质装备：
              {{
                m.constitution_equipped?.length
                  ? m.constitution_equipped.join('、')
                  : '无'
              }}
            </div>
            <div>状态：{{ m.online ? '在线' : '离线' }} · {{ m.status_name || '—' }}</div>
          </div>
        </div>
      </div>
    </template>

    <el-dialog
      v-model="pickOpen"
      :title="pickTitle"
      width="420px"
      append-to-body
    >
      <el-skeleton v-if="pickLoading" animated :rows="4" />
      <el-empty v-else-if="!pickList.length" description="暂无可选" :image-size="48" />
      <div v-else class="pick-list">
        <button
          v-for="item in pickList"
          :key="item.character_id"
          type="button"
          class="pick-item"
          :class="{ offline: !item.online }"
          @click="pickTarget(item)"
        >
          <span class="presence-dot" :class="{ on: item.online }" />
          <el-text tag="b">{{ item.name }}</el-text>
          <el-tag size="small" :type="item.online ? 'success' : 'info'">
            {{ item.online ? '在线' : '离线' }}
          </el-tag>
          <el-tag v-if="item.rank_label_zh" size="small" type="info">
            {{ item.rank_label_zh }}
          </el-tag>
          <el-tag v-if="item.role" size="small">
            {{ mentorRoleLabel(item.role) }}
          </el-tag>
        </button>
      </div>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.hint {
  display: block;
  margin-bottom: 0.5rem;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.row,
.member-top,
.invite-row,
.toolbar,
.invite-main-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.invite-row-card {
  justify-content: space-between;
  padding: 0.35rem 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.actions {
  display: flex;
  gap: 0.35rem;
}

.leader-tag {
  margin-left: 0.35rem;
}

.team-alert {
  margin: 0.5rem 0;
}

.invite-stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 108px;
  gap: 0.75rem;
  margin: 0.5rem 0 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: linear-gradient(
    165deg,
    var(--el-fill-color-blank) 0%,
    var(--el-fill-color-light) 100%
  );
}

.invite-main {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.invite-hint {
  display: block;
  margin-bottom: 0.15rem;
}

.field-label {
  font-size: 0.75rem;
  color: var(--el-text-color-secondary);
}

.invite-side {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  align-items: stretch;
}

.invite-side :deep(.el-button) {
  margin: 0;
}

@media (max-width: 560px) {
  .invite-stage {
    grid-template-columns: 1fr;
  }

  .invite-side {
    flex-direction: row;
    flex-wrap: wrap;
  }
}

.member-card {
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 0.4rem 0;
}

.member-top {
  cursor: pointer;
}

.member-detail {
  margin: 0.35rem 0 0.25rem 1rem;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--el-text-color-regular);
}

.presence-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  flex-shrink: 0;
}

.presence-dot.on {
  background: #67c23a;
}

.pick-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: 360px;
  overflow: auto;
}

.pick-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  text-align: left;
  padding: 0.45rem 0.5rem;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
}

.pick-item:hover {
  border-color: var(--el-color-primary);
}

.pick-item.offline {
  opacity: 0.72;
}
</style>
