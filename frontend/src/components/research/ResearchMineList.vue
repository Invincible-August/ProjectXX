<script setup lang="ts">
/**
 * Finalized private research list (M8 R2).
 */
import { useRouter } from 'vue-router'
import { useResearchStore } from '../../stores/research'

const router = useRouter()
const researchStore = useResearchStore()
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <el-text tag="b" size="small">已定稿</el-text>
    </template>
    <el-empty
      v-if="!researchStore.mine.length"
      description="尚无已定稿内容，开研定稿后会出现在此"
      :image-size="48"
    />
    <el-table v-else :data="researchStore.mine" size="small" stripe>
      <el-table-column prop="label_zh" label="名称" min-width="120" />
      <el-table-column prop="source_label_zh" label="来源" width="90" />
      <el-table-column prop="revision" label="版本" width="70" />
      <el-table-column prop="kind" label="种类" width="80">
        <template #default="{ row }">
          {{
            row.kind === 'formation'
              ? '阵法'
              : row.kind === 'technique'
                ? '功法'
                : row.kind === 'talisman'
                  ? '符箓'
                  : row.kind
          }}
        </template>
      </el-table-column>
      <el-table-column label="" width="90">
        <template #default="{ row }">
          <el-button
            v-if="row.kind === 'formation'"
            link
            type="primary"
            size="small"
            @click="router.push('/formation')"
          >
            去阵法
          </el-button>
          <el-button
            v-else-if="row.kind === 'talisman'"
            link
            type="primary"
            size="small"
            @click="router.push('/workshop?branch=talisman')"
          >
            去工坊
          </el-button>
          <el-button v-else link type="primary" size="small" @click="router.push('/character')">
            去角色穿戴
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
