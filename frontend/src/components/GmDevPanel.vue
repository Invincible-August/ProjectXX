<script setup lang="ts">
/**
 * 开发环境 GM 调参条：M2 扩展三池 / 境界进度 / 品阶 / 会员 / 清 pending。
 * 注意：本面板仅本地联调；正式改配置/扩内容走运营后台（admin/ · /admin/*），勿当 CMS。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  gmForceFerryTimeoutApi,
  gmForceShichenApi,
  gmForceTribulationOutcomeApi,
  gmForceTrueImmortalApi,
  gmForceWeatherApi,
  gmGrantAcceptanceConstitutionApi,
  gmLockFateDaoApi,
  gmM6QuickKitApi,
  gmMarkStoryNodeApi,
  gmOpenDaoChallengeWindowApi,
  gmOpenDaoContestNowApi,
  gmPushWorldEnvApi,
  gmSetAwaitingFerryApi,
  gmSetCharacterApi,
  gmSetDaoLordApi,
  gmSetDaoResourcesApi,
  gmSetSpiritRootTagsApi,
  gmStartTribulationApi,
} from '../api/gm'
import { useCharacterStore } from '../stores/character'
import { useWorldStore } from '../stores/world'
import type { ShichenId, WorldWeatherId } from '../types/world'

const emit = defineEmits<{
  log: [message: string, level?: 'info' | 'success' | 'warning' | 'system']
}>()

const isDev = import.meta.env.DEV
const characterStore = useCharacterStore()
const worldStore = useWorldStore()
const open = ref(false)
const busy = ref(false)
const cultivation = ref(100)
const realmProgress = ref(100)
const stones = ref(200)
const bodyPoints = ref(0)
const craftingExp = ref(0)
const gmShichen = ref<ShichenId>('noon')
const gmWeather = ref<WorldWeatherId>('clear')
/** 逗号/空格分隔；示例 thunder_root */
const spiritRootTagsInput = ref('thunder_root')
const tribOutcome = ref<'won' | 'failed' | 'fallen'>('fallen')
const storyNodeId = ref('demo_node_1')

const shichenOptions: Array<{ value: ShichenId; label: string }> = [
  { value: 'dawn', label: '清晨' },
  { value: 'noon', label: '正午' },
  { value: 'afternoon', label: '晌午' },
  { value: 'dusk', label: '傍晚' },
  { value: 'night', label: '半夜' },
  { value: 'late_night', label: '深夜' },
]

const weatherOptions: Array<{ value: WorldWeatherId; label: string }> = [
  { value: 'clear', label: '晴' },
  { value: 'overcast', label: '阴' },
  { value: 'rain', label: '雨' },
  { value: 'hurricane', label: '飓风' },
  { value: 'storm', label: '风暴' },
  { value: 'thunderstorm', label: '雷暴' },
]

async function applyQuick(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await gmSetCharacterApi({
      cultivation_points: cultivation.value,
      realm_progress: realmProgress.value,
      spirit_stones: stones.value,
      body_tempering_points: bodyPoints.value,
      crafting_exp: craftingExp.value,
    })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || `GM 失败（code=${envelope.code}）`)
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success('GM 已写入')
    emit(
      'log',
      `GM：池修为=${cultivation.value}，境界进度=${realmProgress.value}，灵石=${stones.value}`,
      'system',
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function clearPending(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await gmSetCharacterApi({ clear_offline_pending: true })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || '清除 pending 失败')
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success('已清除离线 pending')
    emit('log', 'GM：清除 offline pending', 'system')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

/** M4：一键金丹 */
async function forceJindan(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await gmSetCharacterApi({ force_jindan: true })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || 'GM 失败')
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success('已提升至金丹')
    emit('log', 'GM：一键金丹', 'system')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function grantMaterials(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await gmSetCharacterApi({ grant_craft_materials: true })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || 'GM 失败')
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success('已发放工坊材料')
    emit('log', 'GM：发放工坊材料', 'system')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function grantTestPet(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await gmSetCharacterApi({ grant_test_pet: true })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || 'GM 失败')
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success('已发放测试灵宠')
    emit('log', 'GM：发放测试灵宠', 'system')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function clearCraftJobs(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const envelope = await gmSetCharacterApi({ clear_craft_jobs: true })
    if (envelope.code !== 0 || !envelope.data) {
      throw new Error(envelope.message || 'GM 失败')
    }
    characterStore.applyCharacter(envelope.data.character)
    ElMessage.success('已清空工坊队列')
    emit('log', 'GM：清空工坊队列', 'system')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

/** 应用 GM 角色响应并可选刷新世界 */
async function applyGmCharacter(
  envelope: Awaited<ReturnType<typeof gmSetCharacterApi>>,
  logMsg: string,
  refreshWorld = false,
): Promise<void> {
  if (envelope.code !== 0 || !envelope.data) {
    throw new Error(envelope.message || 'GM 失败')
  }
  characterStore.applyCharacter(envelope.data.character)
  if (refreshWorld) await worldStore.calibrate()
  ElMessage.success(logMsg)
  emit('log', `GM：${logMsg}`, 'system')
}

async function forceShichen(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmForceShichenApi(gmShichen.value),
      `强制时辰=${gmShichen.value}`,
      true,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function forceWeather(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmForceWeatherApi(gmWeather.value),
      `强制天气=${gmWeather.value}`,
      true,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

/**
 * 写入灵根环境标签，便于验证 tag_modifiers（如雷根吃雷暴加成）。
 */
async function applySpiritRootTags(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const tags = spiritRootTagsInput.value
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean)
    await applyGmCharacter(
      await gmSetSpiritRootTagsApi(tags),
      `灵根标签=${tags.join(',') || '(清空)'}`,
      false,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function startTribulation(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmStartTribulationApi(), '一键开渡劫')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function forceTribOutcome(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmForceTribulationOutcomeApi(tribOutcome.value),
      `强制渡劫结局=${tribOutcome.value}`,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function grantAcceptConstitution(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmGrantAcceptanceConstitutionApi(),
      '发放验收体质并自动镶嵌',
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function setAwaitingFerry(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmSetAwaitingFerryApi(), '置待引渡')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function forceFerryTimeout(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmForceFerryTimeoutApi(), '强制引渡超时轮回')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function markStoryNode(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmMarkStoryNodeApi(storyNodeId.value.trim()),
      `标记 story=${storyNodeId.value}`,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

// --- M6 ---
const fateDaoId = ref('dao_flame')
const daoQi = ref(500)
const daoLevel = ref(3)
const lordDaoId = ref('dao_flame')

const sampleDaoOptions = [
  { value: 'dao_flame', label: '炎道' },
  { value: 'dao_frost', label: '霜道' },
  { value: 'dao_thunder', label: '雷道' },
  { value: 'dao_body', label: '炼体道' },
  { value: 'dao_craft', label: '器道' },
  { value: 'dao_array', label: '阵道' },
  { value: 'dao_flame_apex', label: '炎极道' },
  { value: 'dao_void', label: '虚空道' },
]

/** M6：一键联调套装（真仙+锁道+灌池+道资源+开窗+刷快照） */
async function m6QuickKit(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmM6QuickKitApi(),
      'M6 联调套装已写入（真仙/炎道/道Lv3/开窗）',
      true,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function forceTrueImmortal(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmForceTrueImmortalApi(), '已提升至真仙')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function lockFateDao(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmLockFateDaoApi(fateDaoId.value),
      `锁定本命道=${fateDaoId.value}`,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function applyDaoResources(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmSetDaoResourcesApi({ qi: daoQi.value, level: daoLevel.value }),
      `道值=${daoQi.value} 道等级=${daoLevel.value}`,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function grantAllDaoPool(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmSetCharacterApi({
        grant_dao_pool: sampleDaoOptions.map((o) => o.value),
      }),
      '已灌入全部样本道池',
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function setDaoLord(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmSetDaoLordApi(lordDaoId.value),
      `任命道主=${lordDaoId.value}`,
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function clearDaoLord(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmSetDaoLordApi(''), '已清空自己的道主身份')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function openChallengeWindow(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmOpenDaoChallengeWindowApi(), '已强制挑战开窗')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function openContestNow(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmOpenDaoContestNowApi(), '已立刻开赛（报名截止）')
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function clearDaoCooldown(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmSetCharacterApi({ clear_dao_challenge_cooldown: true }),
      '已清空挑战冷却',
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function pushWorldEnv(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(await gmPushWorldEnvApi(), '已推送 world.env', true)
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function refreshDefenseSnapshot(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmSetCharacterApi({ force_refresh_snapshot: true }),
      '已刷新防守快照（道主应战用）',
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}

async function forceYuanyingPeak(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await applyGmCharacter(
      await gmSetCharacterApi({ force_yuanying_peak: true }),
      '已设元婴大圆满',
    )
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'GM 失败'
    ElMessage.error(message)
    emit('log', message, 'warning')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card v-if="isDev" shadow="never" class="gm-card">
    <template #header>
      <div class="gm-header" @click="open = !open">
        <el-text tag="b" type="warning">调参（DEV）</el-text>
        <el-text size="small" type="info">{{ open ? '收起' : '展开' }}</el-text>
      </div>
    </template>
    <div v-show="open" class="gm-body">
      <el-form label-position="top" size="small">
        <el-form-item label="修为池">
          <el-input-number v-model="cultivation" :min="0" :step="50" />
        </el-form-item>
        <el-form-item label="境界进度">
          <el-input-number v-model="realmProgress" :min="0" :step="50" />
        </el-form-item>
        <el-form-item label="炼体度池">
          <el-input-number v-model="bodyPoints" :min="0" :step="20" />
        </el-form-item>
        <el-form-item label="制造业经验池">
          <el-input-number v-model="craftingExp" :min="0" :step="20" />
        </el-form-item>
        <el-form-item label="灵石">
          <el-input-number v-model="stones" :min="0" :step="50" />
        </el-form-item>
        <el-button type="warning" :loading="busy" @click="applyQuick">写入</el-button>
        <el-button :loading="busy" @click="clearPending">清离线 pending</el-button>
        <el-divider content-position="left">M4</el-divider>
        <el-button :loading="busy" @click="forceJindan">一键金丹</el-button>
        <el-button :loading="busy" @click="forceYuanyingPeak">一元婴圆满</el-button>
        <el-button :loading="busy" @click="grantMaterials">发材料</el-button>
        <el-button :loading="busy" @click="grantTestPet">发测试宠</el-button>
        <el-button :loading="busy" @click="clearCraftJobs">清工坊队列</el-button>
        <el-divider content-position="left">M5</el-divider>
        <el-form-item label="强制时辰">
          <el-select v-model="gmShichen" size="small" style="width: 120px">
            <el-option
              v-for="opt in shichenOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-button :loading="busy" @click="forceShichen">写入</el-button>
        </el-form-item>
        <el-form-item label="强制天气">
          <el-select v-model="gmWeather" size="small" style="width: 120px">
            <el-option
              v-for="opt in weatherOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-button :loading="busy" @click="forceWeather">写入</el-button>
        </el-form-item>
        <el-form-item label="灵根标签（逗号分隔）">
          <el-input
            v-model="spiritRootTagsInput"
            size="small"
            placeholder="thunder_root"
            style="max-width: 220px"
          />
          <el-button :loading="busy" @click="applySpiritRootTags">写入</el-button>
        </el-form-item>
        <el-button :loading="busy" type="danger" @click="startTribulation">
          一键开渡
        </el-button>
        <el-form-item label="强制渡劫结局（验收）">
          <el-select v-model="tribOutcome" size="small" style="width: 140px">
            <el-option value="fallen" label="fallen 极端失败→引渡" />
            <el-option value="failed" label="failed 失败有惩罚" />
            <el-option value="won" label="won 成功进阶" />
          </el-select>
          <el-button :loading="busy" type="danger" plain @click="forceTribOutcome">
            写入结局
          </el-button>
        </el-form-item>
        <el-button :loading="busy" @click="grantAcceptConstitution">
          发放验收体质并镶嵌
        </el-button>
        <el-button :loading="busy" type="warning" @click="setAwaitingFerry">
          置待引渡
        </el-button>
        <el-button :loading="busy" @click="forceFerryTimeout">超时轮回</el-button>
        <el-form-item label="story 节点">
          <el-input v-model="storyNodeId" size="small" />
          <el-button :loading="busy" @click="markStoryNode">标记</el-button>
        </el-form-item>
        <el-divider content-position="left">M6 大道 / 道主</el-divider>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="一键套装：真仙 + 锁炎道 + 全样本道池 + 道Lv3/道值500 + 开窗 + 刷防守快照"
          class="gm-m6-hint"
        />
        <el-button type="danger" :loading="busy" @click="m6QuickKit">
          M6 一键联调套装
        </el-button>
        <el-button :loading="busy" @click="forceTrueImmortal">一键真仙</el-button>
        <el-form-item label="锁定本命道（跳过 roll）">
          <el-select v-model="fateDaoId" size="small" style="width: 140px">
            <el-option
              v-for="opt in sampleDaoOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-button :loading="busy" @click="lockFateDao">锁定</el-button>
        </el-form-item>
        <el-form-item label="道值 / 道等级">
          <el-input-number v-model="daoQi" :min="0" :step="50" />
          <el-input-number v-model="daoLevel" :min="1" :max="20" :step="1" />
          <el-button :loading="busy" @click="applyDaoResources">写入</el-button>
        </el-form-item>
        <el-button :loading="busy" @click="grantAllDaoPool">灌满样本道池</el-button>
        <el-form-item label="任命道主">
          <el-select v-model="lordDaoId" size="small" style="width: 140px">
            <el-option
              v-for="opt in sampleDaoOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-button :loading="busy" type="warning" @click="setDaoLord">任命</el-button>
          <el-button :loading="busy" @click="clearDaoLord">清空自己</el-button>
        </el-form-item>
        <el-button :loading="busy" @click="openChallengeWindow">强制挑战开窗</el-button>
        <el-button :loading="busy" type="danger" @click="openContestNow">立刻开赛</el-button>
        <el-button :loading="busy" @click="clearDaoCooldown">清挑战冷却</el-button>
        <el-button :loading="busy" @click="refreshDefenseSnapshot">刷防守快照</el-button>
        <el-button :loading="busy" @click="pushWorldEnv">推 world.env</el-button>
        <el-text size="small" type="info">
          测完后去「大道」「道主」页；第二账号挑战前也需刷快照。
        </el-text>
      </el-form>
    </div>
  </el-card>
</template>

<style scoped>
.gm-header {
  display: flex;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.gm-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.gm-m6-hint {
  margin-bottom: 0.5rem;
}
</style>
