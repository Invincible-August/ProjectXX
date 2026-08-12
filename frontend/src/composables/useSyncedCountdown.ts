/**
 * 用服务端截止时刻本地滴答倒计时，避免轮询导致双端差约 1 秒。
 */
import { computed, onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * @param endsAtIso - 截止 ISO（UTC Z）
 * @param serverNowIso - 可选服务端当前时刻，用于校准 skew
 */
export function useSyncedCountdown(
  endsAtIso: Ref<string | null | undefined>,
  serverNowIso?: Ref<string | null | undefined>,
): Ref<number> {
  const nowMs = ref(Date.now())
  const skewMs = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null

  function recalibrate(): void {
    const sn = serverNowIso?.value
    if (sn) {
      const parsed = Date.parse(sn)
      if (Number.isFinite(parsed)) {
        skewMs.value = parsed - Date.now()
      }
    }
    nowMs.value = Date.now()
  }

  const secondsLeft = computed(() => {
    void nowMs.value
    const ends = endsAtIso.value
    if (!ends) return 0
    const endMs = Date.parse(ends)
    if (!Number.isFinite(endMs)) return 0
    // 客户端校正后的「服务器此刻」
    const serverishNow = Date.now() + skewMs.value
    return Math.max(0, Math.ceil((endMs - serverishNow) / 1000))
  })

  watch(
    [endsAtIso, ...(serverNowIso ? [serverNowIso] : [])],
    () => recalibrate(),
    { immediate: true },
  )

  timer = setInterval(() => {
    nowMs.value = Date.now()
  }, 250)

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  return secondsLeft
}
