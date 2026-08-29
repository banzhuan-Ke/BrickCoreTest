<template>
  <div class="plan-edit-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-button link @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>返回列表
        </el-button>
        <el-divider direction="vertical" />
        <span class="page-title">{{ isNew ? '新建测试计划' : '编辑测试计划' }}</span>
      </div>
      <div class="header-right">
        <el-button @click="handleBack">取消</el-button>
        <el-button
          v-if="!isNew"
          type="success"
          :loading="running"
          @click="handleRun"
        >
          <el-icon><VideoPlay /></el-icon>执行计划
        </el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          <el-icon><Check /></el-icon>保存
        </el-button>
      </div>
    </div>

    <!-- 主体：左右布局 -->
    <div class="edit-body" v-loading="pageLoading">
      <!-- 左侧：选择器面板 -->
      <div class="selector-panel">
        <div class="panel-title">添加内容</div>
        <PlanItemSelector
          :added-items="planItems"
          @add-items="handleAddItems"
        />
      </div>

      <!-- 右侧：表单 + Item 列表 -->
      <div class="main-panel">
        <!-- 基本信息表单 -->
        <el-card class="form-card" shadow="never">
          <template #header>
            <span class="card-title">基本信息</span>
          </template>
          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-width="90px"
          >
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="计划名称" prop="name">
                  <el-input v-model="form.name" placeholder="请输入计划名称" maxlength="100" show-word-limit />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="默认环境">
                  <el-select v-model="form.env_id" placeholder="选择默认执行环境" clearable style="width: 100%">
                    <el-option
                      v-for="env in proStore.envList"
                      :key="env.id"
                      :label="env.name"
                      :value="env.id"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="所属目录">
                  <CatalogTreeSelect
                    v-model="form.catalog_id"
                    :project-id="proStore.projectInfo.id"
                    placeholder="选择所属目录（可选）"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="描述">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="2"
                placeholder="计划描述（可选）"
                maxlength="500"
                show-word-limit
              />
            </el-form-item>
            <el-form-item label="执行模式">
              <el-switch
                v-model="form.parallel"
                active-text="并行执行"
                inactive-text="串行执行"
              />
              <span class="hint-text" style="margin-left:12px">并行模式下各项同时执行，忽略失败停止设置</span>
            </el-form-item>

            <!-- 全局变量 -->
            <el-form-item label="全局变量">
              <div class="vars-editor">
                <div class="var-toolbar-plan">
                  <el-select
                    v-model="planRefEnvId"
                    placeholder="参考环境"
                    clearable
                    size="small"
                    style="width: 160px"
                  >
                    <el-option
                      v-for="env in proStore.envList"
                      :key="env.id"
                      :label="env.name"
                      :value="env.id"
                    />
                  </el-select>
                  <VarInsertButton :env-id="planRefEnvId" :show-env-edit="false" label="插入变量" />
                  <ToolInsertButton
                    :env-id="planRefEnvId || form.env_id"
                    :extra-vars="planVarNames"
                    label="插入工具"
                  />
                </div>
                <div
                  v-for="(v, idx) in varList"
                  :key="idx"
                  class="var-row"
                >
                  <el-input
                    v-model="v.key"
                    placeholder="变量名"
                    style="width: 150px; margin-right: 8px"
                    @change="syncVars"
                  />
                  <el-input
                    v-model="v.value"
                    placeholder="变量值"
                    style="flex: 1; margin-right: 8px"
                    @change="syncVars"
                  />
                  <el-button link type="danger" @click="removeVar(idx)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-button link type="primary" size="small" @click="addVar">
                  <el-icon><Plus /></el-icon>添加变量
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 计划内容列表 -->
        <el-card class="items-card" shadow="never">
          <template #header>
            <div class="items-header">
              <span class="card-title">计划内容</span>
              <el-button
                v-if="planItems.length > 0"
                link
                type="danger"
                size="small"
                @click="clearAllItems"
              >
                清空全部
              </el-button>
            </div>
          </template>
          <el-alert
            type="info"
            closable
            show-icon
            class="plan-items-help"
          >
            <template #title>执行顺序与依赖说明（可关闭）</template>
            <ul class="plan-help-list">
              <li>列表从上到下即为<strong>串行执行顺序</strong>；并行模式下各项同时执行，依赖设置不生效。</li>
              <li>
                <strong>前置依赖</strong>（链接图标）：仅串行模式有效。若所依赖的前序项执行失败，当前项将被<strong>跳过</strong>，不再执行。
                请只选择序号小于当前项的前序项（第 1 项没有可依赖对象）。
              </li>
              <li>
                <strong>条件分支</strong>属于<strong>用例断言</strong>能力（编辑用例 → 断言 → 条件分支），按响应内容选择不同断言组；
                与计划项依赖无关，计划层面暂不支持 If/Else 流程编排。
              </li>
            </ul>
          </el-alert>
          <PlanItemList
            v-model:items="planItems"
          />
        </el-card>
      </div>
    </div>
  </div>

  <!-- 执行配置弹窗 -->
  <el-dialog v-model="runDialogVisible" title="执行测试计划" width="560px" :close-on-click-modal="false" destroy-on-close>
    <el-form label-width="100px">
      <el-form-item label="执行环境">
        <el-select v-model="runForm.env_id" placeholder="使用计划默认环境" clearable style="width: 100%">
          <el-option
            v-for="env in proStore.envList"
            :key="env.id"
            :label="env.name"
            :value="env.id"
          />
        </el-select>
        <div class="hint-text">不选则使用计划配置的默认环境</div>
      </el-form-item>
      <el-form-item label="执行机">
        <ViaWorkerSelect
          v-model="runForm.worker_id"
          :env-id="runForm.env_id || form.env_id"
          force-serial-hint
        />
      </el-form-item>
      <el-form-item label="失败停止">
        <el-switch v-model="runForm.stop_on_failure" />
        <span class="hint-text" style="margin-left:8px">遇到失败用例时立即停止计划</span>
      </el-form-item>
      <el-form-item label="Schema校验">
        <el-switch v-model="runForm.auto_validate_schema" />
        <span class="hint-text" style="margin-left:8px">自动校验响应格式</span>
      </el-form-item>
    </el-form>
    <VariablePreviewPanel
      v-if="runForm.env_id || form.env_id"
      :env-id="runForm.env_id || form.env_id"
      :extra-variables="form.variables"
    />
    <template #footer>
      <el-button @click="runDialogVisible = false">取消</el-button>
      <el-button type="success" :loading="running" @click="doRun">
        <el-icon><VideoPlay /></el-icon>开始执行
      </el-button>
    </template>
  </el-dialog>

  <!-- 执行结果弹窗 -->
  <el-dialog
    v-model="resultDialogVisible"
    title="执行结果"
    width="1180px"
    top="4vh"
    :close-on-click-modal="false"
  >
    <div v-if="runResult" class="run-result">
      <!-- 总体统计 -->
      <el-row :gutter="16" class="result-stats">
        <el-col :span="6">
          <el-statistic title="总用例数" :value="runResult.total" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="成功" :value="runResult.success" value-style="color:#67c23a" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="失败" :value="runResult.failed" value-style="color:#f56c6c" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="耗时(ms)" :value="runResult.duration" />
        </el-col>
      </el-row>
      <el-divider />
      <!-- 总体状态 -->
      <div class="result-status">
        <el-tag :type="runResult.status === 'success' ? 'success' : 'danger'" size="large">
          {{ runResult.status === 'success' ? '全部通过' : '存在失败' }}
        </el-tag>
        <span class="env-info">环境：{{ runResult.env_name }}</span>
      </div>
      <!-- Item 维度结果 -->
      <el-table :data="runResult.item_results" border style="margin-top:16px" size="small">
        <el-table-column label="序号" type="index" width="55" align="center" />
        <el-table-column label="类型" prop="item_type" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.item_type === 'suite' ? 'primary' : 'info'">
              {{ row.item_type === 'suite' ? '套件' : '用例' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" prop="status" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'success' ? 'success' : row.status === 'skipped' ? 'warning' : 'danger'">
              {{ row.status === 'success' ? '通过' : row.status === 'skipped' ? '跳过' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="通过/总计" width="100" align="center">
          <template #default="{ row }">
            <span :style="row.failed > 0 ? 'color:#f56c6c' : 'color:#67c23a'">
              {{ row.success }}/{{ row.total }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="耗时(ms)" prop="duration" width="90" align="center" />
        <el-table-column label="备注" prop="error" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error" style="color:#f56c6c">{{ row.error }}</span>
            <span v-else style="color:#999">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <template #footer>
      <el-button @click="resultDialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, Delete, Plus, VideoPlay } from '@element-plus/icons-vue'
import { httpPlanApi } from '@/api/modules/http'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import PlanItemSelector from './components/PlanItemSelector.vue'
import PlanItemList from './components/PlanItemList.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import VariablePreviewPanel from '@/components/VariablePreviewPanel.vue'
import ViaWorkerSelect from '@/components/ViaWorkerSelect.vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const planId = route.params.planId
const isNew = computed(() => planId === 'new' || !planId)

const pageLoading = ref(false)
const saving = ref(false)

// 表单
const formRef = ref(null)
const form = ref({
  name: '',
  env_id: null,
  catalog_id: null,
  description: '',
  variables: {},
  parallel: false,
})

const rules = {
  name: [{ required: true, message: '请输入计划名称', trigger: 'blur' }],
}

// 全局变量键值对
const varList = ref([])
const planRefEnvId = ref(null)

const planVarNames = computed(() =>
  varList.value.map((v) => (v.key || '').trim()).filter(Boolean)
)

const syncVars = () => {
  const obj = {}
  varList.value.forEach(v => {
    if (v.key) obj[v.key] = v.value
  })
  form.value.variables = obj
}

const addVar = () => {
  varList.value.push({ key: '', value: '' })
}

const removeVar = (idx) => {
  varList.value.splice(idx, 1)
  syncVars()
}

// 加载 variables 到 varList
const loadVars = (vars) => {
  varList.value = Object.entries(vars || {}).map(([key, value]) => ({ key, value: String(value) }))
}

// 计划内容 items
const planItems = ref([])

// 添加 items（来自 PlanItemSelector）
const handleAddItems = (newItems) => {
  // 去重：suite 按 suite_id，case 按 case_id
  for (const item of newItems) {
    const dup = planItems.value.find(existing => {
      if (item.item_type === 'suite') return existing.item_type === 'suite' && existing.suite_id === item.suite_id
      if (item.item_type === 'case') return existing.item_type === 'case' && existing.case_id === item.case_id
      return false
    })
    if (!dup) {
      planItems.value.push({ ...item, sort: planItems.value.length })
    }
  }
}

const clearAllItems = async () => {
  try {
    await ElMessageBox.confirm('确定清空全部计划内容吗？', '提示', { type: 'warning' })
    planItems.value = []
  } catch (e) {
    // cancelled
  }
}

// 加载计划详情（编辑模式）
const loadPlan = async () => {
  if (isNew.value) return
  pageLoading.value = true
  try {
    const res = await httpPlanApi.getDetail(planId)
    if (res.data) {
      const plan = res.data
      form.value.name = plan.name
      form.value.env_id = plan.env_id || null
      form.value.catalog_id = plan.catalog_id || null
      form.value.description = plan.description || ''
      form.value.variables = plan.variables && typeof plan.variables === 'object' ? plan.variables : {}
      form.value.parallel = !!plan.parallel
      loadVars(form.value.variables)
      planItems.value = (plan.items || []).map((item, idx) => ({
        ...item,
        sort: idx,
        depends_on: Array.isArray(item.depends_on) ? [...item.depends_on] : [],
      }))
    }
  } catch (e) {
    ElMessage.error('加载计划失败')
  } finally {
    pageLoading.value = false
  }
}

const resolveDependsOnToSortIndex = (dep, allItems, selfIdx) => {
  if (dep === null || dep === undefined || dep === '') return null
  const byKeyIdx = allItems.findIndex((it) => it._key === dep)
  if (byKeyIdx >= 0) return byKeyIdx
  const byIdIdx = allItems.findIndex((it) => it.id === dep || it.id === Number(dep))
  if (byIdIdx >= 0) return byIdIdx
  const n = Number(dep)
  if (!Number.isNaN(n) && n >= 0 && n < allItems.length) return n
  return null
}

// 保存
const handleSave = async () => {
  // 同步变量
  syncVars()
  // 表单校验
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先选择项目')
    return
  }

  saving.value = true
  try {
    let hadInvalidDeps = false
    // 构造 items 数据
    const itemsData = planItems.value.map((item, idx) => ({
      item_type: item.item_type,
      suite_id: item.suite_id || null,
      case_id: item.case_id || null,
      sort: idx,
      depends_on: (item.depends_on || [])
        .map((dep) => resolveDependsOnToSortIndex(dep, planItems.value, idx))
        .filter((depIdx) => {
          if (depIdx === null || depIdx === idx) return false
          if (depIdx >= idx) {
            hadInvalidDeps = true
            return false
          }
          return true
        }),
    }))
    if (hadInvalidDeps) {
      ElMessage.warning('部分依赖指向了序号不小于当前项的前序项，已自动忽略。依赖只能选择前序项。')
    }

    if (isNew.value) {
      // 创建计划
      const createRes = await httpPlanApi.create({
        name: form.value.name,
        project_id: proStore.projectInfo.id,
        description: form.value.description || null,
        env_id: form.value.env_id || null,
        catalog_id: form.value.catalog_id || null,
        variables: form.value.variables,
        parallel: form.value.parallel,
      })
      const newPlanId = createRes.data?.id
      if (!newPlanId) throw new Error('创建失败')
      // 保存 items
      if (itemsData.length > 0) {
        await httpPlanApi.updateItems(newPlanId, { items: itemsData })
      }
      ElMessage.success('测试计划创建成功')
    } else {
      // 更新计划
      await httpPlanApi.update(planId, {
        name: form.value.name,
        description: form.value.description || null,
        env_id: form.value.env_id || null,
        catalog_id: form.value.catalog_id || null,
        variables: form.value.variables,
        parallel: form.value.parallel,
      })
      // 全量更新 items
      await httpPlanApi.updateItems(planId, { items: itemsData })
      ElMessage.success('测试计划保存成功')
    }

    router.push('/api-plan')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}

const handleBack = () => {
  router.push('/api-plan')
}

// ========== 执行计划 ==========
const running = ref(false)
const runDialogVisible = ref(false)
const resultDialogVisible = ref(false)
const runResult = ref(null)

const runForm = ref({
  env_id: null,
  worker_id: null,
  stop_on_failure: false,
  auto_validate_schema: false,
})

const handleRun = () => {
  // 预填默认环境
  runForm.value.env_id = form.value.env_id || null
  runForm.value.worker_id = null
  runDialogVisible.value = true
}

const doRun = async () => {
  running.value = true
  try {
    const payload = {
      stop_on_failure: runForm.value.stop_on_failure,
      auto_validate_schema: runForm.value.auto_validate_schema,
    }
    if (runForm.value.env_id) payload.env_id = runForm.value.env_id
    if (runForm.value.worker_id) payload.worker_id = runForm.value.worker_id

    const res = await httpPlanApi.runPlan(planId, payload)
    runResult.value = res.data
    runDialogVisible.value = false
    resultDialogVisible.value = true

    if (res.data?.status === 'success') {
      ElMessage.success(`执行完成：${res.data.success}/${res.data.total} 通过`)
    } else {
      ElMessage.warning(`执行完成：${res.data?.failed} 个用例失败`)
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '执行失败，请检查环境配置')
  } finally {
    running.value = false
  }
}

onMounted(() => {
  proStore.getCatalogList()
  if (proStore.envList.length) {
    planRefEnvId.value = proStore.envList[0].id
  }
  loadPlan()
})
</script>

<style scoped>
.vars-editor {
  width: 100%;
}

.var-toolbar-plan {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.plan-edit-page {
  display: flex;
  flex-direction: column;
  /* 顶栏 56 + 页签约 44 + 底栏 40 + main 内边距 ≈ 140，锁定视口高度以便右侧内部滚动 */
  height: calc(100vh - 140px);
  max-height: calc(100vh - 140px);
  min-height: 0;
  overflow: hidden;
  background: var(--el-bg-color-page, #f5f7fa);
}

/* 头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.header-right {
  display: flex;
  gap: 8px;
}

/* 主体布局 */
.edit-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

/* 左侧选择器 */
.selector-panel {
  width: 340px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  height: 100%;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

/* 右侧主区域：内部滚动 */
.main-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-x: hidden;
  overflow-y: auto;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overscroll-behavior: contain;
}

.form-card {
  flex-shrink: 0;
}

.form-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: var(--el-fill-color-lighter);
}
.items-card {
  flex: 0 0 auto;
}
.items-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: var(--el-fill-color-lighter);
}
.items-card :deep(.el-card__body) {
  padding-bottom: 16px;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.items-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.plan-items-help {
  margin-bottom: 12px;
}

.plan-help-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.plan-help-list li + li {
  margin-top: 4px;
}

/* 变量编辑器 */
.vars-editor {
  width: 100%;
}
.var-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

/* 执行结果 */
.run-result {
  padding: 4px 0;
}
.result-stats {
  margin-bottom: 4px;
}
.result-status {
  display: flex;
  align-items: center;
  gap: 12px;
}
.env-info {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.hint-text {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
