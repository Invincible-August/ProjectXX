/**
 * M7 L2 道友 Pinia store：列表 / 申请 / 隐私 / 资料 / WS 拜帖提示。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  acceptFriend,
  applyFriend,
  fetchFriendPrivacy,
  fetchFriendProfile,
  listFriends,
  rejectFriend,
  removeFriend,
  updateFriendPrivacy,
} from '../api/friends'
import type { FriendItem, FriendProfileCard } from '../types/friends'
import type { WsEnvelope } from '../types/ws'
import { notifyInviteJump } from '../utils/inviteNotify'
import { WsType } from '../ws/protocol'
import { useCharacterStore } from './character'

export const useFriendsStore = defineStore('friends', () => {
  const friends = ref<FriendItem[]>([])
  const incoming = ref<FriendItem[]>([])
  const outgoing = ref<FriendItem[]>([])
  const friendCount = ref(0)
  const maxFriends = ref(0)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')
  /** 本人是否允许道友查看资料 */
  const profileVisible = ref(true)

  async function refresh(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await listFriends()
      if (envelope.code !== 0 || !envelope.data) {
        friends.value = []
        incoming.value = []
        outgoing.value = []
        const msg = envelope.message || `加载道友失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      friends.value = envelope.data.friends ?? []
      incoming.value = envelope.data.incoming ?? []
      outgoing.value = envelope.data.outgoing ?? []
      friendCount.value = Number(envelope.data.friend_count ?? 0)
      maxFriends.value = Number(envelope.data.max_friends ?? 0)
      const ch = useCharacterStore().character
      if (ch) {
        useCharacterStore().applyCharacter({
          ...ch,
          friend_count: friendCount.value,
        })
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Handle friend.request / friend.update WS pushes.
   */
  function applyPush(envelope: WsEnvelope): void {
    if (
      envelope.type !== WsType.FRIEND_REQUEST &&
      envelope.type !== WsType.FRIEND_UPDATE
    ) {
      return
    }
    const p = (envelope.payload || {}) as {
      event?: string
      message?: string
      from_name?: string
    }
    const msg =
      String(p.message || '').trim() ||
      (envelope.type === WsType.FRIEND_REQUEST
        ? '你有新的道友拜帖'
        : '道友申请状态已更新')
    const event = String(p.event || '')
    const title =
      event === 'accepted'
        ? '道友同意'
        : event === 'rejected'
          ? '道友拒绝'
          : '道友拜帖'
    const type =
      event === 'accepted' ? 'success' : event === 'rejected' ? 'warning' : 'info'
    notifyInviteJump({
      title,
      message: msg,
      type,
      dedupeKey: `friend:${event || envelope.type}:${String(p.from_name || msg).slice(0, 32)}`,
      to: { path: '/social', query: { mode: 'friends' } },
      afterNavigate: () => refresh(),
    })
    void refresh()
  }

  async function loadPrivacy(): Promise<string | null> {
    const envelope = await fetchFriendPrivacy()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || `加载隐私设置失败（code=${envelope.code}）`
    }
    profileVisible.value = Boolean(envelope.data.friend_profile_visible)
    return null
  }

  async function setPrivacy(visible: boolean): Promise<string | null> {
    const envelope = await updateFriendPrivacy(visible)
    if (envelope.code !== 0 || !envelope.data) {
      const msg = envelope.message || `更新隐私失败（code=${envelope.code}）`
      lastError.value = msg
      return msg
    }
    profileVisible.value = Boolean(
      envelope.data.friend_profile_visible ?? visible,
    )
    lastMessage.value = envelope.data.message || '隐私已更新'
    return null
  }

  async function loadProfile(
    characterId: number,
  ): Promise<{ err: string | null; profile: FriendProfileCard | null }> {
    const envelope = await fetchFriendProfile(characterId)
    if (envelope.code !== 0 || !envelope.data) {
      return {
        err: envelope.message || `查看失败（code=${envelope.code}）`,
        profile: null,
      }
    }
    return { err: null, profile: envelope.data }
  }

  async function applyByName(targetName: string): Promise<string | null> {
    const name = targetName.trim()
    if (!name) {
      const msg = '请输入对方道号'
      lastError.value = msg
      return msg
    }
    loading.value = true
    try {
      const envelope = await applyFriend({ target_name: name })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `申请失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已发送道友申请'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function applyByCharacterId(characterId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await applyFriend({ target_character_id: characterId })
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `申请失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已发送道友申请'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function accept(friendshipId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await acceptFriend(friendshipId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `确认失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已结为道友'
      if (typeof envelope.data.friend_count === 'number') {
        friendCount.value = envelope.data.friend_count
      }
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function reject(friendshipId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await rejectFriend(friendshipId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `拒绝失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已拒绝申请'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function remove(friendshipId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await removeFriend(friendshipId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `解除失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已解除道友'
      if (typeof envelope.data.friend_count === 'number') {
        friendCount.value = envelope.data.friend_count
      }
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  function applyPresence(characterId: number, online: boolean): void {
    const cid = Number(characterId)
    friends.value = friends.value.map((f) =>
      Number(f.peer_character_id) === cid ? { ...f, online } : f,
    )
  }

  return {
    friends,
    incoming,
    outgoing,
    friendCount,
    maxFriends,
    loading,
    lastMessage,
    lastError,
    profileVisible,
    refresh,
    loadPrivacy,
    setPrivacy,
    loadProfile,
    applyByName,
    applyByCharacterId,
    accept,
    reject,
    remove,
    applyPresence,
    applyPush,
  }
})
