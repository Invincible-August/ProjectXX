/**
 * M4/N4 灵宠 Pinia store。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  captureTestPet,
  claimPetHatch,
  equipPetSkills,
  explorePetAuto,
  explorePetCapture,
  explorePetEncounter,
  feedPet,
  fetchPetCatalog,
  fetchPetExplorePreview,
  fetchPetHatch,
  fetchPets,
  gradeUpPet,
  learnPetSkillFromBook,
  learnPetSkillFromPool,
  patchPet,
  rerollPetAffixType,
  rerollPetAffixValue,
  startPetHatch,
  upgradePet,
} from '../api/pets'
import type {
  PetCaptureResult,
  PetCatalogPayload,
  PetEncounterPublic,
  PetExplorePreview,
  PetHatchEggPublic,
  PetHatchJobPublic,
  PetPublic,
} from '../types/pets'
import { useCharacterStore } from './character'

/** 默认持有上限（与 backend pets.yaml hold_cap 对齐） */
const DEFAULT_PET_CAP = 5

export const usePetsStore = defineStore('pets', () => {
  const pets = ref<PetPublic[]>([])
  const catalog = ref<PetCatalogPayload | null>(null)
  const cap = ref(DEFAULT_PET_CAP)
  const loading = ref(false)
  const hatchEggs = ref<PetHatchEggPublic[]>([])
  const hatchJobs = ref<PetHatchJobPublic[]>([])
  const hatchActiveCount = ref(0)
  const hatchMaxConcurrent = ref(0)
  const explorePreview = ref<PetExplorePreview | null>(null)
  const lastEncounter = ref<PetEncounterPublic | null>(null)
  const lastCapture = ref<PetCaptureResult | null>(null)

  async function load(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchPets()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '加载灵宠失败'
      }
      pets.value = envelope.data.pets
      if (typeof envelope.data.hold_cap === 'number') {
        cap.value = envelope.data.hold_cap
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadCatalog(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchPetCatalog()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '加载图鉴失败'
      }
      catalog.value = envelope.data
      if (typeof envelope.data.hold_cap === 'number') {
        cap.value = envelope.data.hold_cap
      }
      return null
    } finally {
      loading.value = false
    }
  }

  /** 测试捕获：默认不指定物种，由服务端加权抽取 */
  async function captureTest(speciesId?: string | null): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await captureTestPet(
        speciesId ? { species_id: speciesId } : { species_id: null },
      )
      if (envelope.code !== 0) {
        return envelope.message || `测试捕获失败（code=${envelope.code}）`
      }
      await load()
      await loadCatalog()
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function upgrade(petId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await upgradePet(petId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `升级失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0) {
        pets.value[idx] = envelope.data.pet
          ? envelope.data.pet
          : {
              ...pets.value[idx],
              level: envelope.data.level,
              stats: envelope.data.stats ?? pets.value[idx].stats,
            }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function gradeUp(petId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await gradeUpPet(petId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `升阶失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function rerollAffixValue(petId: number, slotIndex: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await rerollPetAffixValue(petId, slotIndex)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `洗炼失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function rerollAffixType(petId: number, slotIndex: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await rerollPetAffixType(petId, slotIndex)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `改类型失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function feed(petId: number, itemId: string, quantity = 1): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await feedPet(petId, itemId, quantity)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `喂养失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function equipSkills(
    petId: number,
    equipped: Array<string | null>,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await equipPetSkills(petId, equipped)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `装备技能失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function learnFromPool(petId: number, skillId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await learnPetSkillFromPool(petId, skillId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `领悟失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function learnFromBook(petId: number, bookId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await learnPetSkillFromBook(petId, bookId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `技能书学习失败（code=${envelope.code}）`
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0 && envelope.data.pet) {
        pets.value[idx] = envelope.data.pet
      } else {
        await load()
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function setDeployPreferred(
    petId: number,
    preferred: boolean,
  ): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await patchPet(petId, { is_deploy_preferred: preferred })
      if (envelope.code !== 0) {
        return envelope.message || '更新偏好失败'
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0) {
        pets.value[idx] = {
          ...pets.value[idx],
          is_deploy_preferred: preferred,
        }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function setNickname(petId: number, nickname: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await patchPet(petId, { nickname })
      if (envelope.code !== 0) {
        return envelope.message || '更新昵称失败'
      }
      const idx = pets.value.findIndex((p) => p.id === petId)
      if (idx >= 0) {
        pets.value[idx] = { ...pets.value[idx], nickname: nickname.trim() || null }
      }
      return null
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    pets.value = []
    catalog.value = null
    hatchEggs.value = []
    hatchJobs.value = []
    hatchActiveCount.value = 0
    hatchMaxConcurrent.value = 0
  }

  async function loadHatch(): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await fetchPetHatch()
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || '加载孵化失败'
      }
      hatchEggs.value = envelope.data.eggs
      hatchJobs.value = envelope.data.jobs
      hatchActiveCount.value = envelope.data.active_count
      hatchMaxConcurrent.value = envelope.data.max_concurrent
      if (typeof envelope.data.hold_cap === 'number') {
        cap.value = envelope.data.hold_cap
      }
      return null
    } finally {
      loading.value = false
    }
  }

  async function startHatch(eggItemId: string): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await startPetHatch(eggItemId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开工失败（code=${envelope.code}）`
      }
      await loadHatch()
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function claimHatch(jobId: number): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await claimPetHatch(jobId)
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `领取失败（code=${envelope.code}）`
      }
      await load()
      await loadCatalog()
      await loadHatch()
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadExplorePreview(regionId = 'default'): Promise<string | null> {
    const envelope = await fetchPetExplorePreview(regionId)
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '加载探索预览失败'
    }
    explorePreview.value = envelope.data
    return null
  }

  async function exploreEncounter(regionId = 'default'): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await explorePetEncounter({ region_id: regionId })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `遭遇失败（code=${envelope.code}）`
      }
      lastEncounter.value = envelope.data
      lastCapture.value = null
      await loadCatalog()
      await loadExplorePreview(regionId)
      return null
    } finally {
      loading.value = false
    }
  }

  async function exploreCapture(): Promise<string | null> {
    if (!lastEncounter.value?.encounter_id) {
      return '请先遭遇'
    }
    loading.value = true
    try {
      const envelope = await explorePetCapture({
        encounter_id: lastEncounter.value.encounter_id,
      })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `捕获失败（code=${envelope.code}）`
      }
      lastCapture.value = envelope.data
      if (envelope.data.success) {
        await load()
        await loadCatalog()
      }
      await loadExplorePreview(lastEncounter.value.region_id)
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  async function exploreAuto(regionId = 'default'): Promise<string | null> {
    loading.value = true
    try {
      const envelope = await explorePetAuto({ region_id: regionId })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `自动捕失败（code=${envelope.code}）`
      }
      const rolls = envelope.data.rolls || []
      lastEncounter.value = rolls.length ? rolls[rolls.length - 1] : null
      lastCapture.value = envelope.data.capture
      if (envelope.data.capture?.success) {
        await load()
        await loadCatalog()
      }
      await loadExplorePreview(regionId)
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    pets,
    catalog,
    cap,
    loading,
    hatchEggs,
    hatchJobs,
    hatchActiveCount,
    hatchMaxConcurrent,
    explorePreview,
    lastEncounter,
    lastCapture,
    load,
    loadCatalog,
    loadHatch,
    startHatch,
    claimHatch,
    loadExplorePreview,
    exploreEncounter,
    exploreCapture,
    exploreAuto,
    captureTest,
    upgrade,
    gradeUp,
    rerollAffixValue,
    rerollAffixType,
    feed,
    equipSkills,
    learnFromPool,
    learnFromBook,
    setDeployPreferred,
    setNickname,
    clear,
  }
})
