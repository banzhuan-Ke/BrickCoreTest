<template>
  <el-container class="case-edit-container">
    <KeywordSidebar
      v-model="activeGroups"
      title="App 操作"
      hint="拖到右侧步骤区，或双击快速添加"
      :groups="keywordGroups"
      enable-dblclick
      @add="addKeywordToSteps"
    />
    <el-main class="case-main">
      <el-card class="edit-card">
        <div class="card-header"><h2>{{ isEdit ? '编辑 App 用例' : '新建 App 用例' }}</h2></div>
        <el-form :model="caseInfo" :rules="rules" ref="formRef" label-width="100px">
          <el-form-item label="用例名称" prop="name">
            <el-input v-model="caseInfo.name" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="所属目录">
            <CatalogTreeSelect v-model="caseInfo.catalog_id" :project-id="proStore.projectInfo.id" />
          </el-form-item>
          <el-form-item label="优先级" prop="level">
            <el-select v-model="caseInfo.level">
              <el-option v-for="lv in ['P0','P1','P2','P3']" :key="lv" :label="lv" :value="lv" />
            </el-select>
          </el-form-item>
          <el-form-item label="平台">
            <el-select v-model="caseInfo.platform_scope">
              <el-option label="Android" value="android" />
            </el-select>
          </el-form-item>
          <el-form-item label="驱动模式">
            <el-select v-model="caseInfo.driver_mode" style="width: 220px">
              <el-option
                v-for="opt in APP_DRIVER_MODE_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
          <AppH5UsageGuide scope="case" />
          <el-form-item label="描述">
            <el-input
              v-model="caseInfo.description"
              type="textarea"
              :rows="3"
              placeholder="可选：操作路径与预期结果（供 AI 优化步骤使用）"
            />
          </el-form-item>
        </el-form>
        <div class="ai-gen-bar">
          <el-button type="primary" plain @click="generatorDialogVisible = true" icon="Cpu">🤖 AI 生成步骤</el-button>
          <el-button type="warning" plain @click="optimizeDialogVisible = true" icon="MagicStick">✨ AI 优化步骤</el-button>
          <el-button size="small" plain type="primary" @click="fragmentPickerVisible = true">插入片段</el-button>
        </div>
        <div class="steps-section">
          <div class="section-title">
            <span>执行步骤</span>
          </div>
          <el-collapse
            v-if="executionHints?.has_failure"
            v-model="hintsExpanded"
            class="execution-hints-collapse"
          >
            <el-collapse-item name="failure">
              <template #title>
                <span class="execution-hints-collapse-title">
                  <el-icon color="#f56c6c"><WarningFilled /></el-icon>
                  最近一次执行未通过（点击展开详情）
                  <el-tag v-if="hasFailureAnalysis" size="small" type="warning" class="ai-analyzed-tag">已 AI 分析</el-tag>
                </span>
              </template>
              <div class="execution-hints-body">
                <p v-if="executionHints.error_msg" class="execution-hints-error">{{ executionHints.error_msg }}</p>
                <pre v-if="executionHints.log_excerpt" class="execution-hints-log">{{ executionHints.log_excerpt }}</pre>
                <p v-else-if="executionHints.log_tail" class="execution-hints-log-muted">{{ executionHints.log_tail }}</p>
                <p v-if="executionHints.start_time" class="execution-hints-meta">
                  执行时间：{{ formatTime(executionHints.start_time) }}
                  <span v-if="executionHints.execution_id"> · 记录 #{{ executionHints.execution_id }}</span>
                </p>
                <CaseExecutionFailureAi
                  :execution-id="executionHints.execution_id"
                  target-type="app"
                  :project-id="proStore.projectInfo?.id"
                  @loaded="onFailureAnalysisLoaded"
                />
              </div>
            </el-collapse-item>
          </el-collapse>
          <StepEditor
            v-model:steps="caseInfo.steps"
            module="app"
            :driver-mode="caseInfo.driver_mode"
            :debug-enabled="isEdit"
            :execution-hints="executionHints"
            :debug-selected-index="selectedStepIndex"
            @debug-step="openDebugDialog"
            @debug-select-step="selectedStepIndex = $event"
          />
        </div>
        <FragmentPickerDialog
          v-model="fragmentPickerVisible"
          domain="app"
          :selected-step-index="selectedStepIndex"
          :steps-count="caseInfo.steps?.length || 0"
          @insert="onFragmentInsert"
        />
        <AppCaseGenerator
          v-model="generatorDialogVisible"
          :initial-description="caseInfo.description || caseInfo.name"
          :driver-mode="caseInfo.driver_mode"
          :app-id="defaultAppId"
          @apply="handleGeneratorApply"
        />
        <AppCaseDebugDialog
          v-if="isEdit"
          v-model="debugDialogVisible"
          :case-id="caseId"
          :steps="caseInfo.steps"
          :through-index="debugThroughIndex"
          :driver-mode="caseInfo.driver_mode"
        />
        <UiCaseStepOptimizeDialog
          v-model="optimizeDialogVisible"
          step-module="app"
          :steps="caseInfo.steps"
          :initial-description="caseInfo.description || caseInfo.name"
          :project-id="proStore.projectInfo.id"
          @apply="handleOptimizeApply"
        />
        <div class="action-bar">
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          <el-button @click="goBack">取消</el-button>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onActivated, onMounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { StepEditor, KeywordSidebar } from '@/components/StepEditor'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import appActionGroup, { APP_DRIVER_MODE_OPTIONS } from '@/datas/AppActionGroup.js'
import { appCaseApi, appElementApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { serializeKeywordForDrag, buildStepFromKeyword, ensureStepsHaveIds, updateStepLocatorAtPath } from '@/utils/stepHelper'
import { parseExecutionIdQuery } from '@/utils/caseExecutionHints'
import dateTools from '@/tools/dateTools'
import { validateCaseDriverMode, rememberProjectDefaultAppId, getProjectDefaultAppId } from '@/utils/appStepMeta.js'
import {
  consumeAppInspectorResult,
  peekInspectorResultParsed,
  inspectorResultMatchesCase,
  consumeAppInspectorCaseDraft,
  setAppInspectorCaseDraft,
  clearAppInspectorCaseDraft,
  formatInspectorStepPathLabel,
} from '@/utils/appInspectorContext.js'
import AppCaseDebugDialog from '@/components/AppCaseDebugDialog.vue'
import AppH5UsageGuide from '@/components/App/AppH5UsageGuide.vue'
import FragmentPickerDialog from '@/components/StepEditor/FragmentPickerDialog.vue'
import UiCaseStepOptimizeDialog from '@/views/AI/components/UiCaseStepOptimizeDialog.vue'
import AppCaseGenerator from '@/views/AI/components/AppCaseGenerator.vue'
import CaseExecutionFailureAi from '@/components/CaseExecutionFailureAi.vue'
import { insertStepIntoList, resolveInsertAfterIndex } from '@/utils/stepHelper'
import { Document, Edit, Mouse, Clock, Search, MessageBox, MoreFilled, Share, Setting, WarningFilled, Cpu } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const caseId = route.params.id
const isEdit = computed(() => !!caseId)
const formRef = ref()
const saving = ref(false)
const executionHints = ref(null)
const hintsExpanded = ref([])
const hasFailureAnalysis = ref(false)
const fragmentPickerVisible = ref(false)
const selectedStepIndex = ref(-1)
const optimizeDialogVisible = ref(false)
const generatorDialogVisible = ref(false)
const debugDialogVisible = ref(false)
const debugThroughIndex = ref(0)
const appElementOptions = ref([])
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
provide('varInsertEnvId', varInsertEnvId)
provide('saveAppInspectorDraft', () => {
  setAppInspectorCaseDraft(JSON.parse(JSON.stringify(caseInfo)), {
    caseId: caseId || null,
    projectId: proStore.projectInfo?.id || null,
  })
})
const activeGroups = ref(['1', '2', '3', '4', '5', '6', '6b', '7', '8'])

const iconMap = { Document, Edit, Mouse, Clock, Search, MessageBox, MoreFilled, Share, Setting }

const caseInfo = reactive({
  name: '',
  level: 'P2',
  catalog_id: null,
  platform_scope: 'android',
  driver_mode: 'hybrid',
  description: '',
  username: uStore.userInfo?.username || '',
  steps: [],
})

const rules = {
  name: [{ required: true, message: '请输入用例名称', trigger: 'blur' }],
  level: [{ required: true, message: '请选择优先级', trigger: 'change' }],
}

function onFragmentInsert(payload) {
  const refStep = payload?.step || payload
  if (!refStep) return
  const insertAt = payload?.insertAt ?? resolveInsertAfterIndex(caseInfo.steps?.length || 0, selectedStepIndex.value)
  const { steps, insertAt: at } = insertStepIntoList(caseInfo.steps, refStep, insertAt)
  caseInfo.steps = steps
  selectedStepIndex.value = at
  ElMessage.success(`已在第 ${at + 1} 步插入片段「${refStep.params?.fragment_name || refStep.desc}」`)
}

function handleOptimizeApply(steps) {
  caseInfo.steps = steps
  ElMessage.success('已应用 AI 优化步骤，请核对定位与断言后保存')
}

const defaultAppId = computed(() =>
  getProjectDefaultAppId(proStore.projectInfo, caseInfo.steps)
)

function handleGeneratorApply({ steps, mode }) {
  const normalizedSteps = ensureStepsHaveIds(steps)
  if (mode === 'replace') {
    caseInfo.steps = [...normalizedSteps]
    ElMessage.success(`已替换为 ${normalizedSteps.length} 个 AI 生成步骤，请核对定位后保存`)
  } else {
    caseInfo.steps = [...(caseInfo.steps || []), ...normalizedSteps]
    ElMessage.success(`已追加 ${normalizedSteps.length} 个 AI 生成步骤，请核对定位后保存`)
  }
}

function openDebugDialog(index) {
  if (!isEdit.value) {
    ElMessage.warning('请先保存用例后再使用调试')
    return
  }
  if (!caseInfo.steps?.length) {
    ElMessage.warning('请先添加步骤')
    return
  }
  debugThroughIndex.value = index
  debugDialogVisible.value = true
}

function applyInspectorResult() {
  const result = consumeAppInspectorResult()
  if (!result) return
  if (result.caseId && caseId && String(result.caseId) !== String(caseId)) {
    ElMessage.warning('探查结果与当前用例不匹配，已忽略')
    clearAppInspectorCaseDraft()
    return
  }
  const stepPath = Array.isArray(result.stepPath)
    ? result.stepPath
    : (typeof result.stepIndex === 'number' ? [result.stepIndex] : null)

  if (result.type === 'locator' && stepPath?.length) {
    if (result.locator) {
      const { steps: nextSteps, updated } = updateStepLocatorAtPath(caseInfo.steps || [], stepPath, result.locator)
      if (!updated) {
        ElMessage.warning('探查回填失败：步骤路径已失效，请重新选择')
        return
      }
      caseInfo.steps = nextSteps
      ElMessage.success(`已回填定位器到${formatInspectorStepPathLabel(stepPath)}`)
    }
  } else if (result.type === 'steps' && Array.isArray(result.steps)) {
    const normalizedSteps = ensureStepsHaveIds(result.steps)
    if (result.mode === 'replace') {
      caseInfo.steps = [...normalizedSteps]
      ElMessage.success(`已替换为探查 AI 生成的 ${normalizedSteps.length} 个步骤`)
    } else {
      caseInfo.steps = [...(caseInfo.steps || []), ...normalizedSteps]
      ElMessage.success(`已追加探查 AI 生成的 ${normalizedSteps.length} 个步骤`)
    }
  }
  clearAppInspectorCaseDraft()
}

const keywordGroups = computed(() =>
  appActionGroup.map((group) => ({
    ...group,
    icon: iconMap[group.groupIcon] || Document,
    items: group.items.map((item) => ({
      name: item.keyword,
      keyword: item.keyword,
      method: item.method,
      icon: iconMap[group.groupIcon] || Document,
      params: { ...item.params },
      is_container: item.is_container,
      branches: item.branches,
    })),
  }))
)

function addKeywordToSteps(item) {
  const raw = JSON.parse(serializeKeywordForDrag(item))
  caseInfo.steps = [...(caseInfo.steps || []), buildStepFromKeyword(raw)]
}

async function loadExecutionHints() {
  if (!caseId) return
  try {
    const params = {}
    const executionId = parseExecutionIdQuery(route.query.execution_id)
    if (executionId) {
      params.execution_id = executionId
    }
    const res = await appCaseApi.getExecutionHints(caseId, params)
    const payload = res.data?.data ?? res.data
    executionHints.value = payload?.has_failure ? payload : null
    hasFailureAnalysis.value = false
    if (executionHints.value) {
      hintsExpanded.value = ['failure']
    }
  } catch {
    executionHints.value = null
    hasFailureAnalysis.value = false
  }
}

function onFailureAnalysisLoaded(data) {
  hasFailureAnalysis.value = !!data?.root_cause
  if (data?.root_cause) {
    hintsExpanded.value = ['failure']
  }
}

async function loadDetail() {
  if (!caseId) return
  const res = await appCaseApi.detail(caseId)
  Object.assign(caseInfo, {
    name: res.data.name,
    level: res.data.level,
    catalog_id: res.data.catalog_id,
    platform_scope: res.data.platform_scope,
    driver_mode: res.data.driver_mode,
    description: res.data.description || '',
    steps: Array.isArray(res.data.steps) ? res.data.steps : [],
  })
}

const formatTime = (value) => dateTools.rTime(value)

function goBack() {
  router.back()
  uStore.deleteTabs(route.path)
}

async function save() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  const driverErr = validateCaseDriverMode(
    caseInfo.driver_mode,
    caseInfo.steps,
    appElementOptions.value
  )
  if (driverErr) {
    ElMessage.error(driverErr)
    return
  }

  saving.value = true
  try {
    const payload = {
      ...caseInfo,
      project_id: proStore.projectInfo.id,
      username: uStore.userInfo?.username,
    }
    if (isEdit.value) {
      await appCaseApi.update(caseId, payload)
      ElMessage.success('已保存')
      goBack()
    } else {
      await appCaseApi.create(payload)
      ElMessage.success('已创建')
      goBack()
    }
    for (const step of caseInfo.steps || []) {
      if (step?.method === 'launch_app' && step.params?.app_id) {
        rememberProjectDefaultAppId(proStore.projectInfo.id, step.params.app_id)
        break
      }
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadElementOptions() {
  try {
    const res = await appElementApi.options({ project_id: proStore.projectInfo.id })
    appElementOptions.value = res.data?.data || res.data || []
  } catch {
    appElementOptions.value = []
  }
}

async function initCaseEditPage() {
  if (!varInsertEnvId.value && proStore.envList.length) {
    varInsertEnvId.value = proStore.envList[0].id
  }
  const pendingResult = peekInspectorResultParsed()
  const hasMatchingResult = inspectorResultMatchesCase(pendingResult, caseId)

  if (hasMatchingResult) {
    const draft = consumeAppInspectorCaseDraft(caseId, proStore.projectInfo?.id)
    if (draft && typeof draft === 'object') {
      Object.assign(caseInfo, draft)
    } else if (caseId) {
      await loadDetail()
    }
  } else if (caseId) {
    await loadDetail()
  }
  await loadExecutionHints()
  await loadElementOptions()
  if (hasMatchingResult) {
    applyInspectorResult()
  }
}

onMounted(() => {
  initCaseEditPage()
})

onActivated(() => {
  const pendingResult = peekInspectorResultParsed()
  if (!inspectorResultMatchesCase(pendingResult, caseId)) return
  const draft = consumeAppInspectorCaseDraft(caseId, proStore.projectInfo?.id)
  if (draft && typeof draft === 'object') {
    Object.assign(caseInfo, draft)
  }
  applyInspectorResult()
})

watch(
  () => route.query.execution_id,
  () => {
    loadExecutionHints()
  }
)
</script>

<style scoped lang="scss">
@use '@/styles/case-step-editor-layout.scss';

.execution-hints-collapse {
  margin-bottom: 12px;
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 8px;
  overflow: hidden;
}

.execution-hints-collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--el-color-danger);
  font-weight: 500;
}

.ai-analyzed-tag {
  margin-left: 2px;
}

.execution-hints-body {
  p, pre {
    margin: 6px 0 0;
  }
}

.execution-hints-error {
  font-size: 13px;
  line-height: 1.5;
}

.execution-hints-log {
  margin-top: 8px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow: auto;
}

.execution-hints-log-muted {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.execution-hints-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.sidebar-hint {
  margin: 6px 0 0;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.ai-gen-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}
</style>
