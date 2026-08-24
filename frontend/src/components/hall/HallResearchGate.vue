<script setup lang="ts">
/**
 * 大厅 nav 增量：工坊 / 洞府（不是侧栏大卡）。
 */
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <el-button size="small" type="warning" plain @click="router.push('/workshop')">
    工坊
  </el-button>
  <el-button size="small" type="success" @click="router.push('/cave')">
    洞府
  </el-button>
</template>
