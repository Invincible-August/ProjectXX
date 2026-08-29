<script setup lang="ts">
/**
 * 角色属性：境界进度、三池、品阶、已开道则大道/道值；详细战斗/根基/生成属性折叠。
 * compact=true 时用于大厅摘要（无卡头，详细折叠隐藏）。
 */
import { computed } from 'vue'
import type { CharacterPublic } from '../types/character'
import { useActivityGate } from '../composables/useActivityGate'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import { idleDirectionLabel } from '../utils/idleLabels'
import { daoLabel } from '../utils/daoLabel'
import AvatarAssistSwitch from './avatar/AvatarAssistSwitch.vue'

const props = withDefaults(
  defineProps<{
    character: CharacterPublic | null
    /** 大厅摘要：隐藏详细折叠 */
    compact?: boolean
    /** 化身页 / 大厅化身简览 */
    variant?: 'main' | 'avatar'
    /** 大厅：本体名与化身同槽切换 */
    showBriefSwitch?: boolean
    briefTab?: 'main' | 'avatar'
  }>(),
  { compact: false, variant: 'main', showBriefSwitch: false, briefTab: 'main' },
)

const emit = defineEmits<{
  'update:briefTab': [value: 'main' | 'avatar']
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const characterStore = useCharacterStore()
const avatarStore = useAvatarStore()
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
    return '采矿'
  }
  return '空闲'
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
  if (dir === 'sect_mining') return '采矿'
  if (dir === 'none') return '空闲'
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

const spiritRootLine = computed(() => {
  const roots = props.character?.spirit_roots
  if (roots?.length) {
    return roots.map((r) => r.label_zh).join('、')
  }
  const tags = props.character?.spirit_root_tags
  if (tags?.length) return tags.join('、')
  return '未定'
})

/** 已选定本命道后才在角色栏展示；未开道不占位。本体与化身各读自己的 dao。 */
const daoOpened = computed(() => Boolean(props.character?.dao?.fate_dao_id))
const daoName = computed(() =>
  daoLabel(props.character?.dao?.fate_dao_id, props.character?.dao?.fate_dao_label),
)
const daoQi = computed(() => props.character?.dao?.qi ?? 0)
const daoLevel = computed(() => props.character?.dao?.level ?? 1)

const shownStones = computed(() => {
  if (props.variant === 'avatar') return props.character?.spirit_stones ?? 0
  if (characterStore.display) return characterStore.display.spirit_stones
  return props.character?.spirit_stones ?? 0
})

const shownCultivationPool = computed(() => {
  if (props.variant === 'avatar') return props.character?.cultivation_points ?? 0
  if (characterStore.display) return characterStore.display.cultivation_points
  return props.character?.cultivation_points ?? 0
})

const shownBody = computed(() => {
  if (props.variant === 'avatar') return props.character?.body_tempering_points ?? 0
  if (characterStore.display) return characterStore.display.body_tempering_points
  return props.character?.body_tempering_points ?? 0
})

const shownCrafting = computed(() => {
  if (props.variant === 'avatar') return props.character?.crafting_exp ?? 0
  if (characterStore.display) return characterStore.display.crafting_exp
  return props.character?.crafting_exp ?? 0
})

/** 体力：优先惰性恢复后的 battle_stamina */
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

const combatFinal = computed(() => props.character?.combat?.final ?? null)
const combatLabels = computed(() => props.character?.combat?.labels ?? {})
const combatPrimary = computed(() => props.character?.combat?.primary ?? null)
const lifeFinal = computed(() => props.character?.life?.final ?? null)
const lifeLabels = computed(() => props.character?.life?.labels ?? {})

type PanelRow = { key: string; label: string; value: string | number }

function pickLabeled(
  bag: Record<string, number> | null | undefined,
  labels: Record<string, string>,
  key: string,
): PanelRow | null {
  if (!bag || bag[key] === undefined) return null
  return {
    key,
    label: labels[key] || key,
    value: bag[key],
  }
}

/** 战斗：资源 → 攻防 → 机动 → 元素抗 → 异常/暗抗 */
const COMBAT_ORDER = [
  'hp',
  'mp',
  'phys_atk',
  'magic_atk',
  'phys_def',
  'magic_def',
  'speed',
  'hit',
  'dodge',
  'resist_metal',
  'resist_wood',
  'resist_water',
  'resist_fire',
  'resist_earth',
  'resist_wind',
  'resist_thunder',
  'resist_ailment',
  'resist_dark',
] as const

const combatCoreRows = computed(() => {
  const f = combatFinal.value
  if (!f) return []
  return COMBAT_ORDER.flatMap((k) => {
    const row = pickLabeled(f, combatLabels.value, k)
    return row ? [row] : []
  })
})

const FOUNDATION_PRIMARY_ORDER = [
  'strength',
  'agility',
  'intelligence',
  'comprehension',
  'bone_root',
] as const

const LIFE_HIDDEN_IN_PANEL = new Set<string>([
  'stamina',
  'comprehension',
  'endurance',
  'breath_efficiency',
  'resist_tribulation',
  'resist_heart_demon',
])

const foundationRows = computed((): PanelRow[] => {
  const rows: PanelRow[] = []
  const primary = combatPrimary.value
  for (const key of FOUNDATION_PRIMARY_ORDER) {
    const row =
      pickLabeled(primary, combatLabels.value, key) ||
      pickLabeled(lifeFinal.value, lifeLabels.value, key)
    if (row) rows.push(row)
  }
  rows.push({
    key: 'divine_ability',
    label: '神通',
    value: props.character?.divine_ability_slots ?? 0,
  })
  const breath = pickLabeled(lifeFinal.value, lifeLabels.value, 'breath_efficiency')
  if (breath) rows.push(breath)
  const endurance = pickLabeled(lifeFinal.value, lifeLabels.value, 'endurance')
  if (endurance) rows.push(endurance)
  for (const key of ['resist_tribulation', 'resist_heart_demon'] as const) {
    const row = pickLabeled(lifeFinal.value, lifeLabels.value, key)
    if (row) rows.push(row)
  }
  return rows
})

/** 生成：心性/灵巧/精密与对应制作等级成对 */
const GENERATION_LIFE_ORDER = [
  'temperament',
  'craft_dexterity',
  'precision',
] as const

const generationRows = computed((): PanelRow[] => {
  const craftByBranch = new Map(
    craftLevelRows.value.map((row) => [row.branch, row]),
  )
  const pairs: [string, string][] = [
    ['temperament', 'alchemy'],
    ['craft_dexterity', 'smithing'],
    ['precision', 'talisman'],
  ]
  const rows: PanelRow[] = []
  for (const [lifeKey, branch] of pairs) {
    const lifeRow = pickLabeled(lifeFinal.value, lifeLabels.value, lifeKey)
    if (lifeRow) rows.push(lifeRow)
    const craft = craftByBranch.get(branch)
    if (craft) {
      rows.push({
        key: `craft:${craft.branch}`,
        label: craft.label_zh,
        value: `Lv.${craft.level}`,
      })
    }
  }
  for (const branch of ['array', 'puppet'] as const) {
    const craft = craftByBranch.get(branch)
    if (craft) {
      rows.push({
        key: `craft:${craft.branch}`,
        label: craft.label_zh,
        value: `Lv.${craft.level}`,
      })
    }
  }
  for (const key of Object.keys(lifeFinal.value || {})) {
    if (LIFE_HIDDEN_IN_PANEL.has(key)) continue
    if ((GENERATION_LIFE_ORDER as readonly string[]).includes(key)) continue
    const extra = pickLabeled(lifeFinal.value, lifeLabels.value, key)
    if (extra) rows.push(extra)
  }
  return rows
})

const craftLevelRows = computed(() => {
  const rows = props.character?.craft_levels
  if (Array.isArray(rows) && rows.length) return rows
  const arrayLv = props.character?.array_craft_level ?? 0
  return [
    { branch: 'alchemy', label_zh: '炼丹等级', level: 0 },
    { branch: 'smithing', label_zh: '炼器等级', level: 0 },
    { branch: 'talisman', label_zh: '制符等级', level: 0 },
    { branch: 'array', label_zh: '阵法等级', level: arrayLv },
    { branch: 'puppet', label_zh: '傀儡制作等级', level: 0 },
  ]
})

function progressPercent(ratio: number): number {
  if (!Number.isFinite(ratio)) return 0
  return Math.max(0, Math.min(100, Math.round(ratio * 100)))
}

function formatResourceAmount(current: number, max: number, clampCurrent = true): string {
  const cap = Math.max(0, Math.round(Number(max) || 0))
  const raw = Math.max(0, Math.round(Number(current) || 0))
  const cur = clampCurrent ? Math.min(cap, raw) : raw
  return `${cur}/ ${cap}`
}

function resourcePercent(current: number, max: number, clampCurrent = true): number {
  const cap = Math.max(0, Math.round(Number(max) || 0))
  const raw = Math.max(0, Math.round(Number(current) || 0))
  const cur = clampCurrent ? Math.min(cap, raw) : raw
  if (cap <= 0) return 0
  return Math.round((cur / cap) * 100)
}

const hpLine = computed(() => {
  const ch = props.character
  const max = ch?.hp_max ?? combatFinal.value?.hp ?? ch?.base_hp ?? 0
  const cur = ch?.hp_current ?? max
  return formatResourceAmount(cur, max)
})

const hpPct = computed(() => {
  const ch = props.character
  const max = ch?.hp_max ?? combatFinal.value?.hp ?? ch?.base_hp ?? 0
  const cur = ch?.hp_current ?? max
  return resourcePercent(cur, max)
})

const mpLine = computed(() => {
  const ch = props.character
  const max = ch?.mp_max ?? combatFinal.value?.mp ?? 0
  const cur = ch?.mp_current ?? max
  return formatResourceAmount(cur, max)
})

const mpPct = computed(() => {
  const ch = props.character
  const max = ch?.mp_max ?? combatFinal.value?.mp ?? 0
  const cur = ch?.mp_current ?? max
  return resourcePercent(cur, max)
})

const senseLine = computed(() => {
  const sense = props.character?.divine_sense
  if (!sense) return ''
  return formatResourceAmount(sense.load, sense.capacity, false)
})

const ownerName = computed(
  () => characterStore.character?.name ?? props.character?.name ?? '角色',
)

const avatarStaminaLine = computed(() => {
  const s = avatarStore.avatar?.stamina
  if (!s) return ''
  return formatResourceAmount(s.stamina, s.stamina_cap)
})

const avatarAssistCountLine = computed(() => {
  const s = avatarStore.avatar?.stamina
  if (!s) return ''
  return formatResourceAmount(s.daily_actions_remaining, s.daily_action_cap)
})
</script>

<template>
  <el-card shadow="never" class="attr-panel">
    <template v-if="!compact" #header>
      <div class="attr-header">
        <el-text tag="b">{{ variant === 'avatar' ? '化身属性' : '本尊属性' }}</el-text>
        <slot name="header-extra" />
      </div>
    </template>

    <el-empty v-if="!character" description="暂无角色数据" :image-size="56" />

    <template v-else>
      <div class="attr-hero">
        <div v-if="compact && showBriefSwitch" class="brief-switch">
          <button
            type="button"
            class="brief-tab"
            :class="{ on: briefTab === 'main' }"
            @click="emit('update:briefTab', 'main')"
          >
            {{ ownerName }}
          </button>
          <button
            type="button"
            class="brief-tab"
            :class="{ on: briefTab === 'avatar' }"
            @click="emit('update:briefTab', 'avatar')"
          >
            化身
          </button>
        </div>
        <AvatarAssistSwitch
          v-else-if="variant === 'avatar'"
          @log="(msg, level) => emit('log', msg, level)"
        />
        <el-text v-else tag="b" size="large">{{ character.name }}</el-text>
        <div class="attr-hero-tags">
          <el-tag type="info" effect="plain" size="small">{{ character.realm_display }}</el-tag>
          <el-tag v-if="daoOpened" type="warning" effect="plain" size="small">
            {{ daoName }}
          </el-tag>
        </div>
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
        v-if="variant === 'main' && shownStalled"
        title="灵石不足，修炼停滞；可通过战斗获取灵石"
        type="warning"
        show-icon
        :closable="false"
        class="attr-stall"
      />

      <el-alert
        v-if="variant === 'main' && character.offline_pending"
        title="有未领取的离线收益，请先领取后再修炼"
        type="info"
        show-icon
        :closable="false"
        class="attr-stall"
      />

      <el-descriptions :column="1" border size="small" class="attr-desc">
        <el-descriptions-item label="境界">{{ character.realm_display }}</el-descriptions-item>
        <el-descriptions-item v-if="daoOpened" label="大道">{{ daoName }}</el-descriptions-item>
        <el-descriptions-item v-if="daoOpened" label="道值">
          {{ daoQi }}
          <el-text size="small" type="info">（Lv.{{ daoLevel }}）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="灵根">{{ spiritRootLine }}</el-descriptions-item>
        <el-descriptions-item v-if="variant !== 'avatar'" label="品阶">
          {{ character.breakthrough_grade_name || '尚未跨境品阶' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="variant !== 'avatar'" label="轮回点">
          {{ character.reincarnation_points ?? 0 }}
          <el-text v-if="character.reincarnation_count != null" size="small" type="info">
            （周目 {{ character.reincarnation_count }}）
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item label="生命值">
          {{ hpLine }}
          <el-text size="small" type="info">（{{ hpPct }}%）</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="法力值">
          {{ mpLine }}
          <el-text size="small" type="info">（{{ mpPct }}%）</el-text>
        </el-descriptions-item>
        <el-descriptions-item v-if="variant === 'main' && character.divine_sense" label="神识">
          {{ senseLine }}
        </el-descriptions-item>
        <el-descriptions-item v-if="variant !== 'avatar'" label="体力">
          {{ battleStaminaLine }}
          <el-text
            v-if="character.battle_stamina?.regen_per_minute"
            size="small"
            type="info"
          >
            （{{ character.battle_stamina.regen_per_minute }}/分）
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item v-if="variant === 'avatar' && avatarStaminaLine" label="化身体力">
          {{ avatarStaminaLine }}
        </el-descriptions-item>
        <el-descriptions-item v-if="variant === 'avatar' && avatarAssistCountLine" label="助战次数">
          {{ avatarAssistCountLine }}
        </el-descriptions-item>
        <el-descriptions-item v-if="variant === 'main' && !showBriefSwitch" label="本体/化身">
          <el-text :type="statusTagType === 'info' ? undefined : statusTagType" size="small">
            {{ bodyAvatarLine }}
          </el-text>
          <el-text v-if="statusHint" size="small" type="info" class="status-hint">
            {{ statusHint }}
          </el-text>
        </el-descriptions-item>
        <el-descriptions-item v-else label="状态">
          {{ idleDirectionLabel(character.idle_direction) }}
        </el-descriptions-item>
        <el-descriptions-item label="灵石">
          {{ shownStones }}
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
        <el-descriptions-item v-if="!compact && variant === 'main' && character.has_avatar" label="化身">
          已凝练 · {{ idleDirectionLabel(character.avatar_summary?.idle_direction ?? 'none') }}
        </el-descriptions-item>
      </el-descriptions>

      <template v-if="!compact">
        <el-collapse class="attr-collapse">
          <el-collapse-item v-if="combatCoreRows.length" title="战斗属性" name="combat">
            <el-descriptions :column="2" border size="small" class="attr-grid">
              <el-descriptions-item
                v-for="row in combatCoreRows"
                :key="row.key"
                :label="row.label"
                :span="1"
              >
                {{ row.value }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
          <el-collapse-item v-if="foundationRows.length" title="根基" name="primary">
            <el-descriptions :column="2" border size="small" class="attr-grid">
              <el-descriptions-item
                v-for="row in foundationRows"
                :key="row.key"
                :label="row.label"
                :span="1"
              >
                {{ row.value }}
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
          <el-collapse-item v-if="generationRows.length" title="生产属性" name="life">
            <el-descriptions :column="2" border size="small" class="attr-grid">
              <el-descriptions-item
                v-for="row in generationRows"
                :key="row.key"
                :label="row.label"
                :span="1"
              >
                {{ row.value }}
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
  gap: 0.75rem;
}

.attr-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.attr-hero-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
}

.brief-switch {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}

.brief-tab {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  max-width: 9em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brief-tab.on {
  color: var(--el-text-color-primary);
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

.attr-grid :deep(.el-descriptions__table) {
  table-layout: fixed;
  width: 100%;
}

.attr-grid :deep(.el-descriptions-item__cell) {
  width: 25%;
}
</style>
