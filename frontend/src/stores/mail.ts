/**
 * M7 L3 邮件 / 赠送 Pinia store。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  claimMail,
  listMail,
  markMailRead,
  sendGift,
  sendMail,
} from '../api/mail'
import type { MailItem } from '../types/mail'
import { useCharacterStore } from './character'

export const useMailStore = defineStore('mail', () => {
  const items = ref<MailItem[]>([])
  const unread = ref(0)
  const loading = ref(false)
  const lastMessage = ref('')
  const lastError = ref('')

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
      return null
    } finally {
      loading.value = false
    }
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

  async function markRead(mailId: number): Promise<string | null> {
    const envelope = await markMailRead(mailId)
    if (envelope.code !== 0) {
      return envelope.message || `标记已读失败（code=${envelope.code}）`
    }
    await refresh()
    return null
  }

  async function sendPlayerMail(body: {
    to_name: string
    subject_zh?: string
    body_zh?: string
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
      return null
    } finally {
      loading.value = false
    }
  }

  async function giftToFriend(body: {
    to_name: string
    spirit_stones?: number
    items?: Array<{ item_id: string; quantity: number }>
    note_zh?: string
  }): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await sendGift(body)
      if (envelope.code !== 0 || !envelope.data) {
        const msg = envelope.message || `赠送失败（code=${envelope.code}）`
        lastError.value = msg
        return msg
      }
      lastMessage.value = envelope.data.message || '已赠送'
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
    refresh,
    claim,
    markRead,
    sendPlayerMail,
    giftToFriend,
  }
})
