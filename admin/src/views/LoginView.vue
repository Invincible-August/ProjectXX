<template>
  <div class="login-page">
    <section class="login-card">
      <p class="brand">Project修仙</p>
      <h1>运营后台</h1>
      <p class="hint">独立鉴权；与玩家账号 / DEV GM 分离</p>
      <el-form @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
          登录
        </el-button>
      </el-form>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminAuthStore } from '../stores/auth'

const auth = useAdminAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('admin')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}
.login-card {
  width: min(420px, 100%);
  background: var(--adm-panel);
  border: 1px solid var(--adm-border);
  padding: 32px 28px;
  box-shadow: 0 18px 40px rgba(28, 25, 20, 0.08);
}
.brand {
  margin: 0;
  font-size: 13px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--adm-accent);
  font-weight: 700;
}
h1 {
  margin: 6px 0 4px;
  font-size: 28px;
}
.hint {
  margin: 0 0 20px;
  color: #5c564c;
  font-size: 13px;
}
.error {
  color: #a33;
  margin-top: 12px;
}
</style>
