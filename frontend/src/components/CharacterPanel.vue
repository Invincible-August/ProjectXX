<script setup lang="ts">
/**
 * 角色属性：境界进度、三池、品阶、神通空槽、攻防。
 */
import { computed } from 'vue'
import type { CharacterPublic } from '../types/character'
import { useCharacterStore } from '../stores/character'
import { idleDirectionLabel } from '../utils/idleLabels'

const props = defineProps<{
  character: CharacterPublic | null
}>()

const characterStore = useCharacterStore()

const shownStones = computed(() => {
  if (characterStore.display) return characterStore.display.spirit_stones
  return props.character?.spirit_stones ?? 0
})

const shownCultivationPool = computed(() => {
  if (characterStore.display) return characterStore.display.cultivation_points
  return props.character?.cultivation_points ?? 0
})

const shownBody = computed(() => {
  if (characterStore.display) return characterStore.display.body_tempering_points
  return props.character?.body_tempering_points ?? 0
})

const shownCrafting = computed(() => {
  if (characterStore.display) return characterStore.display.crafting_exp
  return props.character?.crafting_exp ?? 0
})

const realmProgress = computed(() => props.character?.realm_progress ?? 0)

const shownRatio = computed(() => {
  const ch = props.character
  if (!ch) return 0
  if (ch.cultivation_to_next == null || ch.cultivation_to_next <= 0) return 0
  return Math.min(1, realmProgress.value / ch.cultivation_to_next)
})

const shownStalled = computed(() => {
  if (characterStore.display) return characterStore.display.is_stalled
  return props.character?.is_stalled ?? false
})

const divineSlots = computed(() => {
  const n = props.character?.divine_ability_slots ?? 0
  return Array.from({ length: Math.max(0, n) }, (_, i) => i)
})

function progressPercent(ratio: number): number {
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
}
</script>

<template>
  <el-card shadow="never" class="attr-panel">
    <template #header>
      <el-text tag="b">角色属性</el-text>
    </template>

    <el-empty v-if="!character" description="暂无角色数据" :image-size="56" />

    <template v-else>
      <div class="attr-hero">
        <el-text tag="b" size="large">{{ character.name }}</el-text>
        <el-tag type="info" effect="plain" size="small">{{ character.realm_display }}</el-tag>
      </div>

      <div class="attr-progress">
        <div class="attr-progress-label">
          <el-text size="small">境界进度</el-text>
          <el-text size="small" type="info">
            {{ realmProgress }}
            <template v-if="character.cultivation_to_next != null">
              / {{ character.cultivation_to_next }}
            </template>
          </el-text>
        </div>
        <el-progress
          :percentage="progressPercent(shownRatio)"
          :stroke-width="10"
          :status="shownRatio >= 1 ? 'success' : undefined"
        />
      </div>

      <el-alert
        v-if="shownStalled"
        title="灵石不足，修炼停滞；可通过战斗获取灵石"
        type="warning"
        show-icon
        :closable="false"
        class="attr-stall"
      />

      <el-alert
        v-if="character.offline_pending"
        title="有未领取的离线收益，请先领取后再修炼"
        type="info"
        show-icon
        :closable="false"
        class="attr-stall"
      />

      <el-descriptions :column="1" border size="small" class="attr-desc">
        <el-descriptions-item label="境界">{{ character.realm_display }}</el-descriptions-item>
        <el-descriptions-item label="品阶">
          {{ character.breakthrough_grade_name || '尚未跨境品阶' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">{{ character.status_name }}</el-descriptions-item>
        <el-descriptions-item
          v-if="character.reincarnation_points != null"
          label="轮回点"
        >
          {{ character.reincarnation_points }}
          <el-text v-if="character.reincarnation_count != null" size="small" type="info">
            · 周目 {{ character.reincarnation_count }}
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item
          v-if="character.ferry?.deadline_at"
          label="待引渡"
        >
          截止 {{ character.ferry.deadline_at }}
        </el-descriptions-item>
        <el-descriptions-item label="修炼方向">{{ character.idle_direction_name }}</el-descriptions-item>
        <el-descriptions-item label="灵石">
          {{ shownStones }}
          <el-text v-if="characterStore.display" size="small" type="info">（推算）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="修为池">
          {{ shownCultivationPool }}
          <el-text v-if="characterStore.display" size="small" type="info">（推算）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="炼体度池">
          {{ shownBody }}
          <el-text v-if="characterStore.display" size="small" type="info">（推算）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="制造业经验池">
          {{ shownCrafting }}
          <el-text v-if="characterStore.display" size="small" type="info">（推算）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="攻 / 防">
          {{ character.base_atk }} / {{ character.base_hp }}
        </el-descriptions-item>
        <el-descriptions-item label="神通槽">
          <template v-if="divineSlots.length === 0">无（占位）</template>
          <span v-else class="divine-slots">
            <el-tag
              v-for="slot in divineSlots"
              :key="slot"
              size="small"
              type="info"
              effect="plain"
            >
              空槽
            </el-tag>
          </span>
        </el-descriptions-item>
        <el-descriptions-item v-if="character.divine_sense" label="神识">
          {{ character.divine_sense.load }} / {{ character.divine_sense.capacity }}
          <el-text v-if="character.divine_sense.backlash" type="warning" size="small">反噬</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="阵法等级">
          Lv.{{ character.array_craft_level ?? 0 }}
        </el-descriptions-item>
        <el-descriptions-item v-if="character.has_avatar" label="化身">
          已凝练 · {{ idleDirectionLabel(character.avatar_summary?.idle_direction ?? 'none') }}
        </el-descriptions-item>
      </el-descriptions>
    </template>
  </el-card>
</template>

<style scoped>
.attr-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.attr-progress {
  margin-bottom: 0.75rem;
}

.attr-progress-label {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.25rem;
}

.attr-stall {
  margin-bottom: 0.75rem;
}

.attr-desc {
  margin-top: 0.25rem;
}

.divine-slots {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
</style>
