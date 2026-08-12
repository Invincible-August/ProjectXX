<script setup lang="ts">
/**
 * PVE 面板：选怪 + 选进攻预设 + 开战。
 *
 * 体力不足（40049）与占位错误由响应信封文案直接提示；
 * 开战成功后战报进入 useBattleStore.sessionReports 并自动打开播放器。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMonstersApi } from '../../api/battle'
import BattleDaoUsageLine from './BattleDaoUsageLine.vue'
import { useBattleStore } from '../../stores/battle'
import { useCharacterStore } from '../../stores/character'
import type { MonsterInfo } from '../../types/autochess'

const emit = defineEmits<{
  fought: []
}>()

const battleStore = useBattleStore()
const characterStore = useCharacterStore()

const monsters = ref<MonsterInfo[]>([])
const selectedMonsterId = ref('tutorial_slime')
const presetSlot = ref<number | null>(null)
/** 是否运用本命道（权威结算在服务端） */
const useDao = ref(false)

/** 修炼中不可开战 */
const isCultivating = computed(() => {
  const direction = characterStore.character?.idle_direction
  return Boolean(direction && direction !== 'none')
})

/** 体力不足时禁用开战 */
const staminaBlocked = computed(() => {
  const s = battleStore.stamina
  const monster = monsters.value.find((m) => m.monster_id === selectedMonsterId.value)
  if (!s || !monster) return false
  return s.left < monster.stamina_cost
})

/** 当前选中怪的嘲讽光环说明（§0.7） */
const selectedTauntHint = computed(() => {
  const monster = monsters.value.find((m) => m.monster_id === selectedMonsterId.value)
  const auras = monster?.taunt_auras ?? []
  if (!auras.length) return ''
  return auras.map((a) => `${a.label_zh}（${a.summary || a.aura_id}）`).join('、')
})

function monsterOptionLabel(monster: MonsterInfo): string {
  const base = `${monster.name}（体力 ${monster.stamina_cost} · ${monster.unit_count} 棋子）`
  const auras = monster.taunt_auras ?? []
  if (!auras.length) return base
  const names = auras.map((a) => a.label_zh).join('/')
  return `${base} · 嘲讽：${names}`
}

async function loadMonsters(): Promise<void> {
  const envelope = await fetchMonstersApi()
  if (envelope.code === 0 && envelope.data) {
    monsters.value = envelope.data.monsters
  }
}

async function onFight(): Promise<void> {
  if (isCultivating.value) {
    ElMessage.warning('修炼中不可开战，请先停止修炼')
    return
  }
  const error = await battleStore.startPve(
    selectedMonsterId.value,
    presetSlot.value,
    useDao.value,
  )
  if (error) {
    ElMessage.error(error)
    return
  }
  const result = battleStore.lastReport
  ElMessage[result?.result === 'win' ? 'success' : 'warning'](
    result?.result === 'win' ? '进攻方胜！' : '防守方胜，再接再厉',
  )
  emit('fought')
}

onMounted(() => {
  void loadMonsters()
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">讨伐妖兽（PVE）</el-text>
    </template>

    <el-alert
      v-if="isCultivating"
      title="修炼中不可开战，请先停止修炼"
      type="warning"
      show-icon
      :closable="false"
      class="pve-block"
    />

    <div class="pve-form">
      <el-select v-model="selectedMonsterId" size="small" class="pve-select">
        <el-option
          v-for="monster in monsters"
          :key="monster.monster_id"
          :value="monster.monster_id"
          :label="monsterOptionLabel(monster)"
        />
      </el-select>
      <el-select
        v-model="presetSlot"
        size="small"
        class="pve-select"
        placeholder="进攻预设"
        clearable
      >
        <el-option :value="0" label="槽 0（进攻）" />
        <el-option :value="1" label="槽 1（防守）" />
        <el-option :value="2" label="槽 2（临时）" />
      </el-select>
      <el-button
        type="danger"
        size="small"
        :loading="battleStore.fighting"
        :disabled="isCultivating || staminaBlocked"
        @click="onFight"
      >
        开战
      </el-button>
    </div>
    <BattleDaoUsageLine v-model="useDao" />
    <el-text v-if="selectedTauntHint" type="warning" size="small" class="pve-taunt">
      嘲讽光环：{{ selectedTauntHint }}。移动进入范围会被强制攻击持光环单位。
    </el-text>
    <el-text v-if="staminaBlocked" type="warning" size="small">
      体力不足，请等待恢复。
    </el-text>
    <el-text type="info" size="small" class="pve-hint">
      不选预设时默认使用进攻预设；从未布阵则本体落默认锚点 (0,3)。
    </el-text>
  </el-card>
</template>

<style scoped>
.pve-block {
  margin-bottom: 0.75rem;
}

.pve-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.pve-select {
  min-width: 200px;
}

.pve-hint {
  display: block;
}

.pve-taunt {
  display: block;
  margin-bottom: 0.25rem;
}
</style>
