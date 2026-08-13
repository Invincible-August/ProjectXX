<script setup lang="ts">
/**
 * 登录壳页：同页切换「登录 / 注册 / 忘记密码」。
 * 登录支持：邮箱/手机+密码、手机+短信验证码。
 * 注册字段由后端 REGISTER_REQUIRE_* 开关控制；全关时仅邮箱+密码。
 */
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { registerApi } from '../api/auth'
import { fetchHealthApi } from '../api/server'
import {
  confirmEmailCodeApi,
  confirmSmsCodeApi,
  fetchVerificationModesApi,
  sendEmailCodeApi,
  sendSmsCodeApi,
  submitIdVerifyApi,
} from '../api/verification'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import type { LoginMethod, RegisterPayload } from '../types/auth'
import { getRememberMe } from '../utils/storage'
import { clearLastPlayPath } from '../utils/safeRedirect'

/** 当前展示的表单模式（同页切换，不加载新路由页） */
type AuthFormMode = 'login' | 'register' | 'forgot'

/** 发送验证码冷却秒数（与后端默认发送间隔一致） */
const SEND_COOLDOWN_SECONDS = 60

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const mode = ref<AuthFormMode>('login')
/** 登录子方式：密码 / 短信 */
const loginMethod = ref<LoginMethod>('password')
const submitLoading = ref(false)
/** 「检测状态」按钮独立 loading */
const statusLoading = ref(false)
const tipMessage = ref('')
const tipIsError = ref(false)

/** 后端核验是否处于 DEBUG（用于提示固定验证码） */
const verifyDebug = ref(true)
const idVerifyMode = ref('format')
/** 注册材料开关（与 GET /verification/modes 同步） */
const registerRequirePhone = ref(false)
const registerRequireRealName = ref(false)
const registerRequireEmailCode = ref(false)

/** 邮箱验证码弹窗 */
const emailCodeDialogVisible = ref(false)
const emailDialogSending = ref(false)
const emailDialogConfirming = ref(false)

const loginForm = reactive({
  /** 密码登录：邮箱或手机号 */
  account: '',
  password: '',
  /** 短信登录手机号 */
  phone: '',
  /** 短信登录验证码 */
  smsCode: '',
  /** 默认勾选：关闭浏览器后仍可通过 refresh 恢复登录 */
  rememberMe: getRememberMe(),
})

const registerForm = reactive({
  password: '',
  passwordConfirm: '',
  email: '',
  phone: '',
  /** 短信验证码（用户输入） */
  smsCode: '',
  /** 邮箱验证码（用户输入） */
  emailCode: '',
  realName: '',
  idCard: '',
})

/** 发码按钮冷却剩余秒数；为 0 时可再次发送 */
const smsCooldown = ref(0)
const emailCooldown = ref(0)
/** 登录页短信发码冷却（与注册共用逻辑但独立计时，避免互相干扰） */
const loginSmsCooldown = ref(0)
const smsSending = ref(false)
const emailSending = ref(false)
const loginSmsSending = ref(false)

let smsTimer: ReturnType<typeof setInterval> | null = null
let emailTimer: ReturnType<typeof setInterval> | null = null
let loginSmsTimer: ReturnType<typeof setInterval> | null = null

const forgotForm = reactive({
  account: '',
})

const titleText = computed(() => {
  if (mode.value === 'register') return '注册'
  if (mode.value === 'forgot') return '忘记密码'
  return '登录'
})

/** 注册卡片更宽，容纳核验字段 */
const cardMaxWidth = computed(() =>
  mode.value === 'register' ? '440px' : '360px',
)

/**
 * 启动发送冷却倒计时。
 *
 * @param kind - 注册短信 / 注册邮箱 / 登录短信
 */
function startCooldown(kind: 'sms' | 'email' | 'loginSms'): void {
  if (kind === 'sms') {
    smsCooldown.value = SEND_COOLDOWN_SECONDS
    if (smsTimer) clearInterval(smsTimer)
    smsTimer = setInterval(() => {
      smsCooldown.value -= 1
      if (smsCooldown.value <= 0 && smsTimer) {
        clearInterval(smsTimer)
        smsTimer = null
      }
    }, 1000)
    return
  }
  if (kind === 'loginSms') {
    loginSmsCooldown.value = SEND_COOLDOWN_SECONDS
    if (loginSmsTimer) clearInterval(loginSmsTimer)
    loginSmsTimer = setInterval(() => {
      loginSmsCooldown.value -= 1
      if (loginSmsCooldown.value <= 0 && loginSmsTimer) {
        clearInterval(loginSmsTimer)
        loginSmsTimer = null
      }
    }, 1000)
    return
  }
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

/** 组件卸载时清理倒计时，避免泄漏。 */
onUnmounted(() => {
  if (smsTimer) clearInterval(smsTimer)
  if (emailTimer) clearInterval(emailTimer)
  if (loginSmsTimer) clearInterval(loginSmsTimer)
})

/**
 * 拉取核验 modes（登录短信提示、注册字段开关、身份证模式）。
 */
async function loadVerificationModes(): Promise<void> {
  try {
    const envelope = await fetchVerificationModesApi()
    if (envelope.code === 0 && envelope.data) {
      verifyDebug.value = envelope.data.debug
      idVerifyMode.value = envelope.data.id_verify_mode
      registerRequirePhone.value = envelope.data.register_require_phone
      registerRequireRealName.value = envelope.data.register_require_real_name
      registerRequireEmailCode.value = envelope.data.register_require_email_code
    }
  } catch {
    // 拉取失败不阻断页面；开关保持默认 false（仅邮箱+密码）
  }
}

/** 支持从 /register 重定向带来的 ?mode=register 直接打开注册表单。 */
onMounted(() => {
  void loadVerificationModes()
  if (route.query.mode === 'register') {
    void switchMode('register')
  }
})

/**
 * 切换表单模式；进入注册时拉取核验 modes。
 *
 * @param next - 目标表单模式
 */
async function switchMode(next: AuthFormMode): Promise<void> {
  mode.value = next
  tipMessage.value = ''
  tipIsError.value = false
  loginForm.password = ''
  loginForm.smsCode = ''
  registerForm.password = ''
  registerForm.passwordConfirm = ''
  registerForm.smsCode = ''
  registerForm.emailCode = ''

  if (next === 'register') {
    await loadVerificationModes()
    if (verifyDebug.value) {
      showTip(
        '当前为测试模式（DEBUG）：验证码可用 000000',
        false,
      )
    }
  }
}

/**
 * 在表单下方显示简短提示。
 *
 * @param message - 提示文案
 * @param isError - 为 true 时按错误样式展示
 */
function showTip(message: string, isError = false): void {
  tipMessage.value = message
  tipIsError.value = isError
}

/**
 * 从 Axios / 业务信封失败中提取可读错误信息。
 *
 * @param error - 捕获到的未知错误
 */
function resolveErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { message?: string } | undefined
    if (data?.message) return data.message
    if (error.code === 'ERR_NETWORK') {
      return '无法连接后端：浏览器连不上 :8000（请先启动 uvicorn，或检查防火墙 / 地址是否为 127.0.0.1）'
    }
    return error.message || '请求失败'
  }
  if (error instanceof Error) return error.message
  return '未知错误'
}

/** 粗检大陆手机号。 */
function isValidPhone(phone: string): boolean {
  return /^1\d{10}$/.test(phone)
}

/** 粗检邮箱。 */
function isValidEmail(email: string): boolean {
  const normalized = email.trim()
  return (
    normalized.includes('@') &&
    !normalized.startsWith('@') &&
    !normalized.endsWith('@')
  )
}

/**
 * 密码登录账号：邮箱或手机号至少一种格式正确。
 *
 * @param account - 用户输入
 */
function isValidLoginAccount(account: string): boolean {
  const normalized = account.trim()
  return isValidPhone(normalized) || isValidEmail(normalized)
}

/** 粗检 18 位身份证（末位可为 X）。 */
function isValidIdCard(idCard: string): boolean {
  return /^\d{17}[\dXx]$/.test(idCard.trim())
}

/**
 * 登录页：发送短信验证码。
 */
async function onSendLoginSmsCode(): Promise<void> {
  if (loginSmsSending.value || loginSmsCooldown.value > 0 || submitLoading.value) {
    return
  }
  const phone = loginForm.phone.trim()
  if (!isValidPhone(phone)) {
    showTip('请先填写正确的 11 位手机号', true)
    return
  }
  loginSmsSending.value = true
  tipMessage.value = ''
  try {
    const envelope = await sendSmsCodeApi(phone)
    if (envelope.code !== 0) {
      showTip(envelope.message || `发送失败（code=${envelope.code}）`, true)
      return
    }
    startCooldown('loginSms')
    showTip(
      verifyDebug.value
        ? '短信验证码已发送（测试模式可填 000000）'
        : '短信验证码已发送，请查收',
      false,
    )
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    loginSmsSending.value = false
  }
}

/**
 * 注册：发送短信验证码。
 */
async function onSendSmsCode(): Promise<void> {
  if (smsSending.value || smsCooldown.value > 0 || submitLoading.value) return
  const phone = registerForm.phone.trim()
  if (!isValidPhone(phone)) {
    showTip('请先填写正确的 11 位手机号', true)
    return
  }
  smsSending.value = true
  tipMessage.value = ''
  try {
    const envelope = await sendSmsCodeApi(phone)
    if (envelope.code !== 0) {
      showTip(envelope.message || `发送失败（code=${envelope.code}）`, true)
      return
    }
    startCooldown('sms')
    showTip(
      verifyDebug.value
        ? '短信验证码已发送（测试模式可填 000000）'
        : '短信验证码已发送，请查收',
      false,
    )
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    smsSending.value = false
  }
}

/**
 * 注册：发送邮箱验证码（弹窗内「重新发送」与打开弹窗时共用）。
 */
async function onSendEmailCode(): Promise<void> {
  if (emailSending.value || emailCooldown.value > 0) return
  const email = registerForm.email.trim()
  if (!isValidEmail(email)) {
    showTip('请先填写正确的邮箱地址', true)
    return
  }
  emailSending.value = true
  emailDialogSending.value = true
  tipMessage.value = ''
  try {
    const envelope = await sendEmailCodeApi(email)
    if (envelope.code !== 0) {
      showTip(envelope.message || `发送失败（code=${envelope.code}）`, true)
      return
    }
    startCooldown('email')
    showTip(
      verifyDebug.value
        ? '邮箱验证码已发送（测试模式可填 000000）'
        : '邮箱验证码已发送，请查收',
      false,
    )
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    emailSending.value = false
    emailDialogSending.value = false
  }
}

/** 注册主表单校验（不含邮箱验证码；验证码在弹窗内校验）。通过返回 null。 */
function validateRegisterForm(): string | null {
  if (!isValidEmail(registerForm.email)) {
    return '请填写有效邮箱'
  }
  if (registerRequirePhone.value) {
    if (!isValidPhone(registerForm.phone.trim())) {
      return '请填写 11 位手机号'
    }
    if (!registerForm.smsCode.trim()) {
      return '请填写短信验证码'
    }
  }
  const password = registerForm.password
  if (password.length < 8 || password.length > 64) {
    return '密码长度需为 8～64'
  }
  if (password !== registerForm.passwordConfirm) {
    return '两次输入的密码不一致'
  }
  if (registerRequireRealName.value) {
    if (!registerForm.realName.trim()) {
      return '请填写真实姓名'
    }
    if (!isValidIdCard(registerForm.idCard)) {
      return '请填写 18 位身份证号'
    }
  }
  return null
}

/**
 * 按开关换取所需 ticket（手机 / 邮箱 / 身份证）。
 *
 * @param emailCode - 邮箱验证码；未开启邮箱核验时可传空串
 */
async function obtainRegisterTickets(emailCode = ''): Promise<{
  smsTicket?: string
  emailTicket?: string
  idTicket?: string
} | null> {
  const tickets: {
    smsTicket?: string
    emailTicket?: string
    idTicket?: string
  } = {}

  if (registerRequirePhone.value) {
    const phone = registerForm.phone.trim()
    const smsEnvelope = await confirmSmsCodeApi(phone, registerForm.smsCode.trim())
    if (smsEnvelope.code !== 0 || !smsEnvelope.data?.ticket) {
      showTip(smsEnvelope.message || '短信验证码校验失败', true)
      return null
    }
    tickets.smsTicket = smsEnvelope.data.ticket
  }

  if (registerRequireEmailCode.value) {
    const email = registerForm.email.trim().toLowerCase()
    const emailEnvelope = await confirmEmailCodeApi(email, emailCode.trim())
    if (emailEnvelope.code !== 0 || !emailEnvelope.data?.ticket) {
      showTip(emailEnvelope.message || '邮箱验证码校验失败', true)
      return null
    }
    tickets.emailTicket = emailEnvelope.data.ticket
  }

  if (registerRequireRealName.value) {
    const idEnvelope = await submitIdVerifyApi(
      registerForm.realName.trim(),
      registerForm.idCard.trim(),
    )
    if (idEnvelope.code !== 0 || !idEnvelope.data?.ticket) {
      showTip(idEnvelope.message || '身份证核验失败', true)
      return null
    }
    tickets.idTicket = idEnvelope.data.ticket
  }

  return tickets
}

/**
 * 组装注册请求并提交；成功后切回登录。
 *
 * @param tickets - 已拿到的核验票（可空对象）
 */
async function submitRegister(
  tickets: {
    smsTicket?: string
    emailTicket?: string
    idTicket?: string
  },
): Promise<boolean> {
  const payload: RegisterPayload = {
    password: registerForm.password,
    email: registerForm.email.trim().toLowerCase(),
  }
  if (registerRequirePhone.value) {
    payload.phone = registerForm.phone.trim()
    payload.sms_ticket = tickets.smsTicket
  }
  if (registerRequireEmailCode.value) {
    payload.email_ticket = tickets.emailTicket
  }
  if (registerRequireRealName.value) {
    payload.real_name = registerForm.realName.trim()
    payload.id_card = registerForm.idCard.trim()
    payload.id_ticket = tickets.idTicket
  }

  const envelope = await registerApi(payload)
  if (envelope.code !== 0) {
    showTip(envelope.message || `注册失败（code=${envelope.code}）`, true)
    return false
  }

  loginForm.account = registerForm.email.trim().toLowerCase()
  if (registerRequirePhone.value) {
    loginForm.phone = registerForm.phone.trim()
  }
  emailCodeDialogVisible.value = false
  resetRegisterSensitiveFields()
  await switchMode('login')
  showTip('注册成功，请登录', false)
  return true
}

/**
 * 点击注册：先校验主表单；若需邮箱核验则发码并弹窗，否则直接提交。
 */
async function onRegisterClick(): Promise<void> {
  if (submitLoading.value) return
  tipMessage.value = ''

  const invalid = validateRegisterForm()
  if (invalid) {
    showTip(invalid, true)
    return
  }

  // 需要邮箱验证码：先发码，再弹窗，确认后再注册
  if (registerRequireEmailCode.value) {
    submitLoading.value = true
    try {
      await onSendEmailCode()
      registerForm.emailCode = ''
      emailCodeDialogVisible.value = true
    } finally {
      submitLoading.value = false
    }
    return
  }

  // 无需邮箱弹窗：直接换票（若有）并注册
  submitLoading.value = true
  try {
    const tickets = await obtainRegisterTickets('')
    if (!tickets) return
    await submitRegister(tickets)
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    submitLoading.value = false
  }
}

/**
 * 邮箱验证码弹窗：确认后换齐票并注册。
 */
async function onConfirmEmailCodeDialog(): Promise<void> {
  if (emailDialogConfirming.value) return
  const code = registerForm.emailCode.trim()
  if (!code) {
    showTip('请填写邮箱验证码', true)
    return
  }

  emailDialogConfirming.value = true
  tipMessage.value = ''
  try {
    const tickets = await obtainRegisterTickets(code)
    if (!tickets) return
    await submitRegister(tickets)
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    emailDialogConfirming.value = false
  }
}

/**
 * 清空注册敏感字段（切换回登录前调用）。
 */
function resetRegisterSensitiveFields(): void {
  registerForm.password = ''
  registerForm.passwordConfirm = ''
  registerForm.email = ''
  registerForm.phone = ''
  registerForm.smsCode = ''
  registerForm.emailCode = ''
  registerForm.realName = ''
  registerForm.idCard = ''
}

/**
 * 登录成功后跳转：一律大厅（或创角 / 引渡 / 渡劫等状态页），不回跳上次玩法页。
 */
async function navigateAfterLogin(): Promise<void> {
  await authStore.ensureSession()
  clearLastPlayPath()

  if (!authStore.hasCharacter) {
    await router.replace('/create-character')
    return
  }

  const characterStore = useCharacterStore()
  if (!characterStore.character) {
    try {
      await characterStore.fetchMe()
    } catch {
      await router.replace('/hall')
      return
    }
  }
  const status = characterStore.character?.status
  if (status === 'awaiting_ferry') {
    await router.replace({ path: '/reincarnation', query: { mode: 'ferry' } })
    return
  }
  if (status === 'reincarnating') {
    await router.replace({ path: '/reincarnation', query: { mode: 'newborn' } })
    return
  }
  if (status === 'tribulation') {
    await router.replace('/tribulation')
    return
  }
  await router.replace('/hall')
}

/**
 * 提交当前表单（登录 / 注册 / 忘记密码）。
 */
async function onSubmit(): Promise<void> {
  if (submitLoading.value) return
  tipMessage.value = ''

  if (mode.value === 'forgot') {
    if (!forgotForm.account.trim()) {
      showTip('请输入注册邮箱或手机号', true)
      return
    }
    showTip('忘记密码功能尚未开放（M0 未提供找回接口）', true)
    return
  }

  if (mode.value === 'register') {
    await onRegisterClick()
    return
  }

  submitLoading.value = true
  try {
    // —— 登录 ——
    if (loginMethod.value === 'sms') {
      const phone = loginForm.phone.trim()
      if (!isValidPhone(phone)) {
        showTip('请填写正确的 11 位手机号', true)
        return
      }
      if (!loginForm.smsCode.trim()) {
        showTip('请填写短信验证码', true)
        return
      }
      await authStore.login({
        login_method: 'sms',
        phone,
        sms_code: loginForm.smsCode.trim(),
        remember_me: loginForm.rememberMe,
      })
    } else {
      const account = loginForm.account.trim()
      if (!isValidLoginAccount(account) || !loginForm.password) {
        showTip('请输入邮箱或手机号，以及密码', true)
        return
      }
      await authStore.login({
        login_method: 'password',
        account,
        password: loginForm.password,
        remember_me: loginForm.rememberMe,
      })
    }

    await navigateAfterLogin()
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    submitLoading.value = false
  }
}

/** 游客入口（预留）。 */
function onGuestLogin(): void {
  if (submitLoading.value) return
  showTip('游客登录尚未开放（M0 仅支持账号注册登录）', true)
}

/**
 * 点击「检测状态」：请求 GET /health。
 */
async function checkServerStatus(): Promise<void> {
  if (statusLoading.value || submitLoading.value) return
  tipMessage.value = ''
  statusLoading.value = true
  try {
    const envelope = await fetchHealthApi()
    if (envelope.code !== 0 || !envelope.data) {
      showTip(envelope.message || `健康检查失败（code=${envelope.code}）`, true)
      return
    }
    const { status, app, env, db, time } = envelope.data
    const isDegraded = status !== 'ok' || db !== 'ok'
    showTip(
      `联调成功 · ${app} · env=${env} · status=${status} · db=${db} · ${time}`,
      isDegraded,
    )
  } catch (error: unknown) {
    showTip(resolveErrorMessage(error), true)
  } finally {
    statusLoading.value = false
  }
}
</script>

<template>
  <el-card
    shadow="hover"
    :style="{ maxWidth: cardMaxWidth, margin: '2rem auto' }"
  >
    <template #header>
      <el-text tag="b" size="large">{{ titleText }}</el-text>
    </template>

    <el-text type="info" size="small">
      Project修仙 · 邮箱 / 手机号登录注册
      <template v-if="mode === 'register' && registerRequireRealName">
        · 身份证模式 {{ idVerifyMode }}
      </template>
    </el-text>

    <el-divider />

    <!-- 登录 -->
    <el-form
      v-if="mode === 'login'"
      label-position="top"
      @submit.prevent="onSubmit"
    >
      <el-form-item label="登录方式">
        <el-radio-group v-model="loginMethod">
          <el-radio-button value="password">密码登录</el-radio-button>
          <el-radio-button value="sms">短信登录</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <template v-if="loginMethod === 'password'">
        <el-form-item label="邮箱 / 手机号">
          <el-input
            v-model="loginForm.account"
            maxlength="255"
            autocomplete="username"
            placeholder="邮箱或 11 位手机号"
            clearable
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="loginForm.password"
            type="password"
            maxlength="64"
            autocomplete="current-password"
            show-password
          />
        </el-form-item>
      </template>

      <template v-else>
        <el-form-item label="手机号">
          <div style="display: flex; gap: 0.5rem; width: 100%">
            <el-input
              v-model="loginForm.phone"
              maxlength="11"
              autocomplete="tel"
              placeholder="11 位大陆手机号"
              clearable
              style="flex: 1"
            />
            <el-button
              type="primary"
              plain
              :loading="loginSmsSending"
              :disabled="loginSmsCooldown > 0 || submitLoading"
              @click="onSendLoginSmsCode"
            >
              {{
                loginSmsCooldown > 0 ? `${loginSmsCooldown}s` : '发送验证码'
              }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="短信验证码">
          <el-input
            v-model="loginForm.smsCode"
            maxlength="8"
            placeholder="请输入短信验证码"
            clearable
          />
        </el-form-item>
      </template>

      <el-form-item>
        <el-checkbox v-model="loginForm.rememberMe">记住登录</el-checkbox>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          native-type="submit"
          :loading="submitLoading"
          style="width: 100%"
        >
          登录
        </el-button>
      </el-form-item>
    </el-form>

    <!-- 注册：顺序 邮箱 → 手机(可选) → 密码 → 实名(可选)；邮箱验证码走弹窗 -->
    <el-form
      v-else-if="mode === 'register'"
      label-position="top"
      @submit.prevent="onRegisterClick"
    >
      <el-form-item label="邮箱">
        <el-input
          v-model="registerForm.email"
          maxlength="255"
          autocomplete="email"
          placeholder="用于登录"
          clearable
        />
      </el-form-item>

      <template v-if="registerRequirePhone">
        <el-form-item label="手机号">
          <div style="display: flex; gap: 0.5rem; width: 100%">
            <el-input
              v-model="registerForm.phone"
              maxlength="11"
              autocomplete="tel"
              placeholder="11 位大陆手机号"
              clearable
              style="flex: 1"
            />
            <el-button
              type="primary"
              plain
              :loading="smsSending"
              :disabled="smsCooldown > 0 || submitLoading"
              @click="onSendSmsCode"
            >
              {{ smsCooldown > 0 ? `${smsCooldown}s` : '发送验证码' }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="短信验证码">
          <el-input
            v-model="registerForm.smsCode"
            maxlength="8"
            placeholder="请输入短信验证码"
            clearable
          />
        </el-form-item>
      </template>

      <el-form-item label="密码">
        <el-input
          v-model="registerForm.password"
          type="password"
          maxlength="64"
          autocomplete="new-password"
          placeholder="8～64 位"
          show-password
        />
      </el-form-item>
      <el-form-item label="确认密码">
        <el-input
          v-model="registerForm.passwordConfirm"
          type="password"
          maxlength="64"
          autocomplete="new-password"
          show-password
        />
      </el-form-item>

      <template v-if="registerRequireRealName">
        <el-form-item label="真实姓名">
          <el-input
            v-model="registerForm.realName"
            maxlength="64"
            placeholder="与身份证一致"
            clearable
          />
        </el-form-item>
        <el-form-item label="身份证号">
          <el-input
            v-model="registerForm.idCard"
            maxlength="18"
            placeholder="18 位身份证号"
            clearable
          />
        </el-form-item>
      </template>

      <el-form-item>
        <el-button
          type="primary"
          native-type="submit"
          :loading="submitLoading"
          style="width: 100%"
        >
          注册
        </el-button>
      </el-form-item>
    </el-form>

    <!-- 忘记密码 -->
    <el-form v-else label-position="top" @submit.prevent="onSubmit">
      <el-form-item label="邮箱 / 手机号">
        <el-input
          v-model="forgotForm.account"
          maxlength="255"
          autocomplete="username"
          placeholder="注册时使用的邮箱或手机号"
          clearable
        />
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          native-type="submit"
          :loading="submitLoading"
          style="width: 100%"
        >
          提交找回申请
        </el-button>
      </el-form-item>
    </el-form>

    <el-alert
      v-if="tipMessage"
      :title="tipMessage"
      :type="tipIsError ? 'error' : 'success'"
      :closable="false"
      show-icon
      style="margin-top: 0.5rem"
    />

    <!-- 邮箱验证码弹窗（REGISTER_REQUIRE_EMAIL_CODE=true 时） -->
    <el-dialog
      v-model="emailCodeDialogVisible"
      title="邮箱验证"
      width="360px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-text type="info" size="small">
        验证码已发送至 {{ registerForm.email.trim().toLowerCase() }}
        <template v-if="verifyDebug">（测试模式可填 000000）</template>
      </el-text>
      <el-form label-position="top" style="margin-top: 1rem" @submit.prevent>
        <el-form-item label="邮箱验证码">
          <div style="display: flex; gap: 0.5rem; width: 100%">
            <el-input
              v-model="registerForm.emailCode"
              maxlength="8"
              placeholder="请输入邮箱验证码"
              clearable
              style="flex: 1"
            />
            <el-button
              type="primary"
              plain
              :loading="emailDialogSending"
              :disabled="emailCooldown > 0"
              @click="onSendEmailCode"
            >
              {{ emailCooldown > 0 ? `${emailCooldown}s` : '重新发送' }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="emailCodeDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="emailDialogConfirming"
          @click="onConfirmEmailCodeDialog"
        >
          确认注册
        </el-button>
      </template>
    </el-dialog>

    <el-space wrap style="margin-top: 1rem">
      <el-button
        v-if="mode !== 'login'"
        link
        type="primary"
        @click="switchMode('login')"
      >
        返回登录
      </el-button>
      <el-button
        v-if="mode === 'login'"
        link
        type="primary"
        @click="switchMode('register')"
      >
        注册账号
      </el-button>
      <el-button
        v-if="mode === 'login'"
        link
        type="warning"
        @click="switchMode('forgot')"
      >
        忘记密码
      </el-button>
    </el-space>

    <el-divider />

    <!-- 纵向铺满：避免 el-button 默认 inline-flex 导致两行左右/间距不一致 -->
    <el-space direction="vertical" fill style="width: 100%">
      <el-button
        type="default"
        :loading="submitLoading"
        style="width: 100%"
        @click="onGuestLogin"
      >
        游客登录
      </el-button>
      <el-button
        type="default"
        :loading="statusLoading"
        style="width: 100%"
        @click="checkServerStatus"
      >
        检测状态
      </el-button>
    </el-space>
  </el-card>
</template>
