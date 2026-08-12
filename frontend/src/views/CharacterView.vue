<script setup lang="ts">
/**
 * 角色页：左属性（折叠详参）/ 右装备（体质）与功法。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import CharacterPanel from '../components/CharacterPanel.vue'
import CharacterTechniquesPanel from '../components/character/CharacterTechniquesPanel.vue'
import ConstitutionPanel from '../components/ConstitutionPanel.vue'
import { useCharacterStore } from '../stores/character'
import { createLogEntry, type GameLogEntry } from '../types/gameLog'

const router = useRouter()
const characterStore = useCharacterStore()
const loadError = ref('')
const logHint = ref<GameLogEntry[]>([])

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logHint.value = [...logHint.value.slice(-19), createLogEntry(message, level)]
}

onMounted(async () => {
  loadError.value = ''
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
    }
  }
})
</script>

<template>
  <div class="character-page">
    <AuthSessionBar />
    <div class="character-title">
      <el-text tag="b" size="large">角色</el-text>
      <el-button size="small" @click="router.push('/hall')">← 大厅</el-button>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="character-alert"
    />

    <div class="character-grid">
      <aside class="character-left">
        <CharacterPanel :character="characterStore.character" />
      </aside>
      <main class="character-right">
        <ConstitutionPanel @log="pushLog" />
        <CharacterTechniquesPanel />
        <el-card v-if="logHint.length" shadow="never" class="character-log">
          <template #header>
            <el-text tag="b" size="small">操作提示</el-text>
          </template>
          <el-text
            v-for="e in logHint.slice(-5)"
            :key="e.id"
            size="small"
            class="log-line"
          >
            {{ e.message }}
          </el-text>
        </el-card>
      </main>
    </div>
  </div>
</template>

<style scoped>
.character-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.character-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
}

.character-alert {
  margin-bottom: 1rem;
}

.character-grid {
  display: grid;
  grid-template-columns: minmax(280px, 420px) 1fr;
  gap: 1rem;
  align-items: start;
}

.character-left,
.character-right {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}

.character-log .log-line {
  display: block;
  margin-bottom: 0.25rem;
}

@media (max-width: 800px) {
  .character-grid {
    grid-template-columns: 1fr;
  }
}
</style>
