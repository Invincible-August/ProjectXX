<script setup lang="ts">
/**
 * 灵宠图鉴：注册表投影 + seen/caught（N4）。
 */
import type { PetCatalogSpecies } from '../../types/pets'

defineProps<{
  species: PetCatalogSpecies[]
}>()

function statusLabel(status: string): string {
  if (status === 'caught') return '已捕获'
  if (status === 'seen') return '已遇见'
  return '未遇见'
}

function statusType(status: string): 'success' | 'warning' | 'info' {
  if (status === 'caught') return 'success'
  if (status === 'seen') return 'warning'
  return 'info'
}
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b">灵宠图鉴</el-text>
    </template>
    <el-text type="info" size="small" class="hint">
      物种来自配置注册表；后台/YAML 新增后刷新即可同步。
    </el-text>
    <el-empty v-if="species.length === 0" description="图鉴为空" :image-size="48" />
    <div v-for="item in species" :key="item.species_id" class="dex-row">
      <div class="dex-main">
        <el-text tag="b" size="small">{{ item.name }}</el-text>
        <el-tag size="small">{{ item.race_name || item.race }}</el-tag>
        <el-tag size="small" type="warning">{{ item.rarity }}</el-tag>
        <el-tag size="small" :type="statusType(item.status)">
          {{ statusLabel(item.status) }}
        </el-tag>
      </div>
      <el-text size="small" type="info">
        攻{{ item.base_atk }}/血{{ item.base_hp }}/速{{ item.base_speed }}
      </el-text>
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.5rem;
}
.dex-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem;
  margin-bottom: 0.35rem;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.03);
}
.dex-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}
</style>
