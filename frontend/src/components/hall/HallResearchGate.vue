<script setup lang="ts">
/**
 * 大厅 nav 增量：洞府（工坊/研究室为其二级页；不是侧栏大卡）。
 */
import { useRouter } from 'vue-router'
import { CAVE_PATH, CAVE_WORKSHOP_PATH } from '../../constants/cave'

const router = useRouter()
</script>

<template>
  <el-button size="small" type="warning" plain @click="router.push(CAVE_WORKSHOP_PATH)">
    工坊
  </el-button>
  <el-button size="small" type="success" @click="router.push(CAVE_PATH)">
    洞府
  </el-button>
</template>
