<script setup lang="ts">
/**
 * 默认运用偏好开关：本地记忆，带到 battle / craft。
 * 不负责扣道值权威。
 */
import { useDaoStore } from '../../stores/dao'

const daoStore = useDaoStore()

function onBattle(v: string | number | boolean): void {
  daoStore.setPreferBattle(Boolean(v))
}

function onCraft(v: string | number | boolean): void {
  daoStore.setPreferCraft(Boolean(v))
}
</script>

<template>
  <el-card shadow="never" class="dao-usage">
    <template #header>
      <el-text tag="b">运用偏好</el-text>
    </template>
    <el-text size="small" type="info" class="hint">
      仅记住默认勾选；实际消耗与效果以开战/开工时服务端预览与结算为准。
    </el-text>
    <div class="row">
      <el-switch
        :model-value="daoStore.preferBattleUseDao"
        active-text="战斗默认运用本命道"
        @change="onBattle"
      />
    </div>
    <div class="row">
      <el-switch
        :model-value="daoStore.preferCraftUseDao"
        active-text="工坊默认耗道值运用"
        @change="onCraft"
      />
    </div>
  </el-card>
</template>

<style scoped>
.hint {
  display: block;
  margin-bottom: 0.75rem;
}

.row {
  margin-bottom: 0.5rem;
}
</style>
