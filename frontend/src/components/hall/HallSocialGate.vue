<script setup lang="ts">
/**
 * 大厅社交 / 宗门门闸：入口 + 道友/组队/交易规则主提示。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCharacterStore } from '../../stores/character'

const router = useRouter()
const characterStore = useCharacterStore()

const sect = computed(() => characterStore.character?.sect ?? null)
const inSect = computed(() => Boolean(sect.value?.in_sect))
const sectLabel = computed(() => {
  if (!sect.value) return '宗门大厅 · 拜入 / 任务 / 兑宠'
  if (!sect.value.in_sect) return sect.value.hint_zh || '散修 · 可拜入或自建'
  return `${sect.value.name || '宗门'} · 贡献 ${sect.value.contrib}`
})
</script>

<template>
  <el-card id="hall-social-gate" shadow="never" class="social-gate">
    <template #header>
      <el-text tag="b">宗门与社交（M7）</el-text>
    </template>

    <div class="gate-grid">
      <div
        class="gate-card"
        :class="{ emphasize: !inSect }"
        @click="router.push(inSect ? '/sect?mode=status' : '/sect?mode=join')"
      >
        <el-badge :is-dot="!inSect" type="success">
          <el-button type="primary" size="small">
            {{ inSect ? '宗门' : '去入宗' }}
          </el-button>
        </el-badge>
        <el-text size="small" type="info">{{ sectLabel }}</el-text>
      </div>

      <div class="gate-row">
        <el-button size="small" @click="router.push('/friends')">道友</el-button>
        <el-button size="small" @click="router.push('/party')">队伍</el-button>
        <el-button size="small" @click="router.push('/market')">坊市</el-button>
        <el-button size="small" @click="router.push('/social')">社交</el-button>
        <el-button size="small" @click="router.push('/dual-cultivation')">双修</el-button>
        <el-button size="small" @click="router.push('/shop')">天道商店</el-button>
      </div>

      <el-alert
        class="rules-alert"
        type="warning"
        :closable="false"
        show-icon
        title="社交规则（请先看这里）"
      >
        <ul class="rules-list">
          <li>
            <b>道友</b>：先结交道友，再私聊 / 赠礼 / 面交 / 化身助战；组队请到队伍页。
          </li>
          <li>
            <b>组队</b>：在<strong>队伍页</strong>建队 / 接受邀请；仅队长可邀请与踢人；双方须在线且已是道友；聊天坞「队伍」仅发言，不可发机缘。
          </li>
          <li>
            <b>交易（面交）</b>：须已是道友且双方在线；对方接受 → 摆货 → 锁定 → 双方确认。
          </li>
          <li>
            <b>聊天 / 机缘</b>：世界与宗门可发言并<b>发机缘</b>；私聊、师承、队伍可发言但<b>不可发机缘</b>。私聊未读按「人数」提示（一人未读显示 1，与消息条数无关）。
          </li>
        </ul>
      </el-alert>
    </div>
  </el-card>
</template>

<style scoped>
.social-gate {
  transition: box-shadow 0.2s ease;
}

.social-gate:hover {
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.12);
}

.gate-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.gate-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  padding: 0.25rem 0;
  border-radius: 4px;
  transition: background 0.15s ease;
}

.gate-card:hover {
  background: rgba(64, 158, 255, 0.06);
}

.gate-card.emphasize {
  background: rgba(64, 158, 255, 0.08);
  padding: 0.4rem 0.35rem;
}

.gate-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.rules-alert {
  margin-top: 0.15rem;
}

.rules-list {
  margin: 0.35rem 0 0;
  padding-left: 1.1rem;
  line-height: 1.55;
  font-size: 0.85rem;
}

.rules-list li + li {
  margin-top: 0.35rem;
}
</style>
