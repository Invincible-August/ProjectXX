/**
 * M7 L2 道友 Pinia store：列表 / 申请 / 确认 / 拒绝。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  acceptFriend,
  applyFriend,
  listFriends,
  rejectFriend,
  removeFriend,
} from '../api/friends'
import type { FriendItem } from '../types/friends'
import { useCharacterStore } from './character'

export const useFriendsStore = defineStore('friends', () => {
  /** 已结交道友 */
  const friends = ref<FriendItem[]>([])
  /** 待我确认 */
  const incoming = ref<FriendItem[]>([])
  /** 我发出的待确认 */
  const outgoing = ref<FriendItem[]>([])
  const friendCount = ref(0)
  const maxFriends = ref(0)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')

  /**
   * 刷新道友列表；成功返回 null，失败返回中文错误。
   */
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
      // 同步角色面板角标字段（若已有 character）
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
   * 按道号申请道友。
   *
   * @param targetName - 对方道号
   */
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

  /**
   * 确认来自对方的申请。
   *
   * @param friendshipId - 友谊行 id
   */
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

  /**
   * 拒绝来自对方的申请。
   *
   * @param friendshipId - 友谊行 id
   */
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

  /**
   * 解除已结交道友。
   *
   * @param friendshipId - 友谊行 id
   */
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

  /**
   * Apply WS ``presence.changed`` to friend list dots.
   *
   * @param characterId - Peer character id
   * @param online - New online flag
   */
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
    refresh,
    applyByName,
    accept,
    reject,
    remove,
    applyPresence,
  }
})
