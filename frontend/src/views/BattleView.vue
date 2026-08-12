<script setup lang="ts">
/**
 * 战斗页（M3 · /battle）：PVE/PVP 入口 + 体力条 + 本会话战报列表 + 播放器。
 *
 * 战报零保留：列表数据来自 sessionStorage；?report=<key> 自动打开播放。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import BattleEnvLockLine from '../components/battle/BattleEnvLockLine.vue'
import BattleReportList from '../components/battle/BattleReportList.vue'
import BattleReportPlayer from '../components/battle/BattleReportPlayer.vue'
import PveBattlePanel from '../components/battle/PveBattlePanel.vue'
import PvpAttackPanel from '../components/battle/PvpAttackPanel.vue'
import StaminaBar from '../components/battle/StaminaBar.vue'
import { useBattleStore } from '../stores/battle'
import { useCharacterStore } from '../stores/character'
import type { AutochessBattleResult } from '../types/autochess'

const route = useRoute()
const router = useRouter()
const battleStore = useBattleStore()
const characterStore = useCharacterStore()

/** 默认展开的战斗模式区（?mode=pvp 时展开 PVP） */
const activeTab = ref<'pve' | 'pvp'>('pve')

/** 当前播放的战报 payload */
const activeReport = computed<AutochessBattleResult | null>(() => {
  const key = battleStore.activeReportKey
  if (!key) return null
  return (
    battleStore.sessionReports.find((entry) => entry.session_key === key)
      ?.payload ?? null
  )
})

/** 打开某条战报播放。 */
function openReport(sessionKey: string): void {
  battleStore.activeReportKey = sessionKey
}

onMounted(async () => {
  // 进战斗页确保角色面板可用（禁战判断依赖 idle_direction）
  if (!characterStore.character) {
    await characterStore.fetchMe()
  }
  void battleStore.refreshStamina()
  if (route.query.mode === 'pvp') activeTab.value = 'pvp'
  const reportKey = route.query.report
  if (typeof reportKey === 'string' && reportKey) {
    openReport(reportKey)
  }
})
</script>

<template>
  <div class="battle-page">
    <AuthSessionBar />

    <div class="battle-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">战斗</el-text>
      <el-button size="small" type="primary" plain @click="router.push('/formation')">
        去布阵
      </el-button>
    </div>

    <StaminaBar class="battle-stamina" />
    <BattleEnvLockLine
      :locked-shichen="activeReport?.locked_shichen"
      :locked-shichen-label="activeReport?.locked_shichen_label"
      :locked-weather="activeReport?.locked_weather"
      :locked-weather-label="activeReport?.locked_weather_label"
    />

    <div class="battle-grid">
      <div class="battle-left">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="讨伐妖兽" name="pve">
            <PveBattlePanel />
          </el-tab-pane>
          <el-tab-pane label="攻打快照" name="pvp">
            <PvpAttackPanel />
          </el-tab-pane>
        </el-tabs>
      </div>
      <div class="battle-right">
        <BattleReportList @open="openReport" />
      </div>
    </div>

    <BattleReportPlayer :report="activeReport" class="battle-player" />
  </div>
</template>

<style scoped>
.battle-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.battle-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
  flex-wrap: wrap;
}

.battle-stamina {
  margin-bottom: 1rem;
}

.battle-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(280px, 380px);
  gap: 1rem;
  align-items: start;
  margin-bottom: 1rem;
}

.battle-player {
  margin-top: 0.5rem;
}

@media (max-width: 800px) {
  .battle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
