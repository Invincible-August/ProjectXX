<script setup lang="ts">
/**
 * 邮件收件箱：列表 / 已读 / 领取附件。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useMailStore } from '../../stores/mail'
import type { MailItem } from '../../types/mail'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const mailStore = useMailStore()
const busy = ref(false)
const loadError = ref('')
const selected = ref<MailItem | null>(null)

/** 送信表单 */
const toName = ref('')
const subjectZh = ref('道友来信')
const bodyZh = ref('')

onMounted(async () => {
  loadError.value = ''
  const err = await mailStore.refresh()
  if (err) {
    loadError.value = err
    emit('log', err, 'warning')
  }
})

function selectMail(row: MailItem): void {
  selected.value = row
  if (!row.is_read) {
    void mailStore.markRead(row.id).then((err) => {
      if (err) emit('log', err, 'warning')
    })
  }
}

async function onClaim(row: MailItem): Promise<void> {
  if (busy.value || !row.can_claim) return
  busy.value = true
  try {
    const err = await mailStore.claim(row.id)
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '附件已入包')
    emit('log', mailStore.lastMessage || '已领取附件', 'success')
    selected.value = mailStore.items.find((m) => m.id === row.id) ?? null
  } finally {
    busy.value = false
  }
}

async function onSend(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const err = await mailStore.sendPlayerMail({
      to_name: toName.value,
      subject_zh: subjectZh.value,
      body_zh: bodyZh.value,
    })
    if (err) {
      ElMessage.error(err)
      emit('log', err, 'warning')
      return
    }
    ElMessage.success(mailStore.lastMessage || '已送信')
    emit('log', mailStore.lastMessage || '已送信', 'success')
    toName.value = ''
    bodyZh.value = ''
  } finally {
    busy.value = false
  }
}

function attachSummary(row: MailItem): string {
  if (!row.has_attachments) return '无附件'
  const parts: string[] = []
  const stones = Number(row.attachments?.spirit_stones ?? 0)
  if (stones > 0) parts.push(`${stones} 灵石`)
  for (const line of row.attachments?.items ?? []) {
    parts.push(`${line.item_id}×${line.quantity}`)
  }
  return parts.join(' · ') || '有附件'
}
</script>

<template>
  <el-card shadow="never" class="mail-panel">
    <template #header>
      <div class="hdr">
        <el-text tag="b">邮箱</el-text>
        <el-text size="small" type="info">未读 {{ mailStore.unread }}</el-text>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="hint"
    />

    <div class="mail-grid">
      <div class="mail-list">
        <el-empty
          v-if="!mailStore.items.length"
          description="暂无邮件"
          :image-size="48"
        />
        <button
          v-for="row in mailStore.items"
          :key="row.id"
          type="button"
          class="mail-row"
          :class="{ active: selected?.id === row.id, unread: !row.is_read }"
          @click="selectMail(row)"
        >
          <div class="row-top">
            <el-text size="small" type="info">{{ row.mail_kind_label_zh }}</el-text>
            <el-text tag="b" size="small">{{ row.subject_zh }}</el-text>
          </div>
          <el-text size="small" truncated>{{ row.from_name }} · {{ attachSummary(row) }}</el-text>
        </button>
      </div>

      <div class="mail-detail" v-if="selected">
        <el-text tag="b">{{ selected.subject_zh }}</el-text>
        <el-text size="small" type="info" class="meta">
          来自 {{ selected.from_name }} · {{ selected.mail_kind_label_zh }}
        </el-text>
        <p class="body">{{ selected.body_zh }}</p>
        <el-text size="small">附件：{{ attachSummary(selected) }}</el-text>
        <div class="actions">
          <el-button
            type="primary"
            size="small"
            :disabled="!selected.can_claim || busy"
            @click="onClaim(selected)"
          >
            领取附件
          </el-button>
        </div>
      </div>
      <el-empty v-else description="选择一封邮件查看" :image-size="48" />
    </div>

    <el-divider />
    <el-text tag="b" size="small">写一封无附件信</el-text>
    <div class="compose">
      <el-input v-model="toName" placeholder="对方道号" size="small" clearable />
      <el-input v-model="subjectZh" placeholder="标题" size="small" />
      <el-input
        v-model="bodyZh"
        type="textarea"
        :rows="2"
        placeholder="正文"
        size="small"
      />
      <el-button type="primary" size="small" :loading="busy" @click="onSend">
        送信
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.hint {
  margin-bottom: 0.75rem;
}
.mail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
  gap: 0.75rem;
}
.mail-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  max-height: 320px;
  overflow: auto;
}
.mail-row {
  text-align: left;
  border: 1px solid var(--el-border-color-lighter);
  background: transparent;
  border-radius: 6px;
  padding: 0.45rem 0.55rem;
  cursor: pointer;
}
.mail-row.unread {
  border-color: var(--el-color-primary-light-5);
}
.mail-row.active {
  background: var(--el-fill-color-light);
}
.row-top {
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
  margin-bottom: 0.15rem;
}
.mail-detail {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.meta {
  display: block;
}
.body {
  white-space: pre-wrap;
  margin: 0.25rem 0;
  font-size: 0.9rem;
}
.actions {
  margin-top: 0.35rem;
}
.compose {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-top: 0.5rem;
}
@media (max-width: 720px) {
  .mail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
