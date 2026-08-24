<script setup lang="ts">
/**
 * 化身页：未凝练仅配方槽+凝练；已凝练对齐角色页属性，并提供破除。
 * 挂机方向在大厅修炼区操作，本页不再展示。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import CharacterPanel from '../components/CharacterPanel.vue'
import AvatarCondensePanel from '../components/avatar/AvatarCondensePanel.vue'
import AvatarTransferPanel from '../components/avatar/AvatarTransferPanel.vue'
import CharacterTechniquesPanel from '../components/character/CharacterTechniquesPanel.vue'
import DivineAbilityPanel from '../components/character/DivineAbilityPanel.vue'
import EquipmentSlotsPanel from '../components/character/EquipmentSlotsPanel.vue'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import type { CharacterPublic } from '../types/character'
import type { GameLogEntry } from '../types/gameLog'
import { createLogEntry } from '../types/gameLog'
import { avatarAsCharacter } from '../utils/avatarAsCharacter'
import { canEnterWudao } from '../utils/realm'

const route = useRoute()
const router = useRouter()
const avatarStore = useAvatarStore()
const characterStore = useCharacterStore()

const loadError = ref('')
const logEntries = ref<GameLogEntry[]>([])
const dismissBusy = ref(false)

const hasAvatar = computed(
  () => Boolean(avatarStore.avatar) || Boolean(characterStore.character?.has_avatar),
)
const avatar = computed(() => avatarStore.avatar)
const inTribulation = computed(
  () => characterStore.character?.status === 'tribulation',
)

const avatarCharacter = computed((): CharacterPublic | null => {
  const ch = characterStore.character
  const av = avatar.value
  if (!ch || !av) return ch
  return avatarAsCharacter(ch, av)
})
const canWudao = computed(() => canEnterWudao(avatar.value?.major_realm))

function pushLog(message: string, level: GameLogEntry['level'] = 'info'): void {
  logEntries.value = [...logEntries.value.slice(-49), createLogEntry(message, level)]
}

async function onDismiss(): Promise<void> {
  if (dismissBusy.value) return
  try {
    await ElMessageBox.confirm(
      '破除后化身散去：修为池全额转入本体，淬体消失，装备回背包。凝练材料不退。确定破除？',
      '破除化身',
      {
      confirmButtonText: '破除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  dismissBusy.value = true
  try {
    const error = await avatarStore.dismiss()
    if (error) {
      ElMessage.error(error)
      pushLog(error, 'warning')
      return
    }
    ElMessage.success('化身已破除')
    pushLog('化身已破除', 'success')
  } finally {
    dismissBusy.value = false
  }
}

onMounted(async () => {
  loadError.value = ''
  if (!characterStore.character) {
    const ok = await characterStore.fetchMe()
    if (!ok) {
      await router.replace('/create-character')
      return
    }
  }
  const avErr = await avatarStore.load()
  if (avErr) loadError.value = avErr
  const needFeatures = !avatarStore.avatar || !avatarStore.features?.condense
  if (needFeatures) {
    await avatarStore.loadFeatures()
  }

  if (route.query.tab === 'transfer') {
    requestAnimationFrame(() => {
      document.getElementById('transfer-panel')?.scrollIntoView({ behavior: 'smooth' })
    })
  }
})
</script>

<template>
  <div class="avatar-page">
    <AuthSessionBar />

    <div class="page-title">
      <el-text tag="b" size="large">化身</el-text>
      <el-button
        v-if="hasAvatar && canWudao"
        type="warning"
        size="small"
        @click="router.push('/dao?actor=avatar')"
      >
        悟道
      </el-button>
      <el-button size="small" @click="router.push('/hall')">← 大厅</el-button>
    </div>

    <el-alert
      v-if="inTribulation"
      title="渡劫中：化身不可上阵；挂机请到大厅修炼区"
      type="warning"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <div v-if="!hasAvatar" class="avatar-empty">
      <AvatarCondensePanel @log="pushLog" />
    </div>

    <div v-else-if="avatar" class="character-grid">
      <aside class="character-left">
        <CharacterPanel
          :character="avatarCharacter"
          variant="avatar"
          @log="pushLog"
        />
        <el-button
          type="danger"
          plain
          :loading="dismissBusy"
          class="dismiss-btn"
          @click="onDismiss"
        >
          破除化身
        </el-button>
      </aside>
      <main class="character-right">
        <EquipmentSlotsPanel actor="avatar" @log="pushLog" />
        <CharacterTechniquesPanel actor="avatar" @log="pushLog" />
        <DivineAbilityPanel actor="avatar" @log="pushLog" />
        <AvatarTransferPanel :avatar="avatar" @log="pushLog" />
        <el-card v-if="logEntries.length" shadow="never" class="character-log">
          <template #header>
            <el-text tag="b" size="small">操作提示</el-text>
          </template>
          <el-text
            v-for="entry in logEntries.slice(-5)"
            :key="entry.id"
            size="small"
            class="log-line"
          >
            {{ entry.message }}
          </el-text>
        </el-card>
      </main>
    </div>
    <el-skeleton v-else animated :rows="6" />
  </div>
</template>

<style scoped>
.avatar-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
}

.page-alert {
  margin-bottom: 1rem;
}

.avatar-empty {
  max-width: 520px;
  margin: 0 auto;
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
