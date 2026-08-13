<script setup lang="ts">
/**
 * 大厅邀请列表：聚合交易 / 队伍 / 双修 / 道友 / 道侣 / 师徒待处理邀请。
 * 放在游戏日志下方；终态后消失；接受并跳转 / 拒绝留大厅。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useBondsStore } from '../../stores/bonds'
import { useCharacterStore } from '../../stores/character'
import { useChatStore } from '../../stores/chat'
import { useDualCultivationStore } from '../../stores/dualCultivation'
import { useFriendsStore } from '../../stores/friends'
import { useMentorStore } from '../../stores/mentor'
import { useTradeStore } from '../../stores/trade'
import { parseUtcMs } from '../../utils/parseUtc'

type InviteKind = 'trade' | 'party' | 'dual' | 'friend' | 'companion' | 'mentor'

interface HallInviteRow {
  key: string
  kind: InviteKind
  kindLabel: string
  fromName: string
  expiresAt: string | null
  refId: number
  canReject: boolean
}

const router = useRouter()
const characterStore = useCharacterStore()
const tradeStore = useTradeStore()
const chatStore = useChatStore()
const dualStore = useDualCultivationStore()
const friendsStore = useFriendsStore()
const bondsStore = useBondsStore()
const mentorStore = useMentorStore()

const busyKey = ref('')
const tick = ref(Date.now())
let pollTimer: ReturnType<typeof setInterval> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null

const myId = computed(() => Number(characterStore.character?.id || 0))

const rows = computed((): HallInviteRow[] => {
  void tick.value
  const out: HallInviteRow[] = []

  for (const p of tradeStore.pendingInvites) {
    out.push({
      key: `trade-${p.session_id}`,
      kind: 'trade',
      kindLabel: '交易',
      fromName: p.from_name,
      expiresAt: p.expires_at ?? null,
      refId: p.session_id,
      canReject: true,
    })
  }

  for (const p of chatStore.pendingInvites) {
    out.push({
      key: `party-${p.id}`,
      kind: 'party',
      kindLabel: '队伍',
      fromName: p.inviter_name,
      expiresAt: p.expires_at ?? null,
      refId: p.id,
      canReject: true,
    })
  }

  const dual = dualStore.session
  if (
    dual &&
    dual.status === 'inviting' &&
    myId.value > 0 &&
    Number(dual.invitee?.character_id) === myId.value
  ) {
    out.push({
      key: `dual-${dual.session_id}`,
      kind: 'dual',
      kindLabel: dual.bond_kind === 'vessel' ? '炉鼎双修' : '道侣双修',
      fromName: dual.inviter?.name || '对方',
      expiresAt: dual.invite_expire_at ?? null,
      refId: dual.session_id,
      canReject: String(dual.bond_kind || '') !== 'vessel',
    })
  }

  for (const f of friendsStore.incoming) {
    out.push({
      key: `friend-${f.friendship_id}`,
      kind: 'friend',
      kindLabel: '道友',
      fromName: f.peer_name,
      expiresAt: null,
      refId: f.friendship_id,
      canReject: true,
    })
  }

  for (const b of bondsStore.companionIncoming) {
    out.push({
      key: `companion-${b.bond_id}`,
      kind: 'companion',
      kindLabel: '道侣',
      fromName: b.peer_name,
      expiresAt: b.expires_at ?? null,
      refId: b.bond_id,
      canReject: true,
    })
  }

  for (const m of mentorStore.incoming) {
    const fromName =
      Number(m.master_character_id) === myId.value
        ? m.apprentice_name
        : m.master_name
    out.push({
      key: `mentor-${m.bond_id}`,
      kind: 'mentor',
      kindLabel: '师徒',
      fromName,
      expiresAt: null,
      refId: m.bond_id,
      canReject: true,
    })
  }

  return out
})

function remainLabel(iso: string | null): string {
  if (!iso) return '—'
  const end = parseUtcMs(iso)
  if (!Number.isFinite(end)) return '—'
  const sec = Math.max(0, Math.floor((end - Date.now()) / 1000))
  if (sec <= 0) return '即将过期'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m > 0 ? `${m}分${s}秒` : `${s}秒`
}

function targetPath(row: HallInviteRow): { path: string; query?: Record<string, string> } {
  if (row.kind === 'trade') {
    return {
      path: '/social',
      query: { mode: 'trade', session: String(row.refId) },
    }
  }
  if (row.kind === 'party') return { path: '/social', query: { mode: 'party' } }
  if (row.kind === 'dual') return { path: '/social', query: { mode: 'dual' } }
  if (row.kind === 'friend' || row.kind === 'companion') {
    return { path: '/social', query: { mode: 'friends' } }
  }
  return { path: '/social', query: { mode: 'mentor' } }
}

async function refreshAll(): Promise<void> {
  await Promise.all([
    tradeStore.refreshPending(),
    chatStore.refreshPartyMe(),
    dualStore.refreshMe(),
    friendsStore.refresh(),
    bondsStore.refresh(),
    mentorStore.refresh(),
  ])
}

async function onOpen(row: HallInviteRow): Promise<void> {
  const t = targetPath(row)
  await router.push(t)
}

async function onAccept(row: HallInviteRow): Promise<void> {
  if (busyKey.value) return
  busyKey.value = row.key
  try {
    let err: string | null = null
    if (row.kind === 'trade') {
      // 交易：只跳转社交交易页，由页面内手动接受/拒绝
      await router.push(targetPath(row))
      return
    } else if (row.kind === 'party') {
      err = await chatStore.acceptPartyInvite(row.refId)
    } else if (row.kind === 'dual') {
      err = await dualStore.confirm(row.refId)
    } else if (row.kind === 'friend') {
      err = await friendsStore.accept(row.refId)
    } else if (row.kind === 'companion') {
      err = await bondsStore.accept(row.refId)
    } else if (row.kind === 'mentor') {
      err = await mentorStore.accept(row.refId)
    }
    if (err) {
      ElMessage.error(err)
      return
    }
    ElMessage.success('已接受')
    await router.push(targetPath(row))
  } finally {
    busyKey.value = ''
    await refreshAll()
  }
}

async function onReject(row: HallInviteRow): Promise<void> {
  if (busyKey.value || !row.canReject) return
  busyKey.value = row.key
  try {
    let err: string | null = null
    if (row.kind === 'trade') {
      err = await tradeStore.loadFace(row.refId)
      if (!err) err = await tradeStore.rejectFace()
    } else if (row.kind === 'party') {
      err = await chatStore.rejectPartyInvite(row.refId)
    } else if (row.kind === 'dual') {
      err = await dualStore.cancel(row.refId)
    } else if (row.kind === 'friend') {
      err = await friendsStore.reject(row.refId)
    } else if (row.kind === 'companion') {
      err = await bondsStore.reject(row.refId)
    } else if (row.kind === 'mentor') {
      err = await mentorStore.reject(row.refId)
    }
    if (err) {
      ElMessage.error(err)
      return
    }
    ElMessage.success('已拒绝')
  } finally {
    busyKey.value = ''
    await refreshAll()
  }
}

onMounted(async () => {
  await refreshAll()
  pollTimer = setInterval(() => {
    void refreshAll()
  }, 8000)
  tickTimer = setInterval(() => {
    tick.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (tickTimer) clearInterval(tickTimer)
})
</script>

<template>
  <el-card shadow="never" class="invite-card">
    <template #header>
      <div class="hdr">
        <el-text tag="b" size="small">邀请列表</el-text>
        <el-text size="small" type="info">{{ rows.length }} 条</el-text>
      </div>
    </template>

    <el-empty v-if="!rows.length" description="暂无邀请" :image-size="40" />
    <div v-else class="invite-scroll">
      <div
        v-for="row in rows"
        :key="row.key"
        class="invite-row"
        @click="onOpen(row)"
      >
        <div class="invite-main">
          <el-tag size="small" type="info">{{ row.kindLabel }}</el-tag>
          <el-text tag="b" size="small">{{ row.fromName }}</el-text>
          <el-text size="small" type="warning">{{ remainLabel(row.expiresAt) }}</el-text>
        </div>
        <div class="invite-actions" @click.stop>
          <el-button
            type="primary"
            size="small"
            :loading="busyKey === row.key"
            @click="onAccept(row)"
          >
            {{ row.kind === 'trade' ? '前往' : '接受' }}
          </el-button>
          <el-button
            v-if="row.canReject"
            size="small"
            type="danger"
            plain
            :loading="busyKey === row.key"
            @click="onReject(row)"
          >
            拒绝
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.invite-card {
  margin-top: 0.75rem;
}
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.invite-scroll {
  max-height: 220px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.invite-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.4rem;
  padding: 0.45rem 0.5rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
}
.invite-row:hover {
  background: var(--el-fill-color-light);
}
.invite-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}
.invite-actions {
  display: flex;
  gap: 0.35rem;
  margin-left: auto;
}
</style>
