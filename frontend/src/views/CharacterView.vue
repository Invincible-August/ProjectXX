<script setup lang="ts">
/**
 * 角色页：本尊 / 化身同页切换（不整页重载）；悟道入口挂在本尊属性卡头。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import CharacterPanel from '../components/CharacterPanel.vue'
import AvatarCondensePanel from '../components/avatar/AvatarCondensePanel.vue'
import AvatarTransferPanel from '../components/avatar/AvatarTransferPanel.vue'
import CharacterTechniquesPanel from '../components/character/CharacterTechniquesPanel.vue'
import DivineAbilityPanel from '../components/character/DivineAbilityPanel.vue'
import EquipmentSlotsPanel from '../components/character/EquipmentSlotsPanel.vue'
import ConstitutionPanel from '../components/ConstitutionPanel.vue'
import { useAvatarStore } from '../stores/avatar'
import { useCharacterStore } from '../stores/character'
import type { CharacterPublic } from '../types/character'
import { useGameLogPush } from '../composables/useGameLogPush'
import { avatarAsCharacter } from '../utils/avatarAsCharacter'
import { canEnterWudao } from '../utils/realm'

const route = useRoute()
const router = useRouter()
const characterStore = useCharacterStore()
const avatarStore = useAvatarStore()

const loadError = ref('')
const { gameLogStore, pushLog } = useGameLogPush()
const dismissBusy = ref(false)

const actorView = computed<'main' | 'avatar'>(() =>
  route.query.actor === 'avatar' ? 'avatar' : 'main',
)
const isMain = computed(() => actorView.value === 'main')
const canWudao = computed(() => canEnterWudao(characterStore.character?.major_realm))

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

function setActor(next: 'main' | 'avatar'): void {
  if (actorView.value === next) return
  const query = { ...route.query }
  if (next === 'avatar') {
    query.actor = 'avatar'
  } else {
    delete query.actor
    delete query.tab
  }
  void router.replace({ path: '/character', query })
}

async function ensureAvatarLoaded(): Promise<void> {
  const avErr = await avatarStore.load()
  if (avErr) loadError.value = avErr
  const needFeatures = !avatarStore.avatar || !avatarStore.features?.condense
  if (needFeatures) {
    await avatarStore.loadFeatures()
  }
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
      },
    )
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
  await ensureAvatarLoaded()
})

watch(
  () => [actorView.value, route.query.tab] as const,
  ([next]) => {
    if (next !== 'avatar') return
    if (route.query.tab === 'transfer') {
      requestAnimationFrame(() => {
        document.getElementById('transfer-panel')?.scrollIntoView({ behavior: 'smooth' })
      })
    }
  },
)
</script>

<template>
  <div class="character-page">
    <AuthSessionBar />
    <div class="character-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-button
        size="small"
        :type="isMain ? 'primary' : 'default'"
        @click="setActor('main')"
      >
        本尊
      </el-button>
      <el-button
        size="small"
        :type="isMain ? 'default' : 'primary'"
        @click="setActor('avatar')"
      >
        化身
      </el-button>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
      class="character-alert"
    />

    <template v-if="isMain">
      <div class="character-grid">
        <aside class="character-left">
          <CharacterPanel :character="characterStore.character">
            <template #header-extra>
              <el-button
                v-if="canWudao"
                type="warning"
                size="small"
                @click="router.push('/dao?actor=main')"
              >
                悟道
              </el-button>
            </template>
          </CharacterPanel>
        </aside>
        <main class="character-right">
          <EquipmentSlotsPanel @log="pushLog" />
          <ConstitutionPanel @log="pushLog" />
          <CharacterTechniquesPanel @log="pushLog" />
          <DivineAbilityPanel @log="pushLog" />
          <el-card v-if="gameLogStore.entries.length" shadow="never" class="character-log">
            <template #header>
              <el-text tag="b" size="small">操作提示</el-text>
            </template>
            <el-text
              v-for="e in gameLogStore.entries.slice(-5)"
              :key="e.id"
              size="small"
              class="log-line"
            >
              {{ e.message }}
            </el-text>
          </el-card>
        </main>
      </div>
    </template>

    <template v-else>
      <el-alert
        v-if="inTribulation"
        title="渡劫中：化身不可上阵；挂机请到大厅修炼区"
        type="warning"
        show-icon
        :closable="false"
        class="character-alert"
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
          <el-card v-if="gameLogStore.entries.length" shadow="never" class="character-log">
            <template #header>
              <el-text tag="b" size="small">操作提示</el-text>
            </template>
            <el-text
              v-for="e in gameLogStore.entries.slice(-5)"
              :key="e.id"
              size="small"
              class="log-line"
            >
              {{ e.message }}
            </el-text>
          </el-card>
        </main>
      </div>
      <el-skeleton v-else animated :rows="6" />
    </template>
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
  flex-wrap: wrap;
}

.character-alert {
  margin-bottom: 1rem;
}

.avatar-empty {
  max-width: 520px;
  margin: 0 auto;
}

.dismiss-btn {
  width: fit-content;
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
