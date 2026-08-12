<script setup lang="ts">
/**
 * 大道资源权威面板：本命道 · 道值 · 等级 · 经验 · 锁定态。
 */
import { computed } from 'vue'
import type { DaoPublic } from '../../types/dao'
import { daoLabel } from '../../utils/daoLabel'

const props = defineProps<{
  dao: DaoPublic | null
}>()

const fateName = computed(() =>
  daoLabel(props.dao?.fate_dao_id, props.dao?.fate_dao_label),
)

const expRatio = computed(() => {
  if (!props.dao) return 0
  const need = props.dao.exp_to_next
  if (!need || need <= 0) return 0
  return Math.min(100, Math.round((props.dao.exp / need) * 100))
})
</script>

<template>
  <el-card shadow="never" class="dao-status">
    <template #header>
      <el-text tag="b">本命大道</el-text>
    </template>

    <el-empty v-if="!dao" description="暂无大道数据" :image-size="48" />

    <div v-else class="status-grid">
      <div class="row">
        <el-text type="info" size="small">本命道</el-text>
        <el-text tag="b">{{ fateName }}</el-text>
        <el-tag v-if="dao.locked" size="small" type="warning">周目已锁定</el-tag>
        <el-tag v-else-if="!dao.fate_dao_id" size="small" type="info">未开道</el-tag>
      </div>
      <div class="row">
        <el-text type="info" size="small">道值</el-text>
        <el-text>{{ dao.qi }}</el-text>
        <el-text type="info" size="small">等级</el-text>
        <el-text>Lv.{{ dao.level }}</el-text>
        <el-text type="info" size="small">道池</el-text>
        <el-text>{{ dao.pool_count }}</el-text>
      </div>
      <div class="exp">
        <el-text size="small" type="info">
          经验 {{ dao.exp }}{{ dao.exp_to_next != null ? ` / ${dao.exp_to_next}` : '' }}
        </el-text>
        <el-progress
          v-if="dao.exp_to_next"
          :percentage="expRatio"
          :stroke-width="8"
          :show-text="false"
        />
      </div>
      <el-alert
        v-if="dao.can_open"
        title="可开辟本命大道"
        type="success"
        :closable="false"
        show-icon
      />
    </div>
  </el-card>
</template>

<style scoped>
.status-grid {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.exp {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
</style>
