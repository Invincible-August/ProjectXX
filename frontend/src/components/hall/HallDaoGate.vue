<script setup lang="ts">
/**
 * 大厅大道 / 道主门闸：入口跳转 + 角标；不执行开道事务。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'
import { useDaoLordStore } from '../../stores/daoLord'
import { daoLabel } from '../../utils/daoLabel'

const router = useRouter()
const characterStore = useCharacterStore()
const daoLordStore = useDaoLordStore()

const dao = computed(() => characterStore.character?.dao ?? null)
const daoLord = computed(() => characterStore.character?.dao_lord ?? null)
const canOpen = computed(() => Boolean(dao.value?.can_open))
const isLord = computed(() => Boolean(daoLord.value?.is_self))
const windowOpen = computed(() => daoLordStore.isWindowOpen)
const fateLabel = computed(() =>
  daoLabel(dao.value?.fate_dao_id, dao.value?.fate_dao_label),
)
</script>

<template>
  <el-card id="hall-dao-gate" shadow="never" class="dao-gate">
    <template #header>
      <el-text tag="b">大道与道主（M6）</el-text>
    </template>

    <div class="gate-grid">
      <div
        class="gate-card"
        :class="{ emphasize: canOpen }"
        @click="router.push(canOpen ? '/dao?mode=open' : '/dao')"
      >
        <el-badge :is-dot="canOpen" type="success">
          <el-button type="primary" size="small">
            {{ canOpen ? '去开道' : '大道' }}
          </el-button>
        </el-badge>
        <el-text size="small" type="info">
          {{
            canOpen
              ? '真仙可开 · 三选一本命'
              : dao?.fate_dao_id
                ? `本命：${fateLabel} · Lv.${dao?.level ?? 0}`
                : '道池图鉴 · 抵达真仙后开道'
          }}
        </el-text>
      </div>

      <div
        class="gate-card"
        :class="{ emphasize: windowOpen || isLord }"
        @click="
          router.push(
            windowOpen ? '/dao-lord?mode=contest' : '/dao-lord?mode=board',
          )
        "
      >
        <el-badge :is-dot="windowOpen" type="danger">
          <el-button
            :type="windowOpen ? 'danger' : 'default'"
            size="small"
          >
            {{ windowOpen ? '赛会进行中' : '道主' }}
          </el-button>
        </el-badge>
        <el-text size="small" type="info">
          {{
            isLord
              ? `道主印记：${daoLabel(daoLord?.dao_id, daoLord?.dao_label)}`
              : windowOpen
                ? '报名/对阵开放 · 前往道主之争'
                : '道主榜 · 道主之争报名'
          }}
        </el-text>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.dao-gate {
  transition: box-shadow 0.2s ease;
}

.dao-gate:hover {
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.12);
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
  background: rgba(64, 158, 255, 0.06);
}

.gate-card.emphasize {
  background: rgba(64, 158, 255, 0.08);
  padding: 0.4rem 0.35rem;
}
</style>
