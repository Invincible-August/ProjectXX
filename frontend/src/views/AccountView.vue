<script setup lang="ts">
/**
 * 账号中心：资料摘要、改密弹窗、打赏账单、退出登录。
 */
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import { fetchAccountSummaryApi, fetchAccountTipsApi } from '../api/account'
import { changePasswordApi } from '../api/auth'
import {
  confirmEmailCodeApi,
  fetchVerificationModesApi,
  sendEmailCodeApi,
} from '../api/verification'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import type { AccountSummary, AccountTipItem } from '../types/account'
import { clearLastPlayPath } from '../utils/safeRedirect'

const SEND_COOLDOWN_SECONDS = 60

const router = useRouter()
const authStore = useAuthStore()
const characterStore = useCharacterStore()

const busy = ref(false)
const summaryLoading = ref(false)
const pwdDialogVisible = ref(false)
const tipsDialogVisible = ref(false)
const tipsLoading = ref(false)
const emailSending = ref(false)
const emailCooldown = ref(0)
let emailTimer: ReturnType<typeof setInterval> | null = null

const registerRequireEmailCode = ref(false)
const verifyDebug = ref(false)

const pwdForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
  emailCode: '',
})

const summary = ref<AccountSummary>({
  fate_luck: 0,
  total_recharge_amount: 0,
  ad_watch_count: 0,
})
const tipItems = ref<AccountTipItem[]>([])
const tipTotal = ref(0)

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
      return
    }
  }
  if (!characterStore.character && authStore.hasCharacter) {
    await characterStore.fetchMe()
  }
  await Promise.all([loadVerificationModes(), loadSummary()])
})

onUnmounted(() => {
  if (emailTimer) clearInterval(emailTimer)
})

async function loadVerificationModes(): Promise<void> {
  try {
    const envelope = await fetchVerificationModesApi()
    if (envelope.code === 0 && envelope.data) {
      registerRequireEmailCode.value = envelope.data.register_require_email_code
      verifyDebug.value = envelope.data.debug
    }
  } catch {
    registerRequireEmailCode.value = false
  }
}

async function loadSummary(): Promise<void> {
  summaryLoading.value = true
  try {
    const envelope = await fetchAccountSummaryApi()
    if (envelope.code === 0 && envelope.data) {
      summary.value = envelope.data
    }
  } finally {
    summaryLoading.value = false
  }
}

function startEmailCooldown(): void {
  emailCooldown.value = SEND_COOLDOWN_SECONDS
  if (emailTimer) clearInterval(emailTimer)
  emailTimer = setInterval(() => {
    emailCooldown.value -= 1
    if (emailCooldown.value <= 0 && emailTimer) {
      clearInterval(emailTimer)
      emailTimer = null
    }
  }, 1000)
}

function openPasswordDialog(): void {
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
  pwdForm.emailCode = ''
  pwdDialogVisible.value = true
}

async function onSendEmailCode(): Promise<void> {
  if (emailSending.value || emailCooldown.value > 0) return
  const email = (user.value?.email || '').trim().toLowerCase()
  if (!email) {
    ElMessage.warning('当前账号未绑定邮箱，无法发送验证码')
    return
  }
  emailSending.value = true
  try {
    const envelope = await sendEmailCodeApi(email)
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '发送失败')
      return
    }
    startEmailCooldown()
    ElMessage.success(
      verifyDebug.value ? '邮箱验证码已发送（测试模式可填 000000）' : '邮箱验证码已发送，请查收',
    )
  } finally {
    emailSending.value = false
  }
}

async function onChangePassword(): Promise<void> {
  if (busy.value) return
  const oldPwd = pwdForm.oldPassword
  const next = pwdForm.newPassword.trim()
  const confirm = pwdForm.confirmPassword.trim()
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
    let emailTicket: string | undefined
    if (registerRequireEmailCode.value) {
      const email = (user.value?.email || '').trim().toLowerCase()
      const code = pwdForm.emailCode.trim()
      if (!email) {
        ElMessage.warning('当前账号未绑定邮箱，无法完成邮箱核验')
        return
      }
      if (!code) {
        ElMessage.warning('请填写邮箱验证码')
        return
      }
      const ticketEnvelope = await confirmEmailCodeApi(email, code)
      if (ticketEnvelope.code !== 0 || !ticketEnvelope.data?.ticket) {
        ElMessage.error(ticketEnvelope.message || '邮箱验证码校验失败')
        return
      }
      emailTicket = ticketEnvelope.data.ticket
    }
    const envelope = await changePasswordApi({
      old_password: oldPwd,
      new_password: next,
      email_ticket: emailTicket,
    })
    if (envelope.code !== 0) {
      ElMessage.error(envelope.message || '修改密码失败')
      return
    }
    ElMessage.success(envelope.data?.message || '密码已更新')
    pwdDialogVisible.value = false
  } finally {
    busy.value = false
  }
}

async function openTipsDialog(): Promise<void> {
  tipsDialogVisible.value = true
  tipsLoading.value = true
  try {
    const envelope = await fetchAccountTipsApi(1, 20)
    if (envelope.code !== 0 || !envelope.data) {
      ElMessage.error(envelope.message || '加载打赏记录失败')
      return
    }
    tipItems.value = envelope.data.items
    tipTotal.value = envelope.data.total
  } finally {
    tipsLoading.value = false
  }
}

function formatPaidAt(value: string | null): string {
  if (!value) return '—'
  return value.replace('T', ' ').replace(/\+.*$/, '').replace('Z', '').slice(0, 19)
}

async function onLogout(): Promise<void> {
  clearLastPlayPath()
  authStore.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="account-page">
    <AuthSessionBar />
    <div class="page-title">
      <el-text tag="b" size="large">账号</el-text>
      <el-text type="info" size="small">资料 · 安全 · 账单 · 退出</el-text>
    </div>

    <div class="main-grid">
      <el-card shadow="never" v-loading="summaryLoading">
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
          <el-descriptions-item label="仙缘余额">{{ summary.fate_luck }}</el-descriptions-item>
          <el-descriptions-item label="累计打赏">{{ summary.total_recharge_amount }}</el-descriptions-item>
          <el-descriptions-item label="累计观看广告">{{ summary.ad_watch_count }}</el-descriptions-item>
        </el-descriptions>
        <div class="card-actions">
          <el-button type="primary" @click="openPasswordDialog">修改密码</el-button>
          <el-button @click="openTipsDialog">打赏记录</el-button>
        </div>
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

    <el-dialog
      v-model="pwdDialogVisible"
      title="修改密码"
      width="400px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form label-position="top" size="small" @submit.prevent>
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.newPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdForm.confirmPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item v-if="registerRequireEmailCode" label="邮箱验证码">
          <div class="code-row">
            <el-input
              v-model="pwdForm.emailCode"
              maxlength="8"
              placeholder="请输入邮箱验证码"
              clearable
            />
            <el-button
              type="primary"
              plain
              :loading="emailSending"
              :disabled="emailCooldown > 0"
              @click="onSendEmailCode"
            >
              {{ emailCooldown > 0 ? `${emailCooldown}s` : '发送验证码' }}
            </el-button>
          </div>
          <el-text v-if="verifyDebug" type="info" size="small">测试模式可填 000000</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="onChangePassword">确认修改</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tipsDialogVisible" title="打赏记录" width="640px">
      <el-table :data="tipItems" size="small" v-loading="tipsLoading" empty-text="暂无打赏记录">
        <el-table-column prop="paid_at" label="时间" min-width="160">
          <template #default="{ row }">{{ formatPaidAt(row.paid_at) }}</template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="100" />
        <el-table-column prop="order_no" label="单号" min-width="140" />
        <el-table-column prop="channel" label="途径" min-width="120" />
      </el-table>
      <el-text v-if="!tipsLoading" type="info" size="small" class="tip-count">
        共 {{ tipTotal }} 笔
      </el-text>
    </el-dialog>
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
.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.hint {
  display: block;
  margin-bottom: 0.75rem;
}
.code-row {
  display: flex;
  gap: 0.5rem;
  width: 100%;
}
.tip-count {
  display: block;
  margin-top: 0.5rem;
}
</style>
