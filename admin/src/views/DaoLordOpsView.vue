<template>
  <div class="redirect-hint">正在打开道主控制台…</div>
</template>

<script setup lang="ts">
/**
 * 兼容旧书签：原「道主运营」页已并入 GM 道主控制台。
 * 路由已直接指向 DaoLordGmView；本文件仅作遗留引用兜底。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
onMounted(() => {
  void router.replace({ name: 'ops-dao-lords' })
})
</script>

<style scoped>
.redirect-hint {
  color: #5c564c;
  padding: 24px;
}
</style>
