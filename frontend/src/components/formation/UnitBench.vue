<script setup lang="ts">
/**
 * 可上阵棋子：按装备栏分成角色 / 灵宠 / 傀儡 / 化身四栏，外加助战虚位。
 * 计数为（已上阵 / 已装备）；未装备栏显示 (0/0)。
 */
import { computed } from 'vue'
import type { BenchUnit, UnitPlacement } from '../../types/formation'
import { ASSIST_ANCHOR_UID, isTrialPuppetUid } from '../../types/formation'

const props = defineProps<{
  bench: BenchUnit[]
  units: UnitPlacement[]
  selectedUid: string | null
  maxUnits: number
  assistAnchor?: { x: number; y: number } | null
  assistGuestName?: string | null
}>()

const emit = defineEmits<{
  select: [unit: BenchUnit]
  remove: [unitUid: string]
  selectAssist: []
  removeAssist: []
}>()

interface BenchColumn {
  kind: string
  label: string
  units: BenchUnit[]
  equipped: number
  deployed: number
}

const COLUMN_DEFS: { kind: string; label: string }[] = [
  { kind: 'main', label: '角色' },
  { kind: 'pet', label: '灵宠' },
  { kind: 'puppet', label: '傀儡' },
  { kind: 'avatar', label: '化身' },
]

const kindLabels: Record<string, string> = {
  main: '角色',
  avatar: '化身',
  pet: '灵宠',
  puppet: '傀儡',
}

const columns = computed<BenchColumn[]>(() =>
  COLUMN_DEFS.map((def) => {
    const units = props.bench.filter((unit) => {
      if (unit.unit_kind !== def.kind) return false
      if (def.kind === 'puppet' && isTrialPuppetUid(unit.unit_uid)) return false
      if (String(unit.unit_uid).startsWith('avatar_guest_')) return false
      return true
    })
    const equipped = units.length
    const deployed = props.units.filter((unit) => unit.unit_kind === def.kind).length
    return {
      kind: def.kind,
      label: def.label,
      units,
      equipped,
      deployed,
    }
  }),
)

const occupiedCount = computed(
  () => props.units.length + (props.assistAnchor ? 1 : 0),
)

const assistSelected = computed(() => props.selectedUid === ASSIST_ANCHOR_UID)
const assistLabel = computed(() => props.assistGuestName || '助战')

function displayName(unit: BenchUnit): string {
  return unit.display_name ?? unit.name
}

function disabledText(unit: BenchUnit): string {
  if (unit.enabled) return ''
  return unit.disabled_reason || '未开放'
}

function placementOf(uid: string): UnitPlacement | undefined {
  return props.units.find((u) => u.unit_uid === uid)
}

function removableUidsFor(unit: BenchUnit): string[] {
  if (unit.unit_kind === 'main') return []
  const exact = placementOf(unit.unit_uid)
  return exact ? [exact.unit_uid] : []
}

/** 棋盘上不在 Bench 清单中的孤儿棋子（额外区块展示） */
const orphanUnits = computed(() => {
  const benchUids = new Set(props.bench.map((b) => b.unit_uid))
  return props.units.filter(
    (u) =>
      u.unit_kind !== 'main' &&
      !isTrialPuppetUid(u.unit_uid) &&
      !benchUids.has(u.unit_uid),
  )
})
</script>

<template>
  <el-card shadow="never" class="bench-card">
    <template #header>
      <el-text tag="b">棋子（{{ occupiedCount }}/{{ maxUnits }}）</el-text>
    </template>

    <div class="bench-groups">
      <div v-for="column in columns" :key="column.kind" class="bench-group">
        <el-text tag="b" size="small" class="group-label">
          {{ column.label }}（{{ column.deployed }}/{{ column.equipped }}）
        </el-text>
        <el-text v-if="column.equipped === 0" type="info" size="small" class="empty-hint">
          未装备
        </el-text>
        <div
          v-for="unit in column.units"
          :key="unit.unit_uid"
          class="bench-item"
        >
          <el-tooltip
            v-if="!unit.enabled"
            :content="disabledText(unit)"
            placement="top"
          >
            <el-button size="small" disabled>
              {{ displayName(unit) }}
            </el-button>
          </el-tooltip>
          <el-button
            v-else
            size="small"
            :type="unit.unit_uid === selectedUid ? 'warning' : 'default'"
            @click="emit('select', unit)"
          >
            {{ displayName(unit) }}
            <template v-if="placementOf(unit.unit_uid)">
              ({{ placementOf(unit.unit_uid)!.x }},{{ placementOf(unit.unit_uid)!.y }})
            </template>
          </el-button>
          <el-button
            v-for="uid in removableUidsFor(unit)"
            :key="'rm-' + uid"
            size="small"
            text
            type="danger"
            @click="emit('remove', uid)"
          >
            撤下
          </el-button>
        </div>
      </div>
    </div>

    <div class="bench-group">
      <el-text tag="b" size="small" class="group-label">
        助战（{{ assistAnchor ? 1 : 0 }}/1）
      </el-text>
      <el-text type="info" size="small" class="empty-hint">
        {{ assistGuestName ? '开战时道友化身落入该格' : '无助战会话时为虚位，可先摆位置' }}
      </el-text>
      <div class="bench-item">
        <el-button
          size="small"
          :type="assistSelected ? 'warning' : 'default'"
          @click="emit('selectAssist')"
        >
          {{ assistLabel }}
          <template v-if="assistAnchor">
            ({{ assistAnchor.x }},{{ assistAnchor.y }})
          </template>
        </el-button>
        <el-button
          v-if="assistAnchor"
          size="small"
          text
          type="danger"
          @click="emit('removeAssist')"
        >
          撤下
        </el-button>
      </div>
    </div>

    <div v-if="orphanUnits.length" class="bench-group orphan-group">
      <el-text tag="b" size="small" class="group-label" type="warning">
        失效棋子（已不在清单，须撤下）
      </el-text>
      <div v-for="unit in orphanUnits" :key="'orphan-' + unit.unit_uid" class="bench-item">
        <el-tag size="small" type="danger">
          {{ kindLabels[unit.unit_kind] || unit.unit_kind }} · {{ unit.unit_uid }}
          ({{ unit.x }},{{ unit.y }})
        </el-tag>
        <el-button size="small" text type="danger" @click="emit('remove', unit.unit_uid)">
          撤下
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.bench-card {
  width: 100%;
}

.bench-group {
  margin-bottom: 0.75rem;
}

.group-label {
  display: block;
  margin-bottom: 0.35rem;
  color: var(--el-text-color-secondary);
}

.empty-hint {
  display: block;
  margin-bottom: 0.35rem;
}

.bench-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-bottom: 0.35rem;
  flex-wrap: wrap;
}

.orphan-group {
  margin-top: 0.75rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--el-border-color);
}
</style>
