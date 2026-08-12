<script setup lang="ts">
/**
 * 创角页：道号 + 性别；POST /characters；成功后进大厅。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthSessionBar from '../components/AuthSessionBar.vue'
import { useAuthStore } from '../stores/auth'
import { useCharacterStore } from '../stores/character'
import { validateCharacterName } from '../utils/characterName'

const router = useRouter()
const authStore = useAuthStore()
const characterStore = useCharacterStore()

const name = ref('')
const gender = ref<'male' | 'female' | ''>('')
const tipMessage = ref('')
const tipIsError = ref(false)
const submitLoading = ref(false)

const nameError = computed(() => {
  if (!name.value) return ''
  return validateCharacterName(name.value) ?? ''
})

/**
 * 若已有角色则直接进大厅。
 */
onMounted(() => {
  if (authStore.hasCharacter) {
    void router.replace('/hall')
  }
})

/**
 * 提交创角；成功后进入大厅。
 */
async function onSubmit(): Promise<void> {
  tipMessage.value = ''
  const err = validateCharacterName(name.value)
  if (err) {
    tipIsError.value = true
    tipMessage.value = err
    return
  }
  if (gender.value !== 'male' && gender.value !== 'female') {
    tipIsError.value = true
    tipMessage.value = '请选择道途阴阳（乾道/坤道）'
    return
  }
  submitLoading.value = true
  try {
    await characterStore.create(name.value, gender.value)
    tipIsError.value = false
    tipMessage.value = '创角成功，正在进入大厅…'
    await router.replace('/hall')
  } catch (e: unknown) {
    tipIsError.value = true
    tipMessage.value = e instanceof Error ? e.message : '创角失败'
  } finally {
    submitLoading.value = false
  }
}
</script>

<template>
  <div style="max-width: 480px; margin: 0 auto; padding: 1rem">
    <AuthSessionBar />

    <el-card shadow="never">
      <template #header>
        <el-text tag="b">创建角色</el-text>
      </template>

      <el-text type="info" style="display: block; margin-bottom: 1rem">
        踏入修仙之路，先定道号与道途阴阳。初始境界为锻体一层；性别选定后不可自行更改（影响双修与四榜）。
      </el-text>

      <el-form label-position="top" @submit.prevent="onSubmit">
        <el-form-item
          label="道号"
          :error="nameError || undefined"
          required
        >
          <el-input
            v-model="name"
            maxlength="16"
            show-word-limit
            placeholder="2～16 字，中文 / 字母 / 数字"
            clearable
            @keyup.enter="onSubmit"
          />
        </el-form-item>

        <el-form-item label="道途阴阳" required>
          <el-radio-group v-model="gender">
            <el-radio-button value="male">乾道（男）</el-radio-button>
            <el-radio-button value="female">坤道（女）</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-alert
          v-if="tipMessage"
          :title="tipMessage"
          :type="tipIsError ? 'error' : 'success'"
          show-icon
          :closable="false"
          style="margin-bottom: 1rem"
        />

        <el-button
          type="primary"
          native-type="submit"
          :loading="submitLoading"
          style="width: 100%"
        >
          踏入仙途
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>
