<script setup lang="ts">
/**
 * 可上阵棋子清单（Bench）：按 kind 分组 + disabled_reason tooltip。
 * 支持撤下：精确 uid 匹配，或棋盘孤儿棋子（如无化身后残留 avatar_{id}）。
 */
import { computed } from 'vue'
import type { BenchUnit, UnitPlacement } from '../../types/formation'

const props = defineProps<{
  bench: BenchUnit[]
  units: UnitPlacement[]
  selectedUid: string | null
  maxUnits: number
}>()

const emit = defineEmits<{
  select: [unit: BenchUnit]
  remove: [unitUid: string]
}>()

const kindLabels: Record<string, string> = {
  main: '本体',
  avatar: '化身',
  pet: '灵宠',
  puppet: '傀儡',
}

/** 按 unit_kind 分组（保持原顺序内的相对顺序） */
function groupedBench(): { kind: string; label: string; units: BenchUnit[] }[] {
  const order = ['main', 'avatar', 'pet', 'puppet']
  const map = new Map<string, BenchUnit[]>()
  for (const unit of props.bench) {
    const kind = unit.unit_kind
    if (!map.has(kind)) map.set(kind, [])
    map.get(kind)!.push(unit)
  }
  const groups: { kind: string; label: string; units: BenchUnit[] }[] = []
  for (const kind of order) {
    const units = map.get(kind)
    if (units?.length) {
      groups.push({ kind, label: kindLabels[kind] ?? kind, units })
    }
  }
  for (const [kind, units] of map) {
    if (!order.includes(kind)) {
      groups.push({ kind, label: kind, units })
    }
  }
  return groups
}

function displayName(unit: BenchUnit): string {
  return unit.display_name ?? unit.name
}

/** 灰置原因文案 */
function disabledText(unit: BenchUnit): string {
  if (unit.enabled) return ''
  return unit.disabled_reason || '未开放'
}

function placementOf(uid: string): UnitPlacement | undefined {
  return props.units.find((u) => u.unit_uid === uid)
}

/** Bench 条目精确匹配棋盘时可撤下（孤儿见下方「失效棋子」区） */
function removableUidsFor(unit: BenchUnit): string[] {
  if (unit.unit_kind === 'main') return []
  const exact = placementOf(unit.unit_uid)
  return exact ? [exact.unit_uid] : []
}

/** 棋盘上不在 Bench 清单中的孤儿棋子（额外区块展示） */
const orphanUnits = computed(() => {
  const benchUids = new Set(props.bench.map((b) => b.unit_uid))
  return props.units.filter(
    (u) => u.unit_kind !== 'main' && !benchUids.has(u.unit_uid),
  )
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">棋子（{{ units.length }}/{{ maxUnits }}）</el-text>
    </template>

    <div v-for="group in groupedBench()" :key="group.kind" class="bench-group">
      <el-text tag="b" size="small" class="group-label">{{ group.label }}</el-text>
      <div
        v-for="unit in group.units"
        :key="unit.unit_uid"
        class="bench-item"
        :class="{
          disabled: !unit.enabled,
          active: unit.unit_uid === selectedUid,
        }"
      >
        <el-tooltip
          v-if="!unit.enabled"
          :content="disabledText(unit)"
          placement="right"
        >
          <el-button size="small" disabled>
            {{ displayName(unit) }}（{{ disabledText(unit) }}）
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

    <el-text type="info" size="small">
      本体必须上阵；点选棋子后再点棋盘绿色格落子。无化身时棋盘残留化身可点「撤下」。
    </el-text>
  </el-card>
</template>

<style scoped>
.bench-group {
  margin-bottom: 0.75rem;
}

.group-label {
  display: block;
  margin-bottom: 0.35rem;
  color: var(--el-text-color-secondary);
}

.bench-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-bottom: 0.35rem;
  flex-wrap: wrap;
}

.orphan-group {
  padding-top: 0.25rem;
  border-top: 1px dashed var(--el-border-color);
}
</style>
