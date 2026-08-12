<script setup lang="ts">
/**
 * 陨落 / 待引渡全局提示：任意死亡进入 awaiting_ferry 时弹框。
 * 「前往」进轮回引渡页；「关闭」仅关弹窗不导航。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'

const characterStore = useCharacterStore()
const route = useRoute()
const router = useRouter()

const visible = ref(false)
/** 本会话已提示过的角色 id，避免同一次待引渡反复弹 */
const dismissedForCharacterId = ref<number | null>(null)

const awaitingFerry = computed(
  () => characterStore.character?.status === 'awaiting_ferry',
)

const alreadyOnFerryPage = computed(
  () =>
    route.name === 'reincarnation' &&
    (route.query.mode === 'ferry' || !route.query.mode),
)

watch(
  () => ({
    status: characterStore.character?.status,
    id: characterStore.character?.id,
  }),
  (next, prev) => {
    if (next.status !== 'awaiting_ferry' || next.id == null) {
      if (prev?.status === 'awaiting_ferry') {
        dismissedForCharacterId.value = null
      }
      visible.value = false
      return
    }
    // 已在引渡页或本会话已关闭过 → 不强迫再弹
    if (alreadyOnFerryPage.value) return
    if (dismissedForCharacterId.value === next.id) return
    // 刚进入待引渡，或刷新后仍是待引渡且未 dismiss
    if (prev?.status !== 'awaiting_ferry' || next.id !== prev?.id) {
      visible.value = true
    } else if (!visible.value && dismissedForCharacterId.value !== next.id) {
      // 冷启动：角色已是 awaiting_ferry
      visible.value = true
    }
  },
  { immediate: true },
)

function onClose(): void {
  visible.value = false
  if (characterStore.character?.id != null) {
    dismissedForCharacterId.value = characterStore.character.id
  }
}

function onGo(): void {
  onClose()
  void router.push({ name: 'reincarnation', query: { mode: 'ferry' } })
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="魂飞魄散 · 待引渡"
    width="440px"
    :close-on-click-modal="false"
    append-to-body
    @close="onClose"
  >
    <el-text>
      你已陨落，进入待引渡状态。可前往「轮回与引渡」自救或入轮回；也可先关闭本提示，稍后再去。
    </el-text>
    <el-alert
      v-if="awaitingFerry"
      class="hint"
      type="warning"
      :closable="false"
      show-icon
      title="引渡倒计时仍在进行；超时将强制轮回。"
    />
    <template #footer>
      <el-button type="warning" @click="onGo">前往轮回与引渡</el-button>
      <el-button @click="onClose">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.hint {
  margin-top: 0.75rem;
}
</style>
