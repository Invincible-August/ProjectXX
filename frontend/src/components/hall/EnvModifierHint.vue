<script setup lang="ts">
/**
 * 当前行为环境修正提示：优先 catalog 说明，回退 hints。
 */
import { computed } from 'vue'
import { useWorldStore } from '../../stores/world'
import type { EnvCatalogSnippet } from '../../types/idleEnv'

const props = withDefaults(
  defineProps<{
    /** 取 hints / catalog 的哪一类 */
    kind?: 'idle' | 'breakthrough' | 'craft' | 'tribulation'
  }>(),
  { kind: 'idle' },
)

const worldStore = useWorldStore()

/**
 * 从当前天气/时辰 catalog 拼出一句可见说明。
 *
 * @param weather - 天气 catalog
 * @param shichen - 时辰 catalog
 * @param kind - 提示类别
 * @returns 展示文案
 */
function catalogLine(
  weather: EnvCatalogSnippet | null | undefined,
  shichen: EnvCatalogSnippet | null | undefined,
  kind: typeof props.kind,
): string {
  if (kind === 'idle') {
    const parts = [
      shichen?.idle_note ? `时辰：${shichen.idle_note}` : '',
      weather?.idle_note ? `天气：${weather.idle_note}` : '',
    ].filter(Boolean)
    return parts.join(' · ')
  }
  if (kind === 'craft') {
    const notes = weather?.craft_notes
    if (notes && typeof notes === 'object') {
      const bits = [
        notes.alchemy ? `炼丹：${notes.alchemy}` : '',
        notes.smithing ? `炼器：${notes.smithing}` : '',
      ].filter(Boolean)
      if (bits.length) return bits.join(' · ')
    }
  }
  if (kind === 'tribulation') {
    return weather?.tribulation_note || ''
  }
  if (kind === 'breakthrough') {
    return weather?.breakthrough_note || shichen?.breakthrough_note || ''
  }
  return ''
}

const text = computed(() => {
  const catalog = worldStore.env?.catalog
  const fromCatalog = catalogLine(
    catalog?.weather as EnvCatalogSnippet | undefined,
    catalog?.shichen as EnvCatalogSnippet | undefined,
    props.kind,
  )
  if (fromCatalog) return fromCatalog
  const hints = worldStore.env?.hints
  if (!hints) return ''
  return hints[props.kind] || ''
})
</script>

<template>
  <el-alert
    v-if="text"
    :title="text"
    type="info"
    show-icon
    :closable="false"
    class="env-hint"
  />
</template>

<style scoped>
.env-hint {
  margin: 0.25rem 0;
}
</style>
