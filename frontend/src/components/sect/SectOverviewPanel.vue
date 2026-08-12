<script setup lang="ts">
/**
 * 宗门总览：只读展示等级 / 设施 / 增益（升级与开关在议事厅）。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchSectOverview } from '../../api/sect'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const loading = ref(false)
const data = ref<Record<string, any> | null>(null)

async function reload(): Promise<void> {
  loading.value = true
  try {
    const env = await fetchSectOverview()
    if (env.code !== 0 || !env.data) {
      ElMessage.error(env.message || '加载总览失败')
      emit('log', env.message || '加载总览失败', 'warning')
      return
    }
    data.value = env.data
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void reload()
})
</script>

<template>
  <el-card v-loading="loading" shadow="never">
    <template #header>
      <el-text tag="b">宗门总览</el-text>
    </template>
    <template v-if="data">
      <div class="meta">
        <el-text>
          {{ data.name }} · {{ data.grade_label_zh }}
          <template v-if="data.next_grade">
            （下一档 {{ data.next_grade.label_zh }}）
          </template>
          · 专精 {{ data.specialty_label_zh }} · 人数 {{ data.member_count }}/{{
            data.max_members
          }}
        </el-text>
        <el-text size="small" type="info">
          我的职位 {{ data.my_rank_label_zh }} · 贡献 {{ data.my_contrib }} · 宗门灵石库
          {{ data.spirit_stone_pool }} · 挂机 ×{{ Number(data.idle_bonus).toFixed(2) }}
        </el-text>
        <el-text v-if="data.announcement" size="small">公告：{{ data.announcement }}</el-text>
        <el-text size="small" type="info">
          升宗门等级、升级设施与开关增益请前往「议事厅」（须有权限）。
        </el-text>
      </div>

      <el-divider content-position="left">设施等级</el-divider>
      <div class="fac-list">
        <div v-for="f in data.facilities || []" :key="f.facility_id" class="fac-row">
          <el-text>
            {{ f.label_zh }} Lv.{{ f.level }}/{{ f.max_level }}
          </el-text>
        </div>
      </div>

      <el-divider content-position="left">
        已开增益（最多 {{ data.max_active_buffs }}）
      </el-divider>
      <el-empty
        v-if="!(data.active_buffs || []).length"
        description="暂无开启增益"
        :image-size="40"
      />
      <div v-else class="buff-list">
        <el-tag
          v-for="b in data.active_buffs || []"
          :key="b.buff_id"
          size="small"
          type="success"
        >
          {{ b.label_zh }}
        </el-tag>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.meta {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.fac-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.fac-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}
.buff-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
</style>
