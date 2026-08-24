/**
 * Equipment Pinia store (M8 R0 · 17-zone + puppet loadout).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  addPuppetLoadoutApi,
  equipItemApi,
  fetchEquipmentSlotsApi,
  removePuppetLoadoutApi,
  replacePuppetLoadoutApi,
  setAvatarDeployApi,
  replaceTalismanLoadoutApi,
  unequipSlotApi,
} from '../api/equipment'
import type { EquipmentEquipResponse, EquipmentSlot, EquipmentState } from '../types/equipment'
import { useAvatarStore } from './avatar'
import { useCharacterStore } from './character'

export const useEquipmentStore = defineStore('equipment', () => {
  const slotsState = ref<EquipmentState | null>(null)
  const loading = ref(false)
  const actor = ref<'main' | 'avatar'>('main')

  function applyCombat(combat: EquipmentEquipResponse['combat'] | undefined): void {
    if (!combat) return
    if (actor.value === 'avatar') {
      const avatarStore = useAvatarStore()
      if (avatarStore.avatar) {
        avatarStore.avatar = { ...avatarStore.avatar, combat }
      }
      return
    }
    const characterStore = useCharacterStore()
    if (characterStore.character) {
      characterStore.character = {
        ...characterStore.character,
        combat,
      }
    }
  }

  async function refresh(nextActor: 'main' | 'avatar' = actor.value): Promise<boolean> {
    actor.value = nextActor
    loading.value = true
    try {
      const envelope = await fetchEquipmentSlotsApi(nextActor)
      if (envelope.code !== 0 || !envelope.data) {
        return false
      }
      slotsState.value = envelope.data.equipment
      applyCombat(envelope.data.combat)
      return true
    } finally {
      loading.value = false
    }
  }

  async function equip(slot: EquipmentSlot, itemUid: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await equipItemApi({ slot, item_uid: itemUid, actor: actor.value })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '穿戴失败'
      }
      slotsState.value = envelope.data.equipment
      applyCombat(envelope.data.combat)
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function unequip(slot: EquipmentSlot): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await unequipSlotApi({ slot, actor: actor.value })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '卸下失败'
      }
      slotsState.value = envelope.data.equipment
      applyCombat(envelope.data.combat)
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function addPuppet(itemUid: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await addPuppetLoadoutApi({ item_uid: itemUid })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '加入编成失败'
      }
      slotsState.value = envelope.data.equipment
      return null
    } finally {
      loading.value = false
    }
  }

  async function removePuppet(itemUid: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await removePuppetLoadoutApi({ item_uid: itemUid })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '移出编成失败'
      }
      slotsState.value = envelope.data.equipment
      return null
    } finally {
      loading.value = false
    }
  }

  async function replacePuppets(itemUids: string[]): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await replacePuppetLoadoutApi({ item_uids: itemUids })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '上阵失败'
      }
      slotsState.value = envelope.data.equipment
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function setAvatarDeployed(deployed: boolean): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await setAvatarDeployApi({ deployed })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '化身上阵失败'
      }
      slotsState.value = envelope.data.equipment
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function replaceTalismans(itemUids: string[]): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await replaceTalismanLoadoutApi({ item_uids: itemUids })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '符箓上阵失败'
      }
      slotsState.value = envelope.data.equipment
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    slotsState,
    loading,
    refresh,
    equip,
    unequip,
    addPuppet,
    removePuppet,
    replacePuppets,
    setAvatarDeployed,
    replaceTalismans,
  }
})
