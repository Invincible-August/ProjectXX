<script setup lang="ts">
/**
 * Per-kind finalized research tiles (功法 / 阵法 / 符箓 separate; no shared table).
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { CAVE_WORKSHOP_PATH } from '../../constants/cave'
import { useResearchStore } from '../../stores/research'
import type { PrivateContentPublic, ResearchKind } from '../../types/research'
import {
  efficacyLabelZh,
  rankLabelZh,
  type TechniqueMineFields,
} from '../../types/techniqueCraft'

const props = defineProps<{
  kind: ResearchKind
}>()

const emit = defineEmits<{
  (e: 'cultivate-technique', row: TechniqueMineFields): void
}>()

const router = useRouter()
const researchStore = useResearchStore()

const titleZh = computed(() => {
  if (props.kind === 'technique') return '我的功法'
  if (props.kind === 'formation') return '我的阵法'
  return '我的符箓'
})

const emptyZh = computed(() => {
  if (props.kind === 'technique') return '尚无已定稿功法'
  if (props.kind === 'formation') return '尚无已定稿阵法'
  return '尚无已定稿符箓'
})

const rows = computed(() =>
  researchStore.mine.filter((row) => row.kind === props.kind),
)

function asTechnique(row: PrivateContentPublic): TechniqueMineFields {
  return row as unknown as TechniqueMineFields
}

function techniqueRank(row: PrivateContentPublic): string {
  const t = asTechnique(row)
  return t.major_rank_label_zh || rankLabelZh(t.major_rank)
}

function techniqueEfficacy(row: PrivateContentPublic): string {
  return efficacyLabelZh(asTechnique(row).efficacy)
}

function tileMeta(row: PrivateContentPublic): string {
  if (props.kind === 'technique') {
    return `${techniqueEfficacy(row)} · ${techniqueRank(row)}阶 · 点${asTechnique(row).upgrade_points ?? 0}`
  }
  if (props.kind === 'talisman') {
    return row.effect_label_zh || row.effect_id || '符箓'
  }
  return `${row.source_label_zh} · v${row.revision}`
}

function onCultivate(row: PrivateContentPublic): void {
  emit('cultivate-technique', asTechnique(row))
}

function onSecondary(row: PrivateContentPublic): void {
  if (props.kind === 'formation') {
    void router.push('/formation')
    return
  }
  if (props.kind === 'talisman') {
    void router.push({ path: CAVE_WORKSHOP_PATH, query: { branch: 'talisman' } })
    return
  }
  void router.push('/character')
}
</script>

<template>
  <el-card shadow="never" class="mine-card">
    <template #header>
      <div class="mine-head">
        <el-text tag="b" size="small">{{ titleZh }}</el-text>
        <el-tag size="small" effect="plain" type="info">{{ rows.length }}</el-tag>
      </div>
    </template>

    <el-empty v-if="!rows.length" :description="emptyZh" :image-size="48" />

    <div v-else class="tile-grid">
      <div v-for="row in rows" :key="row.id" class="tile">
        <div class="tile-title">{{ row.label_zh }}</div>
        <div class="tile-meta">{{ tileMeta(row) }}</div>
        <div class="tile-ops">
          <el-button
            v-if="kind === 'technique' && asTechnique(row).cultivable !== false"
            type="primary"
            size="small"
            @click="onCultivate(row)"
          >
            升级功法
          </el-button>
          <el-button
            v-if="kind === 'formation'"
            link
            type="primary"
            size="small"
            @click="onSecondary(row)"
          >
            去阵法
          </el-button>
          <el-button
            v-else-if="kind === 'talisman'"
            link
            type="primary"
            size="small"
            @click="onSecondary(row)"
          >
            去工坊
          </el-button>
          <el-button
            v-else-if="kind === 'technique'"
            link
            type="primary"
            size="small"
            @click="onSecondary(row)"
          >
            去穿戴
          </el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.mine-card {
  border: 1px solid var(--el-border-color-lighter);
}
.mine-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.tile-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  overflow: visible;
}
.tile {
  flex: 1 1 10.5rem;
  max-width: 100%;
  min-width: 9.5rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}
.tile-title {
  font-size: 0.92rem;
  font-weight: 600;
  line-height: 1.35;
  word-break: break-word;
}
.tile-meta {
  margin-top: 0.2rem;
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}
.tile-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem;
  margin-top: 0.45rem;
  align-items: center;
}
</style>
