<template>
  <el-container class="case-edit-container">
    <!-- 左侧：关键字面板 -->
    <el-aside width="280px" class="keyword-sidebar">
      <div class="sidebar-header">
        <h3>操作选项</h3>
      </div>
      <div class="keyword-list">
        <el-collapse v-model="activeGroups" class="keyword-collapse">
          <el-collapse-item
            v-for="group in keywordGroups"
            :key="group.groupId"
            :name="group.groupId"
            class="keyword-group"
          >
            <template #title>
              <div class="group-title">
                <el-icon><component :is="group.icon" /></el-icon>
                <span>{{ group.name }}</span>
              </div>
            </template>
            
            <VueDraggable
              :modelValue="group.items"
              :group="{ name: 'steps', pull: 'clone', put: false }"
              :sort="false"
              :clone="cloneKeyword"
              :animation="200"
              target=".keyword-items"
              class="draggable-source"
            >
              <div class="keyword-items">
                <div
                  v-for="(item, itemIndex) in group.items"
                  :key="`${group.groupId}_${item.method}_${itemIndex}`"
                  class="keyword-item"
                  :data-step="JSON.stringify(item)"
                >
                  <el-icon><component :is="item.icon" /></el-icon>
                  <span>{{ item.name }}</span>
                  <el-icon class="drag-icon"><Rank /></el-icon>
                </div>
              </div>
            </VueDraggable>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-aside>
    
    <!-- 右侧：用例编辑区 -->
    <el-main class="case-main">
      <el-card class="edit-card">
        <!-- 标题 -->
        <div class="card-header">
          <h2>编辑测试用例</h2>
        </div>
        
        <!-- 基本信息表单 -->
        <el-form 
          :model="caseInfo" 
          :rules="formRules" 
          ref="formRef" 
          label-width="100px"
          class="case-form"
        >
          <el-form-item label="用例名称" prop="name">
            <el-input 
              v-model="caseInfo.name" 
              placeholder="请输入用例名称"
              maxlength="100"
              show-word-limit
            />
          </el-form-item>
          
          <el-form-item label="所属目录">
            <CatalogTreeSelect
              v-model="caseInfo.catalog_id"
              :project-id="proStore.projectInfo.id"
              placeholder="请选择所属目录"
            />
          </el-form-item>
          
          <el-form-item label="用例级别" prop="level">
            <el-select v-model="caseInfo.level" placeholder="请选择用例级别">
              <el-option label="P0 - 核心" value="P0" />
              <el-option label="P1 - 高" value="P1" />
              <el-option label="P2 - 中" value="P2" />
              <el-option label="P3 - 低" value="P3" />
            </el-select>
          </el-form-item>

          <el-form-item label="用例描述">
            <el-input
              v-model="caseInfo.description"
              type="textarea"
              :rows="4"
              maxlength="4000"
              show-word-limit
              placeholder="可选：功能背景、操作路径与预期结果（供 AI 优化步骤使用）"
            />
          </el-form-item>
          
          <el-form-item label="创建人">
            <el-input v-model="caseInfo.username" disabled />
          </el-form-item>
        </el-form>

        <CaseUsedVarsPanel :steps="caseInfo.steps" />

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
                执行时间：{{ dateTools.rTime(executionHints.start_time) }}
                <span v-if="executionHints.execution_id"> · 记录 #{{ executionHints.execution_id }}</span>
              </p>
              <CaseExecutionFailureAi
                :execution-id="executionHints.execution_id"
                target-type="ui"
                :project-id="proStore.projectInfo?.id"
                @loaded="onFailureAnalysisLoaded"
              />
            </div>
          </el-collapse-item>
        </el-collapse>
        
        <!-- AI 生成/录制步骤按钮 -->
        <div class="ai-gen-bar">
          <el-button type="warning" @click="aiDialogVisible = true" icon="MagicStick">🤖 AI 生成步骤</el-button>
          <el-button type="success" @click="openRecordDialog" icon="VideoCamera">🎬 AI 录制步骤</el-button>
          <el-button type="warning" plain @click="openOptimizeDialog" icon="MagicStick">✨ AI 优化步骤</el-button>
          <el-button type="primary" plain @click="fragmentPickerVisible = true" icon="Collection">插入片段</el-button>
          <el-button type="warning" plain @click="insertSmartStep" icon="MagicStick">插入智能步骤</el-button>
          <el-button type="success" plain @click="openInteractiveDebug" icon="Monitor">交互调试</el-button>
        </div>

        <UiInteractiveDebugPanel
          ref="debugPanelRef"
          :case-id="caseId"
          :steps="caseInfo.steps"
          :selected-step-index="selectedStepIndex"
          @session-change="interactiveSession = $event"
          @debug-hints-change="debugExecutionHints = $event"
          @focus-step="onDebugSelectStep"
          @apply-locator="applyDebugLocator"
        />

        <!-- 步骤编辑器 -->
        <div class="steps-section">
          <div class="section-title">
            <span>执行步骤</span>
            <el-text type="info" size="small">编辑步骤时在弹窗内插入变量/工具/标签；参数支持 <code v-pre>${{变量名}}</code>、<code v-pre>${{df:标签名}}</code>、<code v-pre>${{dt:md5|text=@a}}</code></el-text>
          </div>
          <StepEditor
            ref="stepEditorRef"
            v-model:steps="caseInfo.steps"
            :execution-hints="executionHints"
            :debug-execution-hints="debugExecutionHints"
            :debug-selected-index="selectedStepIndex"
            :debug-selected-indices="debugHighlightIndices"
            @debug-step="openDebugDialog"
            @debug-select-step="onDebugSelectStep"
            @debug-selected-steps="onDebugSelectedSteps"
            @record-from-step="openRecordFromStep"
          />
        </div>

        <CaseDebugDialog
          v-model="debugDialogVisible"
          :case-id="caseId"
          :steps="caseInfo.steps"
          :through-index="debugThroughIndex"
        />

        <FragmentPickerDialog v-model="fragmentPickerVisible" @insert="onFragmentInsert" />

        <!-- AI 生成弹窗 -->
        <UiCaseGenerator v-model="aiDialogVisible" @apply="handleAiApply" />
        
        <!-- AI 录制弹窗 -->
        <UiCaseRecorder
          v-model="recordDialogVisible"
          :initial-description="recordingDescription"
          :initial-url="recordingInitialUrl"
          :existing-step-count="caseInfo.steps?.length || 0"
          :default-apply-mode="recordPreset.defaultApplyMode"
          :insert-at-index="recordPreset.insertAtIndex"
          :debug-session-id="recordPreset.debugSessionId"
          :preset-device-id="recordPreset.deviceId"
          :preset-mode="recordPreset.presetMode"
          :skip-config="recordPreset.skipConfig"
          :lock-apply-mode="recordPreset.lockApplyMode"
          @apply="handleRecorderApply"
        />

        <UiCaseStepOptimizeDialog
          v-model="optimizeDialogVisible"
          :steps="caseInfo.steps"
          :initial-description="caseInfo.description || caseInfo.name"
          :project-id="proStore.projectInfo.id"
          @apply="handleOptimizeApply"
        />
        
        <!-- 底部按钮 -->
        <div class="action-bar">
          <el-button type="primary" @click="saveCase" :loading="saving">
            <el-icon><Check /></el-icon>
            保存
          </el-button>
          <el-button @click="goBack">
            <el-icon><Close /></el-icon>
            取消
          </el-button>
        </div>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup>
import { reactive, ref, onMounted, computed, provide, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import { StepEditor } from '@/components/StepEditor'
import UiCaseGenerator from '@/views/AI/components/UiCaseGenerator.vue'
import UiCaseRecorder from '@/views/AI/components/UiCaseRecorder.vue'
import UiCaseStepOptimizeDialog from '@/views/AI/components/UiCaseStepOptimizeDialog.vue'
import CaseDebugDialog from '@/components/CaseDebugDialog.vue'
import UiInteractiveDebugPanel from '@/components/UiInteractiveDebugPanel.vue'
import CaseUsedVarsPanel from '@/components/CaseUsedVarsPanel.vue'
import CaseExecutionFailureAi from '@/components/CaseExecutionFailureAi.vue'
import FragmentPickerDialog from '@/components/StepEditor/FragmentPickerDialog.vue'
import { UserStore } from '@/stores/module/UserStore'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { resolveCaseDescriptionForContext, resolveDefaultStartUrl, extractOpenUrlFromSteps, normalizeRecorderApplyPayload } from '@/utils/caseDescription.js'
import { mergeRecorderSteps, resolveRecorderApplyModeLabel } from '@/utils/recorderStepMerge.js'
import http from '@/api/index'
import { ElNotification, ElMessage, ElMessageBox } from 'element-plus'
import dateTools from '@/tools/dateTools'
import ActionGroup from '@/datas/ActionGroup.js'
import { cloneKeywordForDrag } from '@/utils/stepHelper'
import { applyPickLocatorToSteps } from '@/utils/debugLocator.js'
import { parseExecutionIdQuery } from '@/utils/caseExecutionHints'
import { formatDebugStepRange } from '@/utils/debugSession.js'
import {
  Rank, Check, Close,
  ChromeFilled, Position, Mouse,
  CircleCheck, Refresh, SwitchButton,
  DocumentCopy, Upload, Download, 
  FullScreen, View, Timer,
  ArrowDown, ArrowUp, Delete,
  Document, Edit, Clock, Search,
  MessageBox, MoreFilled, Share, WarningFilled
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = UserStore()
const proStore = ProjectStore()
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
const debugPanelRef = ref(null)
const stepEditorRef = ref(null)
const selectedStepIndex = ref(0)
const debugHighlightIndices = ref([])
const pendingDebugIndices = ref(null)
const pendingDebugFromStep = ref(null)
const pendingDebugQueryStep = ref(null)
const interactiveSession = ref(null)
const recordPreset = reactive({
  defaultApplyMode: 'append',
  insertAtIndex: null,
  debugSessionId: null,
  deviceId: '',
  presetMode: false,
  skipConfig: false,
  lockApplyMode: false,
})
provide('varInsertEnvId', varInsertEnvId)
provide('interactiveDebugSession', interactiveSession)
provide('runInteractiveDebugStep', (index) => {
  selectedStepIndex.value = index
  debugPanelRef.value?.runStepAt(index, false)
})

watch(interactiveSession, async (sess, prev) => {
  const pending = pendingDebugIndices.value
  if (pending?.length) {
    if (sess?.status !== 'ready') return
    if (prev?.status === 'ready' && sess?.id === prev?.id) return
    pendingDebugIndices.value = null
    debugHighlightIndices.value = pending
    selectedStepIndex.value = pending[0]
    await nextTick()
    await debugPanelRef.value?.runSelectedSteps(pending)
    return
  }
  const fromStep = pendingDebugFromStep.value
  if (fromStep != null) {
    if (sess?.status !== 'ready') return
    if (prev?.status === 'ready' && sess?.id === prev?.id) return
    pendingDebugFromStep.value = null
    await nextTick()
    await continueRecordFromStep(fromStep)
    return
  }
  const queryStep = pendingDebugQueryStep.value
  if (queryStep == null) return
  if (sess?.status !== 'ready') return
  if (prev?.status === 'ready' && sess?.id === prev?.id) return
  pendingDebugQueryStep.value = null
  await nextTick()
  await debugPanelRef.value?.runFromStartThrough(queryStep)
})
const fragmentPickerVisible = ref(false)

const caseId = route.params.id
const formRef = ref()
const saving = ref(false)
const aiDialogVisible = ref(false)
const recordDialogVisible = ref(false)
const optimizeDialogVisible = ref(false)
const debugDialogVisible = ref(false)
const debugThroughIndex = ref(0)
const debugExecutionHints = ref(null)
const executionHints = ref(null)
const hintsExpanded = ref([])
const hasFailureAnalysis = ref(false)

// 默认展开所有分组
const activeGroups = ref(['1', '2', '2b', '3', '4', '5', '6', '7', '8'])

// 用例信息
const caseInfo = reactive({
  name: '',
  level: '',
  catalog_id: null,
  username: '',
  description: '',
  steps: []
})

const recordingDescription = computed(() => resolveCaseDescriptionForContext(caseInfo))
const recordingInitialUrl = computed(() => resolveDefaultStartUrl({
  steps: caseInfo.steps,
  envList: proStore.envList,
  projectInfo: proStore.projectInfo,
}))

// 图标映射
const iconMap = {
  'Document': Document,
  'Edit': Edit,
  'Mouse': Mouse,
  'Clock': Clock,
  'Search': Search,
  'MessageBox': MessageBox,
  'MoreFilled': MoreFilled,
  'Share': Share
}

// 从 ActionGroup 生成分组后的关键字列表
const keywordGroups = computed(() => {
  return ActionGroup.map(group => ({
    ...group,
    icon: iconMap[group.groupIcon] || Document,
    items: group.items.map(item => ({
      name: item.keyword,
      keyword: item.keyword,
      method: item.method,
      icon: iconMap[group.groupIcon] || Document,
      params: { ...item.params }
    }))
  }))
})

// 扁平化的关键字列表（用于拖拽）
const keywordList = computed(() => {
  const list = []
  ActionGroup.forEach(group => {
    group.items.forEach(item => {
      list.push({
        name: item.keyword,
        keyword: item.keyword,
        method: item.method,
        icon: iconMap[group.groupIcon] || Document,
        params: { ...item.params }
      })
    })
  })
  return list
})

const cloneKeyword = cloneKeywordForDrag

// 表单校验规则
const formRules = {
  name: [
    { required: true, message: '请输入用例名称', trigger: 'blur' },
    { min: 2, max: 100, message: '长度在 2 到 100 个字符', trigger: 'blur' }
  ],
  level: [
    { required: true, message: '请选择用例级别', trigger: 'change' }
  ]
}

async function loadExecutionHints() {
  try {
    const params = {}
    const executionId = parseExecutionIdQuery(route.query.execution_id)
    if (executionId) {
      params.execution_id = executionId
    }
    const res = await http.caseApi.getExecutionHints(caseId, params)
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

// 获取用例详情
async function getCaseDetail() {
  try {
    const res = await http.caseApi.getDetail(caseId)
    if (res.status === 200) {
      caseInfo.name = res.data.name
      caseInfo.level = res.data.level
      caseInfo.catalog_id = res.data.catalog_id ?? null
      caseInfo.username = res.data.username
      caseInfo.description = res.data.description || ''
      // 确保 steps 是数组
      caseInfo.steps = Array.isArray(res.data.steps) ? res.data.steps : []
    }
  } catch (error) {
    ElNotification.error('获取用例详情失败')
  }
}

// 保存用例
async function saveCase() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  
  saving.value = true
  try {
    const res = await http.caseApi.update(caseId, caseInfo)
    if (res.status === 200 || res.status === 201) {
      ElNotification.success('用例保存成功')
      goBack()
    } else {
      ElNotification.error(res.data?.detail || '保存失败')
    }
  } catch (error) {
    ElNotification.error('保存用例失败')
  } finally {
    saving.value = false
  }
}

// 返回列表
function goBack() {
  router.back()
  userStore.deleteTabs(route.path)
}

// AI 生成/录制步骤应用到用例（编辑页：替换全部步骤）
function onFragmentInsert(refStep) {
  if (!refStep) return
  caseInfo.steps = [...(caseInfo.steps || []), refStep]
  ElMessage.success(`已插入片段「${refStep.params?.fragment_name || refStep.desc}」`)
}

function handleAiApply(payload) {
  handleRecorderApply(payload)
}

function insertSmartStep() {
  if (!stepEditorRef.value?.insertSmartStep) {
    ElMessage.warning('步骤编辑器尚未就绪，请稍后重试')
    return
  }
  const stepsLen = caseInfo.steps?.length || 0
  const sel = selectedStepIndex.value
  const insertAt = stepsLen > 0 && sel >= 0 && sel < stepsLen ? sel + 1 : stepsLen
  stepEditorRef.value.insertSmartStep(insertAt)
}

function openRecordDialog() {
  const stepsLen = caseInfo.steps?.length || 0
  const sel = selectedStepIndex.value
  const canInsertAfter = stepsLen > 0 && sel >= 0 && sel < stepsLen
  Object.assign(recordPreset, {
    defaultApplyMode: stepsLen ? 'append' : 'replace',
    insertAtIndex: canInsertAfter ? sel + 1 : null,
    debugSessionId: null,
    deviceId: '',
    presetMode: false,
    skipConfig: false,
    lockApplyMode: false,
  })
  recordDialogVisible.value = true
}

function handleRecorderApply(payload) {
  const { steps, description: desc, applyMode, insertAtIndex } = normalizeRecorderApplyPayload(payload)
  if (!steps?.length) return
  const mode = applyMode || 'replace'
  caseInfo.steps = mergeRecorderSteps(caseInfo.steps, steps, mode, insertAtIndex)
  const modeLabel = resolveRecorderApplyModeLabel(mode)
  if (desc) {
    caseInfo.description = desc
    ElNotification.success(`已${modeLabel} ${steps.length} 个步骤，并同步测试描述到用例描述`)
  } else {
    ElNotification.success(`已${modeLabel} ${steps.length} 个步骤`)
  }
}

async function continueRecordFromStep(index) {
  const sess = interactiveSession.value
  if (sess?.status !== 'ready') return
  if (index > 0) {
    const ok = await debugPanelRef.value?.runFromStartThrough(index - 1)
    if (ok !== true) {
      ElMessage.warning('前置步骤未全部执行成功，请检查登录段后再接录')
      return
    }
  }
  Object.assign(recordPreset, {
    defaultApplyMode: 'insert',
    insertAtIndex: index,
    debugSessionId: sess.id,
    deviceId: sess.device_id,
    presetMode: true,
    skipConfig: true,
    lockApplyMode: true,
  })
  recordDialogVisible.value = true
}

async function openRecordFromStep(index) {
  if (!caseInfo.steps?.length) {
    ElNotification.warning('请先添加步骤')
    return
  }
  onDebugSelectStep(index)
  const sess = interactiveSession.value
  if (sess?.status === 'ready') {
    await continueRecordFromStep(index)
    return
  }
  if (sess && ['starting', 'running', 'closing'].includes(sess.status)) {
    ElMessage.warning('交互调试会话尚未就绪，请稍候')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将从第 1 步自动执行到第 ${index} 步（含登录），然后在当前页继续录制并插入到第 ${index + 1} 步。`,
      '从这里开始录制',
      {
        confirmButtonText: '打开交互调试',
        cancelButtonText: '取消',
        type: 'info',
      },
    )
    pendingDebugFromStep.value = index
    debugPanelRef.value?.showOpenDialog()
  } catch {
    pendingDebugFromStep.value = null
  }
}

async function handleDebugFromStepQuery() {
  const raw = route.query.debugFromStep
  if (raw == null || raw === '') return
  const stepIndex = Number(raw)
  if (!Number.isFinite(stepIndex) || stepIndex < 0) return
  selectedStepIndex.value = stepIndex
  debugHighlightIndices.value = [stepIndex]
  hintsExpanded.value = ['failure']
  await nextTick()
  const sess = interactiveSession.value
  if (sess?.status === 'ready') {
    await debugPanelRef.value?.runFromStartThrough(stepIndex)
    return
  }
  if (sess && ['starting', 'running'].includes(sess.status)) {
    pendingDebugQueryStep.value = stepIndex
    return
  }
  pendingDebugQueryStep.value = stepIndex
  debugPanelRef.value?.showOpenDialog()
}

function openOptimizeDialog() {
  if (!caseInfo.steps?.length) {
    ElMessage.warning('请先添加或录制步骤后再优化')
    return
  }
  optimizeDialogVisible.value = true
}

function handleOptimizeApply(steps) {
  if (!steps?.length) return
  caseInfo.steps = JSON.parse(JSON.stringify(steps))
  ElNotification.success(`已应用 AI 优化后的 ${steps.length} 个步骤，请核对用例描述与步骤后保存`)
}

async function openDebugDialog(index) {
  if (!caseInfo.steps?.length) {
    ElNotification.warning('请先添加步骤')
    return
  }
  onDebugSelectStep(index)

  const sess = interactiveSession.value
  if (sess?.status === 'ready') {
    await debugPanelRef.value?.runFromStartThrough(index)
    return
  }
  if (sess && ['starting', 'running', 'closing'].includes(sess.status)) {
    ElMessage.warning('交互调试会话尚未就绪，请稍候')
    return
  }

  try {
    await ElMessageBox.confirm(
      '推荐使用「交互调试」：浏览器保持打开，可手动操作页面后从第 1 步试跑到目标步。',
      `调试至第 ${index + 1} 步`,
      {
        confirmButtonText: '打开交互调试',
        cancelButtonText: '旧版一次性调试',
        distinguishCancelAndClose: true,
        type: 'info',
      },
    )
    debugPanelRef.value?.showOpenDialog()
  } catch (action) {
    if (action === 'cancel') {
      debugThroughIndex.value = index
      debugDialogVisible.value = true
    }
  }
}

function onDebugSelectStep(index) {
  const idx = Number(index)
  if (!Number.isFinite(idx) || idx < 0) return
  selectedStepIndex.value = idx
  debugHighlightIndices.value = [idx]
  // 选中态经 selectedStepIndex → DebugPanel watch 同步到 Runner，避免重复 select-step 请求
}

async function onDebugSelectedSteps(indices) {
  if (!caseInfo.steps?.length || !indices?.length) return
  const sorted = [...indices].sort((a, b) => a - b)
  debugHighlightIndices.value = sorted
  selectedStepIndex.value = sorted[0]

  const sess = interactiveSession.value
  if (sess?.status === 'ready') {
    await debugPanelRef.value?.runSelectedSteps(sorted)
    return
  }
  if (sess?.status === 'starting') {
    pendingDebugIndices.value = sorted
    ElMessage.info('调试会话启动中，就绪后将自动执行所选步骤')
    return
  }
  if (sess && ['running', 'closing'].includes(sess.status)) {
    ElMessage.warning('交互调试会话尚未就绪，请稍候')
    return
  }

  const rangeText = formatDebugStepRange(sorted)
  try {
    await ElMessageBox.confirm(
      `将执行 ${rangeText}（共 ${sorted.length} 步）。请先打开「交互调试」，浏览器保持打开后可反复试跑。`,
      '多步调试',
      {
        confirmButtonText: '打开交互调试',
        cancelButtonText: '取消',
        type: 'info',
      },
    )
    pendingDebugIndices.value = sorted
    debugPanelRef.value?.showOpenDialog()
  } catch {
    pendingDebugIndices.value = null
  }
}

function applyDebugLocator(payload) {
  const { steps, updated, stepIndex } = applyPickLocatorToSteps(caseInfo.steps, payload, {
    mode: payload.mode || 'replace',
    stepIndex: payload.stepIndex,
    insertAt: payload.insertAt,
    template: payload.template,
  })
  if (!updated) {
    ElMessage.warning('未能回填定位器')
    return
  }
  caseInfo.steps = steps
  selectedStepIndex.value = stepIndex
  debugHighlightIndices.value = [stepIndex]
  const msg = payload.mode === 'insert'
    ? `已新增步骤 ${stepIndex + 1} 并写入定位器（请保存用例）`
    : `步骤 ${stepIndex + 1} 定位器已更新（请保存用例）`
  ElNotification.success(msg)
}

function openInteractiveDebug() {
  if (!caseInfo.steps?.length) {
    ElNotification.warning('请先添加步骤')
    return
  }
  debugPanelRef.value?.showOpenDialog()
}

onMounted(async () => {
  await getCaseDetail()
  await loadExecutionHints()
  await handleDebugFromStepQuery()
})

watch(
  () => route.query.execution_id,
  () => {
    loadExecutionHints()
  }
)

watch(
  () => route.query.debugFromStep,
  () => {
    handleDebugFromStepQuery()
  }
)
</script>

<style scoped lang="scss">
@use '@/styles/case-step-editor-layout.scss';

.execution-hints-collapse {
  margin-bottom: 16px;
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
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: pre-wrap;
}

.execution-hints-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
