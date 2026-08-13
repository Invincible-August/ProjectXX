<script setup lang="ts">
/**
 * 账号中心：资料摘要、修改密码、退出登录。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePasswordApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import { clearLastPlayPath } from '../utils/safeRedirect'

const router = useRouter()
const authStore = useAuthStore()
const characterStore = useCharacterStore()

const busy = ref(false)
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

const user = computed(() => authStore.user)
const displayLabel = computed(() => {
  const u = user.value
  if (!u) return '未登录'
  return u.display_name || u.email || u.phone || `用户 #${u.id}`
})

onMounted(async () => {
  if (!authStore.user) {
    try {
      await authStore.ensureSession()
    } catch {
      await router.replace('/login')
    }
  }
  if (!characterStore.character && authStore.hasCharacter) {
    await characterStore.fetchMe()
  }
})

async function onChangePassword(): Promise<void> {
  if (busy.value) return
  const oldPwd = oldPassword.value
  const next = newPassword.value.trim()
  const confirm = confirmPassword.value.trim()
  if (!oldPwd || !next) {
    ElMessage.warning('请填写原密码与新密码')
    return
  }
  if (next.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (next !== confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  busy.value = true
  try {
    const envelope = await changePasswordApi({
      old_password: oldPwd,
      new_password: next,
    })
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '修改密码失败')
      return
    }
    ElMessage.success(envelope.data?.message || '密码已更新')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } finally {
    busy.value = false
  }
}

async function onLogout(): Promise<void> {
  clearLastPlayPath()
  authStore.logout()
  // 重新登录后固定进大厅，不带 redirect
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="account-page">
    <div class="page-title">
      <el-button size="small" @click="router.push('/hall')">← 回大厅</el-button>
      <el-text tag="b" size="large">账号</el-text>
      <el-text type="info" size="small">资料 · 安全 · 退出</el-text>
    </div>

    <div class="main-grid">
      <el-card shadow="never">
        <template #header>
          <el-text tag="b">账号资料</el-text>
        </template>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="显示名">{{ displayLabel }}</el-descriptions-item>
          <el-descriptions-item label="用户 ID">{{ user?.id ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ user?.email || '—' }}</el-descriptions-item>
          <el-descriptions-item label="手机">{{ user?.phone || '—' }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            {{ characterStore.character?.name || (authStore.hasCharacter ? '已创角' : '未创角') }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <el-text tag="b">修改密码</el-text>
        </template>
        <el-form label-position="top" size="small" class="pwd-form" @submit.prevent>
          <el-form-item label="原密码">
            <el-input v-model="oldPassword" type="password" show-password autocomplete="current-password" />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="confirmPassword" type="password" show-password autocomplete="new-password" />
          </el-form-item>
          <el-button type="primary" :loading="busy" @click="onChangePassword">
            保存新密码
          </el-button>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <el-text tag="b">会话</el-text>
        </template>
        <el-text size="small" type="info" class="hint">
          退出后需重新登录；本地令牌将清除。
        </el-text>
        <el-button type="danger" @click="onLogout">退出登录</el-button>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.account-page {
  max-width: 720px;
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
.main-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.pwd-form {
  max-width: 360px;
}
.hint {
  display: block;
  margin-bottom: 0.75rem;
}
</style>
