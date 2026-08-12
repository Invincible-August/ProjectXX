<template>
  <div>
    <header class="head">
      <h1>配置总览</h1>
      <p>YAML 底表 + 已发布覆盖层 → GameConfigBundle；发布后玩家服无发版生效。</p>
    </header>

    <el-alert
      type="info"
      :closable="false"
      title="编辑约定：每域均有「字段说明」（全路径中文）+「表格/条目」+「JSON」。境界/挂机/修为骰请打开后看「表格编辑」。与 DEV /gm 职责分离。"
      style="margin-bottom: 16px"
    />

    <el-row :gutter="16">
      <el-col :xs="24" :md="14">
        <el-table :data="domains" stripe border>
          <el-table-column prop="category_title_zh" label="类目" width="110" />
          <el-table-column prop="title" label="域" width="120" />
          <el-table-column prop="domain_id" label="ID" width="110" />
          <el-table-column prop="risk" label="风险" width="90" />
          <el-table-column label="编辑方式" width="150">
            <template #default="{ row }">
              <span v-if="row.supports_sheets">表格 </span>
              <span v-if="row.supports_entries">条目 </span>
              <span>JSON</span>
            </template>
          </el-table-column>
          <el-table-column prop="published_version" label="版本" width="80" />
          <el-table-column prop="description" label="说明" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                :disabled="!row.enabled"
                @click="$router.push(`/domains/${row.domain_id}`)"
              >
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-col>
      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>玩家服 Bundle 摘要</template>
          <pre class="json">{{ bundleText }}</pre>
          <el-button size="small" @click="reload">刷新</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchBundleSummary, fetchDomains } from '../api/config'
import type { DomainSummary } from '../types/api'

const domains = ref<DomainSummary[]>([])
const bundle = ref<Record<string, unknown> | null>(null)
const bundleText = computed(() => JSON.stringify(bundle.value, null, 2))

async function reload() {
  const [d, b] = await Promise.all([fetchDomains(), fetchBundleSummary()])
  domains.value = d.domains
  bundle.value = b
}

onMounted(() => {
  void reload().catch((err) => {
    console.error(err)
  })
})
</script>

<style scoped>
.head h1 {
  margin: 0 0 6px;
}
.head p {
  margin: 0 0 18px;
  color: #5c564c;
}
.json {
  max-height: 420px;
  overflow: auto;
  font-size: 12px;
  background: #f7f4ee;
  padding: 12px;
}
</style>
