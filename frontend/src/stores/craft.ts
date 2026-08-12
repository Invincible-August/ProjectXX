/**
 * M4 工坊 Pinia store：配方 / 队列 / 本地进度 tick / 开工领取。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { claimCraft, fetchJobs, fetchRecipes, startCraft } from '../api/craft'
import type { CraftActor, CraftJob, CraftRecipe } from '../types/craft'
import type { CharacterPublic } from '../types/character'
import { craftProgressRatio } from '../utils/craftProgress'
import { useCharacterStore } from './character'

/** 本地进度 tick 间隔 */
function craftTickMs(): number {
  const raw = import.meta.env.VITE_CRAFT_TICK_MS
  const parsed = raw ? Number(raw) : 1000
  return Number.isFinite(parsed) && parsed >= 200 ? parsed : 1000
}

export const useCraftStore = defineStore('craft', () => {
  const recipes = ref<CraftRecipe[]>([])
  const jobs = ref<CraftJob[]>([])
  const actor = ref<CraftActor>('main')
  /** 开工是否耗道值运用（偏好由 DaoUsageToggle / CraftDaoUsageLine 写入） */
  const useDao = ref(false)
  const loading = ref(false)
  /** 驱动本地进度条重算 */
  const tickNow = ref(Date.now())

  let tickTimer: ReturnType<typeof setInterval> | null = null

  /** running 任务本地进度映射 jobId → 0~1 */
  const localProgress = computed(() => {
    void tickNow.value
    const map: Record<number, number> = {}
    for (const job of jobs.value) {
      if (job.status === 'running') {
        map[job.id] = craftProgressRatio(job.started_at, job.finish_at, tickNow.value)
      }
    }
    return map
  })

  const readyJobs = computed(() => jobs.value.filter((j) => j.status === 'ready'))
  const runningJobs = computed(() => jobs.value.filter((j) => j.status === 'running'))

  function startTick(): void {
    stopTick()
    tickTimer = setInterval(() => {
      tickNow.value = Date.now()
    }, craftTickMs())
  }

  function stopTick(): void {
    if (tickTimer !== null) {
      clearInterval(tickTimer)
      tickTimer = null
    }
  }

  function tickLocal(): void {
    tickNow.value = Date.now()
  }

  async function applyCharacterIfPresent(data: unknown): Promise<void> {
    if (!data || typeof data !== 'object') return
    const d = data as { character?: CharacterPublic }
    if (d.character) {
      useCharacterStore().applyCharacter(d.character)
    }
  }

  /** 拉配方 + 队列 */
  async function load(): Promise<string | null> {
    loading.value = true
    try {
      const [recipesEnvelope, jobsEnvelope] = await Promise.all([
        fetchRecipes(),
        fetchJobs(),
      ])
      if (recipesEnvelope.code !== 0 || !recipesEnvelope.data) {
        return recipesEnvelope.message || '加载配方失败'
      }
      if (jobsEnvelope.code !== 0 || !jobsEnvelope.data) {
        return jobsEnvelope.message || '加载工坊队列失败'
      }
      recipes.value = recipesEnvelope.data.recipes
      jobs.value = jobsEnvelope.data.jobs
      startTick()
      return null
    } finally {
      loading.value = false
    }
  }

  /** 刷新队列 */
  async function refreshJobs(): Promise<string | null> {
    const envelope = await fetchJobs()
    if (envelope.code !== 0 || !envelope.data) {
      return envelope.message || '刷新队列失败'
    }
    jobs.value = envelope.data.jobs
    return null
  }

  /** 开工 */
  async function start(recipeId: string, craftActor?: CraftActor): Promise<string | null> {
    const who = craftActor ?? actor.value
    loading.value = true
    try {
      const envelope = await startCraft({
        recipe_id: recipeId,
        actor: who,
        use_dao: useDao.value,
      })
      if (envelope.code !== 0 || !envelope.data) {
        return envelope.message || `开工失败（code=${envelope.code}）`
      }
      const data = envelope.data
      if ('job' in data && data.job) {
        jobs.value = [data.job, ...jobs.value]
        await applyCharacterIfPresent(data)
      } else if ('id' in data && 'recipe_id' in data) {
        jobs.value = [data as CraftJob, ...jobs.value]
      }
      await useCharacterStore().fetchMe()
      return null
    } finally {
      loading.value = false
    }
  }

  /** 领取 */
  async function claim(jobId: number): Promise<{ error: string | null; failed?: boolean }> {
    loading.value = true
    try {
      const envelope = await claimCraft(jobId)
      if (envelope.code !== 0 || !envelope.data) {
        return { error: envelope.message || `领取失败（code=${envelope.code}）` }
      }
      await applyCharacterIfPresent(envelope.data)
      await useCharacterStore().fetchMe()
      await refreshJobs()
      return { error: null, failed: envelope.data.failed }
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    stopTick()
    recipes.value = []
    jobs.value = []
  }

  return {
    recipes,
    jobs,
    actor,
    useDao,
    loading,
    localProgress,
    readyJobs,
    runningJobs,
    load,
    refreshJobs,
    start,
    claim,
    tickLocal,
    startTick,
    stopTick,
    clear,
  }
})
