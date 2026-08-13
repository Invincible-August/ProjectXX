<script setup lang="ts">
/**
 * 角色属性：境界进度、三池、品阶；详细战斗/生活属性折叠。
 * compact=true 时用于大厅摘要，链到 /character。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { CharacterPublic } from '../types/character'
import { useActivityGate } from '../composables/useActivityGate'
import { useCharacterStore } from '../stores/character'
import { idleDirectionLabel } from '../utils/idleLabels'

const props = withDefaults(
  defineProps<{
    character: CharacterPublic | null
    /** 大厅摘要：隐藏详细折叠，显示「打开角色页」 */
    compact?: boolean
  }>(),
  { compact: false },
)

const router = useRouter()
const characterStore = useCharacterStore()
const { activity, modeLabel } = useActivityGate()

/**
 * 本体侧文案：优先非挂机活动（工坊/进阶等）；挂机中显示方向与速率。
 */
const mainActivityLabel = computed(() => {
  const ch = props.character
  if (!ch) return '—'
  const mode = activity.value.mode
  if (mode !== 'free' && mode !== 'idle') {
    return modeLabel.value
  }
  const preview = ch.dual_idle_preview
  const mainDir = preview?.main_idle_direction ?? ch.idle_direction
  if (mainDir === 'spirit') {
    const rate = preview?.main_cultivation_per_tick ?? ch.idle_cultivation_per_tick
    return `修炼 +${rate}/周天`
  }
  if (mainDir === 'body') {
    const rate = preview?.main_body_per_tick ?? ch.idle_body_per_tick ?? 0
    return `淬体 +${rate}/周天`
  }
  if (mainDir === 'crafting') {
    const rate = preview?.main_crafting_per_tick ?? ch.idle_crafting_per_tick ?? 0
    return `制造业修炼 +${rate}/周天`
  }
  if (mainDir === 'sect_mining') {
    return '采矿中'
  }
  return '待机'
})

/** 化身侧：方向与速率（未凝练单独标明） */
const avatarActivityLabel = computed(() => {
  const ch = props.character
  if (!ch) return '—'
  if (!ch.has_avatar) return '未凝练'
  const preview = ch.dual_idle_preview
  const dir =
    preview?.avatar_idle_direction ?? ch.avatar_summary?.idle_direction ?? 'none'
  if (dir === 'spirit') {
    const rate = preview?.avatar_cultivation_per_tick ?? 0
    return `修炼 +${rate}/周天`
  }
  if (dir === 'body') {
    const rate = preview?.avatar_body_per_tick ?? 0
    return `淬体 +${rate}/周天`
  }
  if (dir === 'crafting') {
    const rate = preview?.avatar_crafting_per_tick ?? 0
    return `制造业修炼 +${rate}/周天`
  }
  if (dir === 'sect_mining') return '采矿中'
  if (dir === 'none') return '待机'
  return idleDirectionLabel(dir)
})

/** 本体 · 化身一行（替代原「状态」+「双线程」） */
const bodyAvatarLine = computed(() => {
  const av = avatarActivityLabel.value
  if (av === '未凝练') return `${mainActivityLabel.value} · 化身未凝练`
  return `${mainActivityLabel.value} · 化身${av}`
})

/**
 * 非修炼区已覆盖的占用提示（工坊/进阶/渡劫/待引渡）。
 * 修炼/采矿互斥说明只在修炼区展示，此处不再重复。
 */
const statusHint = computed(() => {
  const mode = activity.value.mode
  if (mode === 'craft') {
    return '工坊进行中无法进入修炼；请等待任务完成或领取后再修炼'
  }
  if (mode === 'breaking_through') {
    return '突破结算中，请稍候片刻'
  }
  if (mode === 'tribulation') {
    return '渡劫进行中'
  }
  if (mode === 'awaiting_ferry') {
    return '待引渡：可前往轮回页自救或求援'
  }
  if (mode === 'reincarnating') {
    return '轮回中：请先完成新生流程'
  }
  return ''
})

const statusTagType = computed(() => {
  const mode = activity.value.mode
  if (mode === 'idle') return 'success'
  if (mode === 'free') return 'info'
  return 'warning'
})

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

/** 战斗体力：优先惰性恢复后的 battle_stamina */
const battleStaminaLine = computed(() => {
  const ch = props.character
  if (!ch) return '—'
  const bs = ch.battle_stamina
  if (bs && typeof bs.left === 'number' && typeof bs.cap === 'number') {
    return `${bs.left} / ${bs.cap}`
  }
  const lifeStamina = ch.life?.final?.stamina
  if (lifeStamina !== undefined && lifeStamina !== null) {
    return String(lifeStamina)
  }
  return '—'
})

/** 炼体程度：炼体九境展示（炼皮→道体） */
const bodyDegreeLabel = computed(() => {
  const ch = props.character
  if (!ch) return '—'
  return ch.body_temper_display || ch.body_temper_stage_name || '—'
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

const combatFinal = computed(() => props.character?.combat?.final ?? null)
const combatLabels = computed(() => props.character?.combat?.labels ?? {})
const combatPrimary = computed(() => props.character?.combat?.primary ?? null)
const combatBreakdown = computed(() => props.character?.combat?.breakdown ?? [])
const lifeFinal = computed(() => props.character?.life?.final ?? null)
const lifeLabels = computed(() => props.character?.life?.labels ?? {})

const combatCoreRows = computed(() => {
  const f = combatFinal.value
  if (!f) return []
  const keys = [
    'hp',
    'phys_atk',
    'phys_def',
    'magic_atk',
    'magic_def',
    'speed',
    'mp',
    'hit',
    'dodge',
  ]
  return keys
    .filter((k) => f[k] !== undefined)
    .map((k) => ({
      key: k,
      label: combatLabels.value[k] || k,
      value: f[k],
    }))
})

const resistRows = computed(() => {
  const f = combatFinal.value
  if (!f) return []
  return Object.keys(f)
    .filter((k) => k.startsWith('resist_'))
    .map((k) => ({
      key: k,
      label: combatLabels.value[k] || k,
      value: f[k],
    }))
})

const primaryRows = computed(() => {
  const p = combatPrimary.value
  if (!p) return []
  return Object.entries(p).map(([k, v]) => ({
    key: k,
    label: combatLabels.value[k] || k,
    value: v,
  }))
})

const lifeRows = computed(() => {
  const f = lifeFinal.value
  if (!f) return []
  return Object.entries(f).map(([k, v]) => ({
    key: k,
    label: lifeLabels.value[k] || k,
    value: v,
  }))
})

const hasDetailAttrs = computed(
  () =>
    combatCoreRows.value.length > 0 ||
    resistRows.value.length > 0 ||
    primaryRows.value.length > 0 ||
    lifeRows.value.length > 0,
)

function progressPercent(ratio: number): number {
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
}

function formatBreakdownLine(row: Record<string, unknown>): string {
  const label = String(row.label_zh || row.source || '来源')
  const parts: string[] = []
  for (const [k, v] of Object.entries(row)) {
    if (k === 'source' || k === 'label_zh' || k === 'note_zh' || k === 'enabled') continue
    parts.push(`${combatLabels.value[k] || k}=${v}`)
  }
  if (row.enabled === false) {
    parts.push(String(row.note_zh || '通道未开启'))
  }
  return parts.length ? `${label}：${parts.join('，')}` : label
}
</script>

<template>
  <el-card shadow="never" class="attr-panel">
    <template #header>
      <div class="attr-header">
        <el-text tag="b">{{ compact ? '角色摘要' : '角色属性' }}</el-text>
        <el-button
          v-if="compact"
          size="small"
          type="primary"
          link
          @click="router.push('/character')"
        >
          打开角色页
        </el-button>
      </div>
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
        <el-descriptions-item label="本体/化身">
          <el-text :type="statusTagType === 'info' ? undefined : statusTagType" size="small">
            {{ bodyAvatarLine }}
          </el-text>
          <el-text v-if="statusHint" size="small" type="info" class="status-hint">
            {{ statusHint }}
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item label="灵石">
          {{ shownStones }}
          <el-text v-if="characterStore.display" size="small" type="info">（推算）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="战斗体力">
          {{ battleStaminaLine }}
          <el-text
            v-if="character.battle_stamina?.regen_per_minute"
            size="small"
            type="info"
          >
            （{{ character.battle_stamina.regen_per_minute }}/分）
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item label="修为池">
          {{ shownCultivationPool }}
        </el-descriptions-item>
        <el-descriptions-item label="淬体度">
          {{ shownBody }}
        </el-descriptions-item>
        <el-descriptions-item label="炼体程度">
          {{ bodyDegreeLabel }}
          <el-text
            v-if="character.body_temper_to_next != null && !character.body_temper_capped"
            size="small"
            type="info"
          >
            （{{ character.body_temper_progress ?? 0 }}
            <template v-if="(character.body_temper_progress ?? 0) + (character.body_temper_to_next ?? 0) > 0">
              /
              {{
                (character.body_temper_progress ?? 0) + (character.body_temper_to_next ?? 0)
              }}
            </template>
            ）
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item label="制造业经验">
          {{ shownCrafting }}
        </el-descriptions-item>
        <el-descriptions-item v-if="!compact" label="攻 / 血">
          {{ character.base_atk }} / {{ character.base_hp }}
        </el-descriptions-item>
        <el-descriptions-item v-if="!compact && character.divine_sense" label="神识">
          {{ character.divine_sense.load }} / {{ character.divine_sense.capacity }}
        </el-descriptions-item>
        <el-descriptions-item v-if="!compact && character.has_avatar" label="化身">
          已凝练 · {{ idleDirectionLabel(character.avatar_summary?.idle_direction ?? 'none') }}
        </el-descriptions-item>
      </el-descriptions>

      <template v-if="!compact && hasDetailAttrs">
        <el-collapse class="attr-collapse">
          <el-collapse-item v-if="combatCoreRows.length" title="战斗属性" name="combat">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item
                v-for="row in combatCoreRows"
                :key="row.key"
                :label="row.label"
              >
                {{ row.value }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
          <el-collapse-item v-if="resistRows.length" title="元素抗性" name="resist">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item
                v-for="row in resistRows"
                :key="row.key"
                :label="row.label"
              >
                {{ row.value }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
          <el-collapse-item v-if="primaryRows.length" title="根基" name="primary">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item
                v-for="row in primaryRows"
                :key="row.key"
                :label="row.label"
              >
                {{ row.value }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
          <el-collapse-item v-if="lifeRows.length" title="生活属性" name="life">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item
                v-for="row in lifeRows"
                :key="row.key"
                :label="row.label"
              >
                {{ row.value }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
          <el-collapse-item
            v-if="combatBreakdown.length"
            title="属性来源拆解"
            name="breakdown"
          >
            <ul class="attr-breakdown">
              <li v-for="(row, idx) in combatBreakdown" :key="idx">
                {{ formatBreakdownLine(row) }}
              </li>
            </ul>
          </el-collapse-item>
          <el-collapse-item title="其它" name="misc">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item
                v-if="character.reincarnation_points != null"
                label="轮回点"
              >
                {{ character.reincarnation_points }}
                <el-text v-if="character.reincarnation_count != null" size="small" type="info">
                  · 周目 {{ character.reincarnation_count }}
                </el-text>
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
              <el-descriptions-item label="阵法等级">
                Lv.{{ character.array_craft_level ?? 0 }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
        </el-collapse>
      </template>
    </template>
  </el-card>
</template>

<style scoped>
.attr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

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

.status-hint {
  display: block;
  margin-top: 0.25rem;
  line-height: 1.4;
}

.attr-collapse {
  margin-top: 0.75rem;
}

.attr-breakdown {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.divine-slots {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
</style>
