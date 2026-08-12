<script setup lang="ts">
/**
 * PET-D05 灵宠 vs NPC 对战面板。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  autoPetDuelNpc,
  startPetDuelNpc,
  turnPetDuel,
} from '../../api/pets'
import type { PetDuelState, PetPublic } from '../../types/pets'

const props = defineProps<{
  pets: PetPublic[]
}>()

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const selectedPetId = ref<number | null>(null)
const duelId = ref<string | null>(null)
const state = ref<PetDuelState | null>(null)
const busy = ref(false)
const seedInput = ref('')
const lastEvents = ref<Array<Record<string, unknown>>>([])

const selectedPet = computed(
  () => props.pets.find((p) => p.id === selectedPetId.value) ?? null,
)

const equippedChoices = computed(() => {
  const ids = selectedPet.value?.skills?.equipped_ids ?? []
  const learned = selectedPet.value?.skills?.learned ?? []
  return ids
    .filter((id): id is string => !!id)
    .map((id) => {
      const hit = learned.find((s) => s.skill_id === id)
      return { skill_id: id, name: hit?.name || id }
    })
})

async function onStart(): Promise<void> {
  if (!selectedPetId.value || busy.value) return
  busy.value = true
  try {
    const seedRaw = seedInput.value.trim()
    const seedNum = seedRaw === '' ? null : Number(seedRaw)
    const envelope = await startPetDuelNpc({
      pet_id: selectedPetId.value,
      seed: seedNum != null && Number.isFinite(seedNum) ? seedNum : null,
    })
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '开战失败')
      emit('log', envelope.message || '开战失败', 'warning')
      return
    }
    duelId.value = envelope.data.duel_id
    state.value = envelope.data.state
    lastEvents.value = envelope.data.state.events || []
    ElMessage.success('对战已开始')
    emit('log', `对战开始 seed=${envelope.data.seed}`, 'success')
  } finally {
    busy.value = false
  }
}

async function onTurn(skillId: string | null): Promise<void> {
  if (!duelId.value || busy.value || state.value?.finished) return
  busy.value = true
  try {
    const envelope = await turnPetDuel(duelId.value, skillId)
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '回合失败')
      emit('log', envelope.message || '回合失败', 'warning')
      return
    }
    state.value = envelope.data.state
    lastEvents.value = envelope.data.turn_events || []
    if (envelope.data.finished) {
      ElMessage.success(`对战结束：${envelope.data.winner}`)
      emit('log', `对战结束 winner=${envelope.data.winner}`, 'system')
    }
  } finally {
    busy.value = false
  }
}

async function onAuto(): Promise<void> {
  if (!selectedPetId.value || busy.value) return
  busy.value = true
  try {
    const seedRaw = seedInput.value.trim()
    const seedNum = seedRaw === '' ? null : Number(seedRaw)
    const envelope = await autoPetDuelNpc({
      pet_id: selectedPetId.value,
      seed: seedNum != null && Number.isFinite(seedNum) ? seedNum : null,
    })
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '自动对战失败')
      emit('log', envelope.message || '自动对战失败', 'warning')
      return
    }
    duelId.value = envelope.data.state.duel_id
    state.value = envelope.data.state
    lastEvents.value = envelope.data.report.events || []
    ElMessage.success(`自动对战结束：${envelope.data.report.winner}`)
    emit(
      'log',
      `自动对战 winner=${envelope.data.report.winner} rounds=${envelope.data.report.rounds}`,
      'system',
    )
  } finally {
    busy.value = false
  }
}

function formatEvent(ev: Record<string, unknown>): string {
  const type = String(ev.type || '')
  if (type === 'damage') {
    return `${ev.side} 造成 ${ev.damage} 伤害 → 对方 HP ${ev.target_hp}`
  }
  if (type === 'move') {
    return `${ev.actor} 使用 ${ev.skill_name}`
  }
  if (type === 'miss') {
    return `${ev.side} 未命中`
  }
  if (type === 'battle_end') {
    return `结束 winner=${ev.winner}`
  }
  return JSON.stringify(ev)
}
</script>

<template>
  <div class="duel">
    <el-text tag="b">灵宠对战（vs NPC · 回合制）</el-text>
    <el-text type="info" size="small">
      非自走棋；选招→比速→结算。可用固定 seed 复现自动战。
    </el-text>

    <div class="row">
      <el-select
        v-model="selectedPetId"
        placeholder="选择出战灵宠"
        clearable
        size="small"
        class="pet-select"
      >
        <el-option
          v-for="p in pets"
          :key="p.id"
          :label="`${p.nickname || p.species_name || p.species_id}（#${p.id}）`"
          :value="p.id"
        />
      </el-select>
      <el-input
        v-model="seedInput"
        size="small"
        placeholder="seed（可选）"
        class="seed-input"
      />
      <el-button size="small" type="primary" :loading="busy" :disabled="!selectedPetId" @click="onStart">
        开战
      </el-button>
      <el-button size="small" :loading="busy" :disabled="!selectedPetId" @click="onAuto">
        自动打完
      </el-button>
    </div>

    <div v-if="state" class="battlefield">
      <div class="fighter">
        <el-text tag="b">{{ state.player.name }}</el-text>
        <el-progress
          :percentage="Math.round((state.player.hp / Math.max(1, state.player.max_hp)) * 100)"
          :stroke-width="12"
          status="success"
        />
        <el-text size="small">
          HP {{ state.player.hp }}/{{ state.player.max_hp }} · 速 {{ state.player.speed }}
        </el-text>
      </div>
      <div class="fighter">
        <el-text tag="b">{{ state.foe.name }}</el-text>
        <el-progress
          :percentage="Math.round((state.foe.hp / Math.max(1, state.foe.max_hp)) * 100)"
          :stroke-width="12"
          status="exception"
        />
        <el-text size="small">
          HP {{ state.foe.hp }}/{{ state.foe.max_hp }} · 速 {{ state.foe.speed }}
        </el-text>
      </div>
    </div>

    <div v-if="state && !state.finished" class="moves">
      <el-button
        v-for="s in equippedChoices"
        :key="s.skill_id"
        size="small"
        :loading="busy"
        @click="onTurn(s.skill_id)"
      >
        {{ s.name }}
      </el-button>
      <el-button size="small" :loading="busy" @click="onTurn(null)">挣扎</el-button>
    </div>

    <el-alert
      v-if="state?.finished"
      :title="`胜负：${state.winner} · 回合 ${state.round_index} · seed ${state.seed}`"
      type="info"
      :closable="false"
      show-icon
    />

    <div v-if="lastEvents.length" class="log">
      <el-text tag="b" size="small">本回合/战报事件</el-text>
      <ul>
        <li v-for="(ev, i) in lastEvents" :key="i">{{ formatEvent(ev) }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.duel {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.pet-select {
  min-width: 12rem;
}

.seed-input {
  width: 8rem;
}

.battlefield {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.fighter {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.moves {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.log ul {
  margin: 0.25rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
}
</style>
