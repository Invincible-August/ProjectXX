<script setup lang="ts">
/**
 * M7 L2+ 占位页：坊市 / 社交 / 双修 / 商店共用壳。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'

const route = useRoute()
const router = useRouter()

const title = computed(() => {
  const raw = route.meta.placeholderTitle
  return typeof raw === 'string' && raw ? raw : '玩法'
})
</script>

<template>
  <div class="placeholder-page">
    <AuthSessionBar />
    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">{{ title }}</el-text>
      <el-text type="info" size="small">M7 L2+ 待实现</el-text>
    </div>
    <el-empty :description="`${title}：M7 L2+ 待实现`" :image-size="72" />
  </div>
</template>

<style scoped>
.placeholder-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}

.page-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 0.75rem;
  margin: 0.75rem 0 1rem;
}
</style>
