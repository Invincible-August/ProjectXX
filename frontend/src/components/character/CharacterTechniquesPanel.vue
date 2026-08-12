<script setup lang="ts">
/**
 * 角色页功法一览（只读摘要；升级等仍走既有入口）。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMyTechniquesApi } from '../../api/techniques'
import type { TechniqueItem } from '../../types/techniques'

const items = ref<TechniqueItem[]>([])
const loading = ref(false)

async function reload(): Promise<void> {
  loading.value = true
  try {
    const env = await fetchMyTechniquesApi()
    if (env.code !== 0) {
      ElMessage.error(env.message || '加载功法失败')
      return
    }
    items.value = env.data?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card shadow="never" v-loading="loading">
    <template #header>
      <el-text tag="b">功法</el-text>
    </template>
    <el-empty v-if="!items.length" description="暂无功法" :image-size="48" />
    <el-table v-else :data="items" size="small" stripe>
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="track" label="轨道" width="90" />
      <el-table-column label="等级" width="100">
        <template #default="{ row }">
          {{ row.level }} / {{ row.max_level }}
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
