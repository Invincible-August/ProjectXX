<script setup lang="ts">
/**
 * 独立注册路由页（空壳）。
 * 正式注册 UI 已合并进 LoginView 同页切换；本文件保留路由占位，避免 /register 空白无说明。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

onMounted(() => {
  // 统一引导到登录页，并由用户点击「注册账号」进入注册表单
  void router.replace({ path: '/login', query: { mode: 'register' } })
})
</script>

<template>
  <el-text type="info">正在跳转到注册表单…</el-text>
</template>
