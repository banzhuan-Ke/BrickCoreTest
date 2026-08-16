<template>
  <el-container class="case-edit-container">
    <KeywordSidebar v-model="activeGroups" :groups="keywordGroups" />
    
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
              maxlength="50"
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
          v-if="executionHints?.has_failure || recoveryCount > 0"
          v-model="hintsExpanded"
          class="execution-hints-collapse"
        >
          <el-collapse-item v-if="executionHints?.has_failure" name="failure">
            <template #title>
              <span class="execution-hints-collapse-title">
                <el-icon color="#f56c6c"><WarningFilled /></el-icon>
                最近一次执行未通过（点击展开详情）
                <el-tag v-if="hasFailureAnalysis" size="small" type="warning" class="ai-analyzed-tag">已 AI 分析</el-tag>
              </span>
            </template>
            <div class="execution-hints-body">
              <p v-if="executionHints.error_msg" class="execution-hints-error">{{ executionHints.error_msg }}</p>
              <ul
                v-if="executionHints.step_failures?.length"
                class="execution-hints-failures"
              >
                <li
                  v-for="(fail, idx) in executionHints.step_failures.filter((f) => f && !f.unresolved)"
                  :key="`${fail.step_id || fail.step_index}-${idx}`"
                >
                  <span>步骤 {{ (fail.step_index ?? idx) + 1 }}</span>
                  <el-tag
                    v-if="fail.failure_code"
                    size="small"
                    :type="failureCodeTagType(fail.failure_code)"
                    effect="plain"
                    class="execution-hints-code"
                  >{{ formatFailureCode(fail.failure_code) }}</el-tag>
                  <span v-if="fail.keyword || fail.desc"> · {{ fail.keyword || fail.desc }}</span>
                  <span v-if="fail.message" class="execution-hints-fail-msg"> — {{ fail.message }}</span>
                </li>
              </ul>
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
          <el-collapse-item v-if="recoveryCount > 0" name="recovery">
            <template #title>
              <span class="execution-hints-collapse-title execution-hints-recovery-title">
                <el-icon color="#e6a23c"><WarningFilled /></el-icon>
                最近一次执行有 {{ recoveryCount }} 步被自愈 / AI Act 救过
              </span>
            </template>
            <div class="execution-hints-body">
              <ul class="execution-hints-failures">
                <li
                  v-for="(item, idx) in visibleRecoveries"
                  :key="`rec-${item.step_id || item.step_index}-${idx}`"
                >
                  <span>步骤 {{ (item.step_index ?? idx) + 1 }}</span>
                  <el-tag
                    v-if="item.kinds?.includes('heal')"
                    size="small"
                    type="warning"
                    effect="plain"
                    class="execution-hints-code"
                  >自愈</el-tag>
                  <el-tag
                    v-if="item.kinds?.includes('act')"
                    size="small"
                    type="success"
                    effect="plain"
                    class="execution-hints-code"
                  >AI Act</el-tag>
                  <span v-if="item.keyword || item.desc"> · {{ item.keyword || item.desc }}</span>
                  <span v-if="item.message" class="execution-hints-fail-msg"> — {{ item.message }}</span>
                </li>
              </ul>
              <p v-if="executionHints.start_time" class="execution-hints-meta">
                执行时间：{{ dateTools.rTime(executionHints.start_time) }}
                <span v-if="executionHints.execution_id"> · 记录 #{{ executionHints.execution_id }}</span>
                · 详情也可在步骤卡片上查看
              </p>
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
          @run-selected-request="onToolbarRunSelected"
        />

        <UiCaseAuthoringTips />

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
            :enable-run-selected="true"
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

        <FragmentPickerDialog
          v-model="fragmentPickerVisible"
          :selected-step-index="selectedStepIndex"
          :steps-count="caseInfo.steps?.length || 0"
          @insert="onFragmentInsert"
        />

        <!-- AI 生成弹窗 -->
        <UiCaseGenerator v-model="aiDialogVisible" @apply="handleAiApply" />
        
        <!-- AI 录制弹窗 -->
        <UiCaseRecorder
          ref="recorderRef"
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
          :replay-through-index="recordPreset.replayThroughIndex"
          @prepare-replay="onPrepareReplayForRecord"
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
            保存用例
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
import { reactive, ref, onMounted, computed, provide, watch, nextTick, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { StepEditor, KeywordSidebar } from '@/components/StepEditor'
import UiCaseGenerator from '@/views/AI/components/UiCaseGenerator.vue'
import UiCaseRecorder from '@/views/AI/components/UiCaseRecorder.vue'
import UiCaseStepOptimizeDialog from '@/views/AI/components/UiCaseStepOptimizeDialog.vue'
import CaseDebugDialog from '@/components/CaseDebugDialog.vue'
import UiInteractiveDebugPanel from '@/components/UiInteractiveDebugPanel.vue'
import CaseUsedVarsPanel from '@/components/CaseUsedVarsPanel.vue'
import CaseExecutionFailureAi from '@/components/CaseExecutionFailureAi.vue'
import UiCaseAuthoringTips from '@/components/UiCaseAuthoringTips.vue'
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
import { applyPickLocatorToSteps } from '@/utils/debugLocator.js'
import { parseExecutionIdQuery, hasExecutionHintsPayload } from '@/utils/caseExecutionHints'
import { formatFailureCode, failureCodeTagType } from '@/utils/uiFailureCode'
import { formatDebugStepRange } from '@/utils/debugSession.js'
import { insertStepIntoList, resolveInsertAfterIndex } from '@/utils/stepHelper'
import {
  Check, Close,
  Document, Edit, Clock, Search,
  MessageBox, MoreFilled, Share, WarningFilled, Mouse
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = UserStore()
const proStore = ProjectStore()
const varInsertEnvId = ref(proStore.envList[0]?.id || null)
const debugPanelRef = ref(null)
const recorderRef = ref(null)
const stepEditorRef = ref(null)
const selectedStepIndex = ref(-1)
const debugHighlightIndices = ref([])
const pendingDebugIndices = ref(null)
const pendingDebugFromStep = ref(null)
const pendingDebugQueryStep = ref(null)
const interactiveSession = ref(null)
/** 取消「从这里开始录制」回放时递增，避免回放结束后仍启动接录 */
let recordPrepareEpoch = 0
const recordPreset = reactive({
  defaultApplyMode: 'append',
  insertAtIndex: null,
  debugSessionId: null,
  deviceId: '',
  presetMode: false,
  skipConfig: false,
  lockApplyMode: false,
  replayThroughIndex: null,
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
    // 刚打开调试时页面多在起点，需回放前置步再接录
    await continueRecordFromStep(fromStep, { forceReplay: true })
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

watch(recordDialogVisible, (open) => {
  if (!open) recordPrepareEpoch += 1
})
const debugThroughIndex = ref(0)
const debugExecutionHints = ref(null)
const executionHints = ref(null)
const hintsExpanded = ref([])
const hasFailureAnalysis = ref(false)

const visibleRecoveries = computed(() =>
  (executionHints.value?.step_recoveries || []).filter((item) => item && !item.unresolved),
)
const recoveryCount = computed(() => visibleRecoveries.value.length)

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

// 表单校验规则
const formRules = {
  name: [
    { required: true, message: '请输入用例名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  level: [
    { required: true, message: '请选择用例级别', trigger: 'change' }
  ]
}

/** 用于判断是否有未落库的编辑（含步骤弹窗「确定」后的内存变更） */
const savedSnapshot = ref('')
let bypassLeaveGuard = false

function captureSavedSnapshot() {
  savedSnapshot.value = JSON.stringify({
    name: caseInfo.name,
    level: caseInfo.level,
    catalog_id: caseInfo.catalog_id,
    description: caseInfo.description || '',
    steps: caseInfo.steps || [],
  })
}

function isCaseDirty() {
  if (!savedSnapshot.value) return false
  const now = JSON.stringify({
    name: caseInfo.name,
    level: caseInfo.level,
    catalog_id: caseInfo.catalog_id,
    description: caseInfo.description || '',
    steps: caseInfo.steps || [],
  })
  return now !== savedSnapshot.value
}

function onBeforeUnload(e) {
  if (!isCaseDirty()) return
  e.preventDefault()
  e.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (bypassLeaveGuard || !isCaseDirty()) return true
  try {
    await ElMessageBox.confirm(
      '用例有未保存的修改（步骤弹窗里点「确定」只改当前页，还需点底部「保存用例」才会写入服务器）。确定离开吗？',
      '未保存提示',
      { type: 'warning', confirmButtonText: '离开', cancelButtonText: '留下' }
    )
    return true
  } catch {
    return false
  }
})

async function loadExecutionHints() {
  try {
    const params = {}
    const executionId = parseExecutionIdQuery(route.query.execution_id)
    if (executionId) {
      params.execution_id = executionId
    }
    const res = await http.caseApi.getExecutionHints(caseId, params)
    const payload = res.data?.data ?? res.data
    executionHints.value = hasExecutionHintsPayload(payload) ? payload : null
    hasFailureAnalysis.value = false
    if (executionHints.value) {
      const expand = []
      if (executionHints.value.has_failure) expand.push('failure')
      if (recoveryCount.value > 0) expand.push('recovery')
      hintsExpanded.value = expand
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
      await nextTick()
      captureSavedSnapshot()
    }
  } catch (error) {
    ElNotification.error('获取用例详情失败')
  }
}

// 保存用例
async function saveCase() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请先完善用例名称、级别等必填项后再保存')
    return
  }
  
  saving.value = true
  try {
    const payload = {
      name: caseInfo.name,
      level: caseInfo.level,
      catalog_id: caseInfo.catalog_id,
      description: caseInfo.description || '',
      steps: JSON.parse(JSON.stringify(caseInfo.steps || [])),
    }
    const res = await http.caseApi.update(caseId, payload)
    if (res.status === 200 || res.status === 201) {
      captureSavedSnapshot()
      bypassLeaveGuard = true
      ElNotification.success('用例保存成功')
      goBack()
    } else {
      const detail = res.data?.detail
      ElNotification.error(
        typeof detail === 'string' ? detail : (detail?.message || '保存失败')
      )
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
function onFragmentInsert(payload) {
  const refStep = payload?.step || payload
  if (!refStep) return
  const insertAt = payload?.insertAt ?? resolveInsertAfterIndex(caseInfo.steps?.length || 0, selectedStepIndex.value)
  const { steps, insertAt: at } = insertStepIntoList(caseInfo.steps, refStep, insertAt)
  caseInfo.steps = steps
  selectedStepIndex.value = at
  debugHighlightIndices.value = [at]
  ElMessage.success(`已在第 ${at + 1} 步插入片段「${refStep.params?.fragment_name || refStep.desc}」`)
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
  recordPrepareEpoch += 1
  Object.assign(recordPreset, {
    defaultApplyMode: stepsLen ? 'append' : 'replace',
    insertAtIndex: canInsertAfter ? sel + 1 : null,
    debugSessionId: null,
    deviceId: '',
    presetMode: false,
    skipConfig: false,
    lockApplyMode: false,
    replayThroughIndex: null,
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

async function onPrepareReplayForRecord(throughIndex) {
  const epoch = recordPrepareEpoch
  const through = Number(throughIndex)
  if (!Number.isFinite(through) || through < 0) {
    await recorderRef.value?.startAfterPrepare?.()
    return
  }
  const ok = await debugPanelRef.value?.runFromStartThrough(through)
  if (epoch !== recordPrepareEpoch || !recordDialogVisible.value) return
  if (ok !== true) {
    recorderRef.value?.markPrepareFailed?.('前置步骤未全部执行成功，请检查登录段后再接录')
    return
  }
  await recorderRef.value?.startAfterPrepare?.()
}

/**
 * 调试已就绪时接录。
 * @param {number} index 插入位置（0-based）
 * @param {{ forceReplay?: boolean }} [opts]
 *   forceReplay：刚打开调试、页面尚在起点时，必须先回放前置步（不弹二选一）
 */
async function continueRecordFromStep(index, opts = {}) {
  const sess = interactiveSession.value
  if (sess?.status !== 'ready') return

  let replayThroughIndex = null
  const forceReplay = !!opts.forceReplay

  if (index > 0 && forceReplay) {
    replayThroughIndex = index - 1
  } else if (index > 0) {
    try {
      await ElMessageBox.confirm(
        `将在当前调试浏览器中接录，新步骤插入到第 ${index + 1} 步。\n\n` +
          '若浏览器已停留在目标页面（例如刚「调试到此步」或手动执行过），请选「直接接录」。\n' +
          '若页面还在起点/状态不对，请选「先回放再接录」。',
        '从这里开始录制',
        {
          confirmButtonText: '直接接录',
          cancelButtonText: '先回放再接录',
          distinguishCancelAndClose: true,
          type: 'info',
        },
      )
      replayThroughIndex = null
    } catch (action) {
      // Element Plus：cancel=点「先回放再接录」，close=点右上角关闭
      if (action === 'cancel') {
        replayThroughIndex = index - 1
      } else {
        return
      }
    }
  }

  recordPrepareEpoch += 1
  Object.assign(recordPreset, {
    defaultApplyMode: 'insert',
    insertAtIndex: index,
    debugSessionId: sess.id,
    deviceId: sess.device_id,
    presetMode: true,
    skipConfig: true,
    lockApplyMode: true,
    replayThroughIndex,
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
      `将打开交互调试，并从第 1 步执行到第 ${index} 步，然后在当前调试浏览器中接录、插入到第 ${index + 1} 步。`,
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

async function onToolbarRunSelected() {
  const indices = stepEditorRef.value?.getSelectedIndices?.() || []
  if (!indices.length) {
    ElMessage.warning('请先在步骤列表勾选要执行的步骤')
    return
  }
  await onDebugSelectedSteps(indices)
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
  window.addEventListener('beforeunload', onBeforeUnload)
  await getCaseDetail()
  await loadExecutionHints()
  await handleDebugFromStepQuery()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
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

.execution-hints-failures {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.execution-hints-code {
  margin: 0 4px;
  vertical-align: middle;
}

.execution-hints-fail-msg {
  color: var(--el-text-color-secondary);
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
