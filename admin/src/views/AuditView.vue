<template>
  <div>
    <header class="head">
      <h1>操作审计</h1>
      <el-button size="small" @click="load">刷新</el-button>
    </header>
    <el-table :data="logs" border stripe>
      <el-table-column prop="created_at" label="时间" width="200" />
      <el-table-column prop="username" label="操作者" width="120" />
      <el-table-column prop="action" label="动作" width="120" />
      <el-table-column prop="domain_id" label="域" width="120" />
      <el-table-column prop="summary" label="摘要" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchAuditLogs } from '../api/config'
import type { AuditLogRow } from '../types/api'

const logs = ref<AuditLogRow[]>([])

async function load() {
  const data = await fetchAuditLogs()
  logs.value = data.logs
}

onMounted(() => {
  void load().catch(console.error)
})
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.head h1 {
  margin: 0;
}
</style>
