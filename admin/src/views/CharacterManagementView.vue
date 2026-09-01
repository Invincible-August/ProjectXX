<template>
  <div class="accounts-page">
    <header class="page-head">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p class="sub">{{ pageDesc }}</p>
      </div>
      <div class="toolbar">
        <el-input
          v-model="keyword"
          clearable
          placeholder="道号 / user_id / 邮箱"
          class="search"
          @keyup.enter="onSearch"
        />
        <el-button type="primary" :loading="loading" @click="onSearch">搜索</el-button>
        <el-button :disabled="loading" @click="onReset">重置</el-button>
        <span class="page-size-label">每页</span>
        <el-select v-model="pageSize" style="width: 96px" @change="onPageSizeChange">
          <el-option v-for="n in pageSizeOptions" :key="n" :value="n" :label="String(n)" />
        </el-select>
      </div>
    </header>

    <div class="batch-bar">
      <span class="batch-hint">已选 {{ selectedRows.length }} 项</span>
      <el-button
        type="danger"
        size="small"
        :disabled="!selectedRows.length || acting"
        @click="batchSoftDelete"
      >
        删除
      </el-button>
      <el-button
        type="warning"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchKill"
      >
        死亡
      </el-button>
      <el-button
        type="danger"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchReincarnate"
      >
        轮回
      </el-button>
      <el-button
        type="primary"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchBreakthroughCultivation"
      >
        修为突破
      </el-button>
      <el-button
        type="primary"
        size="small"
        plain
        :disabled="!selectedRows.length || acting"
        @click="batchBreakthroughBody"
      >
        炼体突破
      </el-button>
      <el-button
        type="success"
        size="small"
        plain
        :disabled="selectedRows.length !== 1 || acting"
        @click="openGrant(selectedRows[0])"
      >
        给予
      </el-button>
    </div>

    <div class="grid-wrap">
      <el-table
        v-loading="loading"
        :data="rows"
        border
        stripe
        size="small"
        height="520"
        class="navicat-grid"
        empty-text="暂无角色"
        row-key="id"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="42" fixed="left" />
        <el-table-column prop="id" label="角色ID" width="80" fixed="left" />
        <el-table-column prop="name" label="道号" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="user_id" label="user_id" width="110" />
        <el-table-column prop="realm_display" label="修为境界" min-width="120" show-overflow-tooltip />
        <el-table-column prop="status_label_zh" label="状态" width="88" align="center" />
        <el-table-column prop="spirit_stones" label="灵石" width="90" align="right" />
        <el-table-column label="有效" width="72" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
              {{ row.is_active ? '是' : '已删' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="快捷" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">管理</el-button>
            <el-button link type="success" size="small" @click="openGrant(row)">给予</el-button>
            <el-button link type="warning" size="small" @click="doKill(row)">死亡</el-button>
            <el-button link type="danger" size="small" @click="doReincarnate(row)">轮回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, jumper"
        background
        @current-change="load"
      />
    </div>

    <!-- 给予 -->
    <el-dialog v-model="grantVisible" title="给予道具（邮件）" width="420px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="物品种类ID">
          <el-input v-model="grantForm.itemId" placeholder="如 beginner_wood_sword" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="grantForm.quantity" :min="1" :step="1" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="grantForm.note" clearable />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitGrant">发送</el-button>
      </template>
    </el-dialog>

    <!-- 详情管理 -->
    <el-drawer
      v-model="detailVisible"
      size="720px"
      destroy-on-close
      :title="detail ? `角色 · ${detail.name}` : '角色管理'"
      @closed="onDetailClosed"
    >
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="detail">
          <p class="detail-meta">
            ID {{ detail.id }} · {{ detail.user_id }} · {{ detail.realm_display }} ·
            {{ detail.status_label_zh }}
            <el-tag v-if="!detail.is_active" type="info" size="small" class="ml">已删除</el-tag>
          </p>

          <div class="section-grid">
            <button type="button" class="section-card" @click="openAttrs">属性</button>
            <button type="button" class="section-card" @click="openStatus">状态</button>
            <button type="button" class="section-card" @click="openBag">背包</button>
            <button type="button" class="section-card" @click="openTechs">功法</button>
            <button type="button" class="section-card" @click="openRealm">境界</button>
            <button type="button" class="section-card" @click="openCraft">制造业</button>
            <button type="button" class="section-card" @click="openCurrency">货币</button>
            <button type="button" class="section-card" @click="openConstitution">体质</button>
          </div>

          <div class="detail-actions">
            <el-button size="small" type="danger" plain :loading="acting" @click="doSoftDelete(detail)">
              删除
            </el-button>
            <el-button size="small" type="warning" plain :loading="acting" @click="doKill(detail)">
              死亡
            </el-button>
            <el-button size="small" type="danger" plain :loading="acting" @click="doReincarnate(detail)">
              轮回
            </el-button>
            <el-button size="small" type="primary" plain :loading="acting" @click="doBreakCult(detail)">
              修为突破
            </el-button>
            <el-button size="small" type="primary" plain :loading="acting" @click="doBreakBody(detail)">
              炼体突破
            </el-button>
            <el-button size="small" type="success" plain @click="openGrant(detail)">给予</el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :loading="acting"
              @click="doGrantCraftTestCards(detail)"
            >
              发放自研测试卡
            </el-button>
          </div>
        </template>
      </div>
    </el-drawer>

    <!-- 属性 -->
    <el-dialog v-model="attrsVisible" title="基础属性" width="480px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item v-for="row in attrsForm" :key="row.key" :label="row.label_zh">
          <el-input-number v-model="row.value" :step="1" controls-position="right" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="attrsVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitAttrs">保存</el-button>
      </template>
    </el-dialog>

    <!-- 状态 -->
    <el-dialog v-model="statusVisible" title="角色状态" width="360px" destroy-on-close>
      <el-select v-model="statusForm" style="width: 100%">
        <el-option
          v-for="opt in statusOptions"
          :key="opt.value"
          :value="opt.value"
          :label="opt.label_zh"
        />
      </el-select>
      <template #footer>
        <el-button @click="statusVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitStatus">保存</el-button>
      </template>
    </el-dialog>

    <!-- 背包 -->
    <el-dialog v-model="bagVisible" title="背包" width="720px" destroy-on-close>
      <el-table :data="bagItems" size="small" border max-height="420" empty-text="背包为空">
        <el-table-column prop="id" label="实例ID" width="72" />
        <el-table-column prop="item_id" label="种类ID" min-width="120" show-overflow-tooltip />
        <el-table-column prop="name" label="名称" min-width="100" />
        <el-table-column prop="quantity" label="数量" width="72" />
        <el-table-column prop="bag_kind" label="袋" width="88" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              :disabled="row.unique || row.max_stack <= 1"
              @click="editBagQty(row)"
            >
              改数量
            </el-button>
            <el-button link type="warning" size="small" @click="editBagMeta(row)">改属性</el-button>
            <el-button link type="danger" size="small" @click="deleteBagItem(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 功法 -->
    <el-dialog v-model="techVisible" title="功法" width="640px" destroy-on-close>
      <div class="inline-form">
        <el-input v-model="learnTechId" placeholder="功法ID" style="width: 200px" />
        <el-button type="primary" size="small" :loading="acting" @click="submitLearnTech">学会</el-button>
      </div>
      <el-table :data="detail?.techniques || []" size="small" border max-height="400">
        <el-table-column prop="technique_id" label="功法ID" min-width="120" />
        <el-table-column prop="name" label="名称" min-width="100" />
        <el-table-column prop="level" label="等级" width="72" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="editTechLevel(row)">改等级</el-button>
            <el-button link type="danger" size="small" @click="doForgetTech(row)">遗忘</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 境界 -->
    <el-dialog v-model="realmVisible" title="境界" width="480px" destroy-on-close>
      <el-tabs v-model="realmTab">
        <el-tab-pane label="修为" name="cultivation">
          <el-form label-width="96px">
            <el-form-item label="大境界">
              <el-input v-model="realmCult.major" placeholder="如 body_tempering" />
            </el-form-item>
            <el-form-item label="小境界层">
              <el-input-number v-model="realmCult.stage" :min="1" />
            </el-form-item>
            <el-form-item label="境界进度">
              <el-input-number v-model="realmCult.progress" :min="0" />
            </el-form-item>
            <el-form-item label="修为池">
              <el-input-number v-model="realmCult.pool" :min="0" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="炼体" name="body">
          <el-form label-width="96px">
            <el-form-item label="炼体大境">
              <el-input v-model="realmBody.major" placeholder="如 refine_skin" />
            </el-form-item>
            <el-form-item label="层/期">
              <el-input-number v-model="realmBody.stage" :min="1" />
            </el-form-item>
            <el-form-item label="淬体进度">
              <el-input-number v-model="realmBody.progress" :min="0" />
            </el-form-item>
            <el-form-item label="淬体度池">
              <el-input-number v-model="realmBody.pool" :min="0" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="realmVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitRealm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 制造业 -->
    <el-dialog v-model="craftVisible" title="制造业" width="640px" destroy-on-close>
      <el-form label-width="72px" class="craft-levels">
        <el-form-item v-for="row in craftLevelsForm" :key="row.branch" :label="row.label_zh">
          <el-input-number v-model="row.level" :min="0" />
        </el-form-item>
      </el-form>
      <el-button type="primary" size="small" :loading="acting" class="mb" @click="submitCraftLevels">
        保存等级
      </el-button>
      <div class="inline-form">
        <el-input v-model="learnRecipeId" placeholder="配方ID" style="width: 200px" />
        <el-button type="success" size="small" :loading="acting" @click="submitLearnRecipe">
          学习配方
        </el-button>
      </div>
      <el-collapse>
        <el-collapse-item
          v-for="branch in craftBranches"
          :key="branch.value"
          :title="`${branch.label_zh} · 配方`"
          :name="branch.value"
        >
          <el-table
            :data="detail?.recipes_by_branch?.[branch.value] || []"
            size="small"
            border
            empty-text="无已学配方"
          >
            <el-table-column prop="recipe_id" label="配方ID" min-width="140" />
            <el-table-column prop="name" label="名称" min-width="100" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button link type="danger" size="small" @click="doForgetRecipe(row)">
                  遗忘
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>

    <!-- 货币 -->
    <el-dialog v-model="currencyVisible" title="货币（不含仙缘）" width="420px" destroy-on-close>
      <p class="dialog-hint">仙缘绑定账号，请在账号管理派发。数值须为整数且 ≥ 0。</p>
      <el-form label-width="88px">
        <el-form-item v-for="row in currencyForm" :key="row.key" :label="row.label_zh">
          <el-input-number v-model="row.amount" :min="0" :step="1" :precision="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="仙缘(只读)">
          <el-text>{{ detail?.fate_luck_readonly ?? 0 }}</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="currencyVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting" @click="submitCurrency">保存</el-button>
      </template>
    </el-dialog>

    <!-- 体质只读 -->
    <el-dialog v-model="consVisible" title="体质" width="640px" destroy-on-close>
      <h4 class="sub-h">镶嵌槽</h4>
      <el-table :data="detail?.constitution?.slots || []" size="small" border class="mb">
        <el-table-column prop="slot_type" label="槽类型" />
        <el-table-column prop="slot_index" label="序号" width="72" />
        <el-table-column prop="item_instance_id" label="物品实例" />
      </el-table>
      <h4 class="sub-h">体质物品</h4>
      <el-table :data="detail?.constitution?.items || []" size="small" border>
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="def_id" label="定义ID" min-width="120" />
        <el-table-column prop="quality" label="品质" width="88" />
        <el-table-column prop="grade" label="品阶" width="88" />
        <el-table-column prop="is_equipped" label="已镶嵌" width="80">
          <template #default="{ row }">{{ row.is_equipped ? '是' : '否' }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * 玩家角色管理：布局对齐账号管理；道号可从账号页跳转带 user_db_id。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  breakthroughBody,
  breakthroughCultivation,
  fetchCharacterDetail,
  fetchCharacterOpsSchema,
  fetchCharacters,
  forgetRecipe,
  forgetTechnique,
  grantCharacterItem,
  grantTechniqueCraftTestCards,
  killCharacter,
  learnRecipe,
  learnTechnique,
  reincarnateCharacter,
  softDeleteCharacter,
  updateCharacterBaseAttrs,
  updateCharacterCurrencies,
  updateCharacterInventory,
  updateCharacterRealm,
  updateCharacterStatus,
  updateCraftLevels,
  updateTechniqueLevel,
  type CharacterDetail,
  type CharacterListRow,
  type CharacterOpsSchema,
  type InventoryItemRow,
} from '../api/characters'

const route = useRoute()
const router = useRouter()

const schema = ref<CharacterOpsSchema | null>(null)
const loading = ref(false)
const acting = ref(false)
const rows = ref<CharacterListRow[]>([])
const selectedRows = ref<CharacterListRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const activeKeyword = ref('')
const filterUserDbId = ref<number | undefined>(undefined)

const pageSizeOptions = computed(() => schema.value?.page_sizes ?? [10, 20, 50, 100])
const pageTitle = computed(() => schema.value?.title_zh ?? '玩家管理 · 角色管理')
const pageDesc = computed(() => schema.value?.description_zh ?? '运行时角色干预')
const statusOptions = computed(() => schema.value?.status_options ?? [])
const craftBranches = computed(() => schema.value?.craft_branches ?? [])

const grantVisible = ref(false)
const grantTargetId = ref<number | null>(null)
const grantForm = reactive({ itemId: '', quantity: 1, note: '' })

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<CharacterDetail | null>(null)

const attrsVisible = ref(false)
const attrsForm = ref<{ key: string; label_zh: string; value: number }[]>([])

const statusVisible = ref(false)
const statusForm = ref('normal')

const bagVisible = ref(false)
const bagItems = computed(() => detail.value?.inventory?.items ?? [])

const techVisible = ref(false)
const learnTechId = ref('')

const realmVisible = ref(false)
const realmTab = ref<'cultivation' | 'body'>('cultivation')
const realmCult = reactive({ major: '', stage: 1, progress: 0, pool: 0 })
const realmBody = reactive({ major: '', stage: 1, progress: 0, pool: 0 })

const craftVisible = ref(false)
const craftLevelsForm = ref<{ branch: string; label_zh: string; level: number }[]>([])
const learnRecipeId = ref('')

const currencyVisible = ref(false)
const currencyForm = ref<{ key: string; label_zh: string; amount: number }[]>([])

const consVisible = ref(false)

function onSelectionChange(selection: CharacterListRow[]) {
  selectedRows.value = selection
}

async function load() {
  loading.value = true
  try {
    const data = await fetchCharacters({
      q: activeKeyword.value || undefined,
      page: page.value,
      page_size: pageSize.value,
      user_db_id: filterUserDbId.value,
    })
    rows.value = data.items
    total.value = data.total
    page.value = data.page
    pageSize.value = data.page_size
    selectedRows.value = []
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  activeKeyword.value = keyword.value.trim()
  page.value = 1
  void load()
}

function onReset() {
  keyword.value = ''
  activeKeyword.value = ''
  filterUserDbId.value = undefined
  page.value = 1
  void router.replace({ name: 'player-characters', query: {} })
  void load()
}

function onPageSizeChange() {
  page.value = 1
  void load()
}

async function openDetail(row: CharacterListRow | CharacterDetail) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await fetchCharacterDetail(row.id)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加载详情失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function onDetailClosed() {
  detail.value = null
}

function openGrant(row: CharacterListRow | CharacterDetail) {
  grantTargetId.value = row.id
  grantForm.itemId = ''
  grantForm.quantity = 1
  grantForm.note = ''
  grantVisible.value = true
}

async function submitGrant() {
  if (!grantTargetId.value) return
  if (!grantForm.itemId.trim()) {
    ElMessage.warning('请输入物品种类ID')
    return
  }
  acting.value = true
  try {
    const d = await grantCharacterItem(grantTargetId.value, {
      item_id: grantForm.itemId.trim(),
      quantity: grantForm.quantity,
      note: grantForm.note || undefined,
    })
    ElMessage.success('已发送系统邮件')
    grantVisible.value = false
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '给予失败')
  } finally {
    acting.value = false
  }
}

async function doGrantCraftTestCards(row: CharacterListRow | CharacterDetail) {
  acting.value = true
  try {
    const d = await grantTechniqueCraftTestCards(row.id)
    ElMessage.success('已直发【测】属性/效能无限正式卡各一张到背包')
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '发放失败')
  } finally {
    acting.value = false
  }
}

async function runBatch(
  title: string,
  confirmText: string,
  fn: (id: number) => Promise<unknown>,
) {
  const targets = [...selectedRows.value]
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(confirmText, title, { type: 'warning' })
  } catch {
    return
  }
  acting.value = true
  let ok = 0
  try {
    for (const row of targets) {
      await fn(row.id)
      ok += 1
    }
    ElMessage.success(`完成 ${ok} 个`)
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `中断（已成功 ${ok}）`)
    await load()
  } finally {
    acting.value = false
  }
}

function batchSoftDelete() {
  return runBatch('批量删除', `软删选中 ${selectedRows.value.length} 个角色？`, (id) =>
    softDeleteCharacter(id),
  )
}
function batchKill() {
  return runBatch('批量死亡', `令选中角色进入待引渡？`, (id) => killCharacter(id))
}
function batchReincarnate() {
  return runBatch('批量轮回', `强制轮回选中角色？不可轻易撤销。`, (id) => reincarnateCharacter(id))
}
function batchBreakthroughCultivation() {
  return runBatch('修为突破', `无视进度进入下一小境界？`, (id) => breakthroughCultivation(id))
}
function batchBreakthroughBody() {
  return runBatch('炼体突破', `无视进度进入下一炼体小境界？`, (id) => breakthroughBody(id))
}

async function doSoftDelete(row: CharacterListRow | CharacterDetail) {
  try {
    await ElMessageBox.confirm(`软删角色「${row.name}」？`, '删除', { type: 'warning' })
  } catch {
    return
  }
  acting.value = true
  try {
    const d = await softDeleteCharacter(row.id)
    ElMessage.success('已软删')
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function doKill(row: CharacterListRow | CharacterDetail) {
  try {
    await ElMessageBox.confirm(`令「${row.name}」进入待引渡？`, '死亡', { type: 'warning' })
  } catch {
    return
  }
  acting.value = true
  try {
    const d = await killCharacter(row.id)
    ElMessage.success('已进入待引渡')
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function doReincarnate(row: CharacterListRow | CharacterDetail) {
  try {
    await ElMessageBox.confirm(`强制轮回「${row.name}」？`, '轮回', { type: 'warning' })
  } catch {
    return
  }
  acting.value = true
  try {
    const d = await reincarnateCharacter(row.id)
    ElMessage.success('已轮回')
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function doBreakCult(row: CharacterListRow | CharacterDetail) {
  acting.value = true
  try {
    const d = await breakthroughCultivation(row.id)
    ElMessage.success('修为已突破一小境')
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function doBreakBody(row: CharacterListRow | CharacterDetail) {
  acting.value = true
  try {
    const d = await breakthroughBody(row.id)
    ElMessage.success('炼体已突破一小境')
    if (detail.value?.id === d.id) detail.value = d
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

function openAttrs() {
  attrsForm.value = (detail.value?.base_attrs || []).map((a) => ({ ...a }))
  attrsVisible.value = true
}

async function submitAttrs() {
  if (!detail.value) return
  const attrs: Record<string, number> = {}
  for (const row of attrsForm.value) attrs[row.key] = Number(row.value)
  acting.value = true
  try {
    detail.value = await updateCharacterBaseAttrs(detail.value.id, attrs)
    ElMessage.success('已保存属性')
    attrsVisible.value = false
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

function openStatus() {
  const cur = detail.value?.status || 'normal'
  const allowed = statusOptions.value.map((o) => o.value)
  statusForm.value = allowed.includes(cur) ? cur : 'normal'
  statusVisible.value = true
}

async function submitStatus() {
  if (!detail.value) return
  acting.value = true
  try {
    detail.value = await updateCharacterStatus(detail.value.id, statusForm.value)
    ElMessage.success('已保存状态')
    statusVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

function openBag() {
  bagVisible.value = true
}

async function editBagQty(row: InventoryItemRow) {
  if (!detail.value) return
  try {
    const { value } = await ElMessageBox.prompt('新数量（可堆叠）', '修改数量', {
      inputValue: String(row.quantity),
      inputPattern: /^[1-9]\d*$/,
      inputErrorMessage: '请输入正整数',
    })
    detail.value = await updateCharacterInventory(detail.value.id, row.id, {
      quantity: Number(value),
    })
    ElMessage.success('已更新')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : '失败')
  }
}

async function editBagMeta(row: InventoryItemRow) {
  if (!detail.value) return
  try {
    const { value } = await ElMessageBox.prompt('物品 meta JSON', '修改物品属性', {
      inputValue: JSON.stringify(row.meta || {}, null, 0),
      inputType: 'textarea',
    })
    const meta = JSON.parse(value) as Record<string, unknown>
    detail.value = await updateCharacterInventory(detail.value.id, row.id, { meta })
    ElMessage.success('已更新')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : 'JSON 或保存失败')
  }
}

async function deleteBagItem(row: InventoryItemRow) {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(`删除背包物品 ${row.name}？`, '删除', { type: 'warning' })
    detail.value = await updateCharacterInventory(detail.value.id, row.id, { delete: true })
    ElMessage.success('已删除')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : '失败')
  }
}

function openTechs() {
  learnTechId.value = ''
  techVisible.value = true
}

async function submitLearnTech() {
  if (!detail.value || !learnTechId.value.trim()) return
  acting.value = true
  try {
    detail.value = await learnTechnique(detail.value.id, learnTechId.value.trim())
    ElMessage.success('已学会')
    learnTechId.value = ''
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function editTechLevel(row: { technique_id: string; level: number; name: string }) {
  if (!detail.value) return
  try {
    const { value } = await ElMessageBox.prompt(`修改「${row.name}」等级`, '功法等级', {
      inputValue: String(row.level),
      inputPattern: /^\d+$/,
    })
    detail.value = await updateTechniqueLevel(detail.value.id, row.technique_id, Number(value))
    ElMessage.success('已更新')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : '失败')
  }
}

async function doForgetTech(row: { technique_id: string; name: string }) {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(`遗忘「${row.name}」？`, '遗忘功法', { type: 'warning' })
    detail.value = await forgetTechnique(detail.value.id, row.technique_id)
    ElMessage.success('已遗忘')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : '失败')
  }
}

function openRealm() {
  if (!detail.value) return
  realmCult.major = detail.value.major_realm
  realmCult.stage = detail.value.realm_stage
  realmCult.progress = detail.value.realm_progress
  realmCult.pool = detail.value.cultivation_points
  realmBody.major = detail.value.body_temper_stage
  realmBody.stage = detail.value.body_temper_layer
  realmBody.progress = detail.value.body_temper_progress
  realmBody.pool = detail.value.body_tempering_points
  realmTab.value = 'cultivation'
  realmVisible.value = true
}

async function submitRealm() {
  if (!detail.value) return
  acting.value = true
  try {
    if (realmTab.value === 'cultivation') {
      detail.value = await updateCharacterRealm(detail.value.id, {
        track: 'cultivation',
        major: realmCult.major,
        stage: realmCult.stage,
        progress: realmCult.progress,
        pool_points: realmCult.pool,
      })
    } else {
      detail.value = await updateCharacterRealm(detail.value.id, {
        track: 'body',
        major: realmBody.major,
        stage: realmBody.stage,
        progress: realmBody.progress,
        pool_points: realmBody.pool,
      })
    }
    ElMessage.success('已保存境界')
    realmVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

function openCraft() {
  craftLevelsForm.value = (detail.value?.craft_levels || []).map((r) => ({ ...r }))
  learnRecipeId.value = ''
  craftVisible.value = true
}

async function submitCraftLevels() {
  if (!detail.value) return
  const levels: Record<string, number> = {}
  for (const row of craftLevelsForm.value) levels[row.branch] = row.level
  acting.value = true
  try {
    detail.value = await updateCraftLevels(detail.value.id, levels)
    ElMessage.success('已保存制造业等级')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function submitLearnRecipe() {
  if (!detail.value || !learnRecipeId.value.trim()) return
  acting.value = true
  try {
    detail.value = await learnRecipe(detail.value.id, learnRecipeId.value.trim())
    ElMessage.success('已学会配方')
    learnRecipeId.value = ''
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

async function doForgetRecipe(row: { recipe_id: string; name: string }) {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(`遗忘配方「${row.name}」？`, '遗忘', { type: 'warning' })
    detail.value = await forgetRecipe(detail.value.id, row.recipe_id)
    ElMessage.success('已遗忘')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : '失败')
  }
}

function openCurrency() {
  currencyForm.value = (detail.value?.currencies || []).map((c) => ({
    key: c.key,
    label_zh: c.label_zh,
    amount: c.amount,
  }))
  currencyVisible.value = true
}

async function submitCurrency() {
  if (!detail.value) return
  const amounts: Record<string, number> = {}
  for (const row of currencyForm.value) {
    const n = Number(row.amount)
    if (!Number.isInteger(n) || n < 0) {
      ElMessage.warning(`${row.label_zh} 须为非负整数`)
      return
    }
    amounts[row.key] = n
  }
  acting.value = true
  try {
    detail.value = await updateCharacterCurrencies(detail.value.id, amounts)
    ElMessage.success('已保存货币')
    currencyVisible.value = false
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '失败')
  } finally {
    acting.value = false
  }
}

function openConstitution() {
  consVisible.value = true
}

watch(
  () => route.query.user_db_id,
  (v) => {
    if (v) {
      const n = Number(v)
      filterUserDbId.value = Number.isFinite(n) ? n : undefined
    }
  },
  { immediate: true },
)

watch(
  () => route.query.character_id,
  async (v) => {
    if (!v) return
    const id = Number(v)
    if (!Number.isFinite(id)) return
    await openDetail({ id } as CharacterListRow)
  },
)

onMounted(async () => {
  try {
    schema.value = await fetchCharacterOpsSchema()
    pageSize.value = schema.value.default_page_size
  } catch {
    schema.value = null
  }
  const qName = route.query.q
  if (typeof qName === 'string' && qName) {
    keyword.value = qName
    activeKeyword.value = qName
  }
  const ud = route.query.user_db_id
  if (ud) {
    const n = Number(ud)
    if (Number.isFinite(n)) filterUserDbId.value = n
  }
  await load()
  const cid = route.query.character_id
  if (cid) {
    const id = Number(cid)
    if (Number.isFinite(id)) await openDetail({ id } as CharacterListRow)
  }
})
</script>

<style scoped>
.accounts-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  height: 100%;
}
.page-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}
.page-head h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  color: #16352f;
}
.sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: #5b736d;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.batch-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #f3f7f5;
  border: 1px solid #c5d4cf;
  border-radius: 2px;
}
.batch-hint {
  font-size: 13px;
  color: #243f39;
  margin-right: 4px;
  min-width: 72px;
}
.search {
  width: 260px;
}
.page-size-label {
  font-size: 13px;
  color: #5b736d;
  margin-left: 4px;
}
.grid-wrap {
  background: #fff;
  border: 1px solid #c5d4cf;
  border-radius: 2px;
  overflow: hidden;
}
.navicat-grid {
  --el-table-header-bg-color: #e8efec;
  --el-table-header-text-color: #243f39;
  --el-table-row-hover-bg-color: #f3f8f6;
  font-family: Consolas, 'Cascadia Mono', 'Sarasa Mono SC', monospace;
  font-size: 12px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0 8px;
}
.dialog-hint {
  margin: 0 0 10px;
  font-size: 13px;
  color: #6a7f78;
}
.detail-meta {
  margin: 0 0 12px;
  font-size: 13px;
  color: #5b736d;
}
.ml {
  margin-left: 8px;
}
.section-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}
.section-card {
  border: 1px solid #c5d4cf;
  background: #f7fbf9;
  color: #16352f;
  padding: 14px 8px;
  font-size: 14px;
  cursor: pointer;
  border-radius: 2px;
}
.section-card:hover {
  background: #e8efec;
}
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.inline-form {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.mb {
  margin-bottom: 12px;
}
.sub-h {
  margin: 8px 0;
  font-size: 14px;
  color: #16352f;
}
.craft-levels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}
</style>
