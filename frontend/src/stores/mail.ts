/**
 * M7 L3 邮件 Pinia store（附物发信并入）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  claimMail,
  claimMailAll,
  deleteMail,
  deleteMailAll,
  fetchMailComposeOptions,
  listMail,
  markMailRead,
  markMailReadAll,
  sendMail,
} from '../api/mail'
import type { MailComposeOptions, MailItem, MailLimits } from '../types/mail'
import { useCharacterStore } from './character'

export const useMailStore = defineStore('mail', () => {
  const items = ref<MailItem[]>([])
  const unread = ref(0)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')
  const limits = ref<MailLimits | null>(null)
  const composeOptions = ref<MailComposeOptions | null>(null)

  function syncBadge(nextUnread: number): void {
    unread.value = nextUnread
    const ch = useCharacterStore().character
    if (!ch) return
    const badges = {
      ...(ch.social_badges ?? {}),
      mail_unread: nextUnread,
      chat_unread: Number(ch.social_badges?.chat_unread ?? 0),
      dual_invite: Number(ch.social_badges?.dual_invite ?? 0),
    }
    useCharacterStore().applyCharacter({
      ...ch,
      social_badges: badges,
    })
  }

  async function refresh(): Promise<string | null> {
    loading.value = true
    lastError.value = ''
    try {
      const envelope = await listMail()
      if (envelope.code !== 0 || !envelope.data) {
        items.value = []
        const msg = envelope.message || `加载邮件失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      items.value = envelope.data.items ?? []
      syncBadge(Number(envelope.data.unread ?? 0))
      if (envelope.data.limits) limits.value = envelope.data.limits
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadComposeOptions(): Promise<string | null> {
    const envelope = await fetchMailComposeOptions()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || `加载写信选项失败（code=${envelope.code}）`
    }
    composeOptions.value = envelope.data
    if (envelope.data.limits) limits.value = envelope.data.limits
    return null
  }

  async function claim(mailId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await claimMail(mailId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `领取失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '附件已入包'
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character as never)
      }
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function claimAll(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await claimMailAll()
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `一键领取失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已领取'
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character as never)
      }
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function markRead(mailId: number): Promise<string | null> {
    const envelope = await markMailRead(mailId)
    if (envelope.code !== 0) {
      return envelope.message || `标记已读失败（code=${envelope.code}）`
    }
    await refresh()
    return null
  }

  async function markReadAll(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await markMailReadAll()
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `一键已读失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已全部标读'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function remove(mailId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await deleteMail(mailId)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `删除失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已删除'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function removeAllEligible(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await deleteMailAll()
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `一键删除失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已删除'
      await refresh()
      return null
    } finally {
      loading.value = false
    }
  }

  async function sendPlayerMail(body: {
    to_name?: string
    to_character_id?: number
    subject_zh?: string
    body_zh?: string
    spirit_stones?: number
    items?: Array<{ item_id: string; quantity: number }>
    broadcast?: 'sect' | 'disciples' | null
  }): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await sendMail(body)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `送信失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已送信'
      if (envelope.data.character) {
        useCharacterStore().applyCharacter(envelope.data.character as never)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    items,
    unread,
    loading,
    lastMessage,
    lastError,
    limits,
    composeOptions,
    refresh,
    loadComposeOptions,
    claim,
    claimAll,
    markRead,
    markReadAll,
    remove,
    removeAllEligible,
    sendPlayerMail,
  }
})
