/**
 * 化身 Pinia store：面板 / 功能 / 神识 / 凝练 / 挂机 / 传修为。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  condenseAvatar,
  fetchAvatar,
  fetchAvatarFeatures,
  fetchDivineSense,
  previewTransfer,
  setAvatarIdle,
  transferCultivation,
  type AvatarMutationPayload,
} from '../api/avatar'
import type {
  AvatarFeaturesPayload,
  AvatarIdleDirection,
  AvatarPublic,
  AvatarTransferAudit,
  DivineSenseReading,
} from '../types/avatar'
import type { CharacterPublic } from '../types/character'
import { useCharacterStore } from './character'

/** 解析后端多种响应形态：{character, avatar} 或直接 avatar 面板 */
function unwrapAvatarPayload(
  data: AvatarMutationPayload | AvatarPublic | null | undefined,
): { avatar: AvatarPublic | null; character?: CharacterPublic } {
  if (!data) return { avatar: null }
  if ('avatar' in data || 'character' in data) {
    const wrapped = data as AvatarMutationPayload
    return {
      avatar: wrapped.avatar ?? null,
      character: wrapped.character,
    }
  }
  if ('id' in data && 'idle_direction' in data) {
    return { avatar: data as AvatarPublic }
  }
  return { avatar: null }
}

export const useAvatarStore = defineStore('avatar', () => {
  const avatar = ref<AvatarPublic | null>(null)
  const features = ref<AvatarFeaturesPayload | null>(null)
  const sense = ref<DivineSenseReading | null>(null)
  const loading = ref(false)

  /** 写入化身权威态 */
  function setAvatar(next: AvatarPublic | null): void {
    avatar.value = next
  }

  /** 写入功能看板（可由 /me 回填，避免重复请求） */
  function setFeatures(next: AvatarFeaturesPayload | null): void {
    features.value = next
  }

  /** 写入神识读数 */
  function setSense(next: DivineSenseReading | null): void {
    sense.value = next
  }

  /**
   * 拉取化身面板；未凝练时 data=null。
   * 若响应含 features，同步写入 features 缓存（省 /avatar/features 往返）。
   *
   * 返回: 错误消息；成功为 null。
   */
  async function load(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchAvatar()
      if (envelope.code !== 0) {
        return envelope.message || `加载化身失败（code=${envelope.code}）`
      }
      avatar.value = envelope.data ?? null
      const av = avatar.value
      if (av?.features) {
        features.value = {
          major_realm: useCharacterStore().character?.major_realm ?? '',
          features: av.features,
          unlock_preview: av.unlock_preview ?? null,
        }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 拉取功能解锁看板 */
  async function loadFeatures(): Promise<string | null> {
    const envelope = await fetchAvatarFeatures()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载化身功能失败'
    }
    features.value = envelope.data
    return null
  }

  /** 拉取神识读数 */
  async function loadSense(): Promise<string | null> {
    const envelope = await fetchDivineSense()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载神识失败'
    }
    sense.value = envelope.data
    return null
  }

  /** 凝练化身 */
  async function condense(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await condenseAvatar()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `凝练失败（code=${envelope.code}）`
      }
      const { avatar: av, character } = unwrapAvatarPayload(envelope.data)
      if (av) avatar.value = av
      const characterStore = useCharacterStore()
      if (character) {
        characterStore.applyCharacter(character)
      } else {
        await characterStore.fetchMe()
      }
      await Promise.all([loadSense()])
      // 凝练响应含完整 panel 时直接回填功能表
      if (av?.features) {
        features.value = {
          major_realm: characterStore.character?.major_realm ?? '',
          features: av.features,
          unlock_preview: av.unlock_preview ?? null,
        }
      } else {
        await loadFeatures()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 设置化身挂机方向 */
  async function setIdle(direction: AvatarIdleDirection | string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await setAvatarIdle(direction)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `切换化身方向失败（code=${envelope.code}）`
      }
      const { avatar: av, character } = unwrapAvatarPayload(envelope.data)
      if (av) avatar.value = av
      if (character) {
        useCharacterStore().applyCharacter(character)
      } else {
        await useCharacterStore().fetchMe()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 互传预览（不扣池） */
  async function preview(
    direction: 'main_to_avatar' | 'avatar_to_main',
    amount: number,
  ): Promise<{ error: string | null; data: AvatarTransferAudit | null }> {
    const envelope = await previewTransfer({ direction, amount })
    if (envelope.code !== 0 || !envelope.data) {
      return { error: envelope.message || '预览失败', data: null }
    }
    return { error: null, data: envelope.data }
  }

  /** 传修为（仅 cultivation_points；按保留率到账） */
  async function transfer(
    direction: 'main_to_avatar' | 'avatar_to_main',
    amount: number,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await transferCultivation({ direction, amount })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `传修为失败（code=${envelope.code}）`
      }
      const data = envelope.data
      const characterStore = useCharacterStore()
      if (data.character) {
        characterStore.applyCharacter(data.character)
      }
      if (data.avatar) {
        avatar.value = data.avatar
      } else if (
        data.main_cultivation != null &&
        data.avatar_cultivation != null &&
        characterStore.character
      ) {
        characterStore.applyCharacter({
          ...characterStore.character,
          cultivation_points: data.main_cultivation,
        })
        if (avatar.value) {
          avatar.value = {
            ...avatar.value,
            cultivation_points: data.avatar_cultivation,
          }
        }
      } else {
        await Promise.all([load(), characterStore.fetchMe()])
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 登出清空 */
  function clear(): void {
    avatar.value = null
    features.value = null
    sense.value = null
  }

  return {
    avatar,
    features,
    sense,
    loading,
    setAvatar,
    setFeatures,
    setSense,
    load,
    loadFeatures,
    loadSense,
    condense,
    setIdle,
    preview,
    transfer,
    clear,
  }
})
