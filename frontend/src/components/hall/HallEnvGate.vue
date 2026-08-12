<script setup lang="ts">
/**
 * 大厅环境门闸：渡劫 / 待引渡 / 祭坛入口。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'

const router = useRouter()
const characterStore = useCharacterStore()

const status = computed(() => characterStore.character?.status ?? 'normal')
const inTribulation = computed(() => status.value === 'tribulation')
const awaitingFerry = computed(() => status.value === 'awaiting_ferry')
const reincarnating = computed(() => status.value === 'reincarnating')
const reincarnationPoints = computed(
  () => characterStore.character?.reincarnation_points ?? 0,
)
</script>

<template>
  <el-card id="hall-env-gate" shadow="never" class="env-gate">
    <template #header>
      <el-text tag="b">环境与轮回（M5）</el-text>
    </template>

    <el-alert
      v-if="reincarnating"
      title="轮回新生未完成：请前往选角（灵根 / 传承 / 体质）或轮回商店"
      type="warning"
      show-icon
      :closable="false"
      class="newborn-alert"
      @click="router.push('/reincarnation?mode=newborn')"
    />

    <div class="gate-grid">
      <div
        class="gate-card"
        :class="{ emphasize: inTribulation }"
        @click="router.push('/tribulation')"
      >
        <el-badge :is-dot="inTribulation" type="danger">
          <el-button type="danger" size="small">
            {{ inTribulation ? '前往渡劫' : '渡劫' }}
          </el-button>
        </el-badge>
        <el-text size="small" type="info">
          {{ inTribulation ? '雷劫进行中' : '仅跨大境界（元婴→化神起）需渡劫；小境界可直接突破' }}
        </el-text>
      </div>

      <div
        class="gate-card"
        :class="{ emphasize: awaitingFerry || reincarnating }"
        @click="
          router.push(
            reincarnating
              ? '/reincarnation?mode=newborn'
              : '/reincarnation?mode=ferry',
          )
        "
      >
        <el-badge :is-dot="awaitingFerry || reincarnating" type="warning">
          <el-button
            :type="awaitingFerry || reincarnating ? 'warning' : 'default'"
            size="small"
          >
            {{
              reincarnating
                ? '去新生选角'
                : awaitingFerry
                  ? '去引渡'
                  : '轮回 / 引渡'
            }}
          </el-button>
        </el-badge>
        <el-text size="small" type="info">
          {{
            reincarnating
              ? '保留道号 · 选灵根/传承 · 商店'
              : awaitingFerry
                ? '待引渡·请尽快抉择'
                : '自救 · 祭坛 · 流水'
          }}
        </el-text>
      </div>

      <div class="gate-card" @click="router.push('/reincarnation?mode=altar')">
        <el-button type="primary" plain size="small" :disabled="reincarnating">
          祭坛
        </el-button>
        <el-text size="small" type="info">
          主动轮回（化神期起）· 轮回点 {{ reincarnationPoints }}
        </el-text>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.env-gate {
  transition: box-shadow 0.2s ease;
}

.env-gate:hover {
  box-shadow: 0 2px 12px rgba(230, 162, 60, 0.12);
}

.gate-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.gate-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  padding: 0.25rem 0;
  border-radius: 4px;
  transition: background 0.15s ease;
}

.gate-card:hover {
  background: rgba(230, 162, 60, 0.06);
}

.gate-card.emphasize {
  background: rgba(245, 108, 108, 0.08);
  padding: 0.4rem 0.35rem;
}

.newborn-alert {
  margin-bottom: 0.75rem;
  cursor: pointer;
}
</style>
