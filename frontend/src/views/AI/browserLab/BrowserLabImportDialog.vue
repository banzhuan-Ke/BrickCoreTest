<template>
  <el-dialog
    v-model="visible"
    title="导入 Web 自动化用例"
    width="980px"
    destroy-on-close
    @closed="handleClosed"
  >
    <el-alert
      v-if="importPlan.reason"
      :type="planAlertType"
      :closable="false"
      show-icon
      class="plan-alert"
    >
      <template #title>智能推荐：{{ planModeLabel }}</template>
      {{ importPlan.reason }}
      <span v-if="qualityScore != null" class="quality-score">质量分 {{ qualityScore }}</span>
    </el-alert>

    <el-radio-group v-model="importMode" class="mode-switch" @change="onModeChange">
      <el-radio value="draft">快速转换</el-radio>
      <el-radio value="agent">Agent 重新固化</el-radio>
    </el-radio-group>

    <!-- 快速转换 -->
    <div v-if="importMode === 'draft'" v-loading="loading" class="draft-panel">
      <el-alert type="info" :closable="false" show-icon class="tip">
        <template #title>由智能浏览器执行记录生成 Web 用例草稿</template>
        Runner 已采集 DOM 元数据并生成多定位候选（类似录制）；可在下表切换主定位。
        有动作缓存时优先用缓存步骤；弱定位多时再考虑 Agent 固化。
      </el-alert>

      <el-form label-width="108px" class="form" inline>
        <el-form-item label="用例名称" required>
          <el-input v-model="form.case_name" maxlength="200" show-word-limit style="width: 280px;" />
        </el-form-item>
        <el-form-item v-if="cacheAvailable" label="步骤来源">
          <el-radio-group v-model="stepsSource" @change="loadPreview">
            <el-radio value="auto">自动</el-radio>
            <el-radio value="cache">动作缓存</el-radio>
            <el-radio value="steps">执行记录</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="打开浏览器">
          <el-switch v-model="form.include_open_browser" @change="loadPreview" />
        </el-form-item>
      </el-form>

      <el-form label-width="108px" class="form">
        <el-form-item label="用例描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="4000" show-word-limit />
        </el-form-item>
      </el-form>

      <div class="stats-row">
        <el-tag v-if="weakLocatorCount > 0" type="warning">需核对 {{ weakLocatorCount }} 步</el-tag>
        <el-tag v-if="stepsWithCandidates > 0" type="success">多定位 {{ stepsWithCandidates }} 步</el-tag>
        <el-tag v-if="harvestedCount > 0" type="info">Runner 采集 {{ harvestedCount }} 步</el-tag>
        <el-tag v-if="cacheAvailable" type="primary">动作缓存可用</el-tag>
      </div>

      <div v-if="warnings.length" class="warnings">
        <el-text type="warning">规范化：{{ warnings.join('；') }}</el-text>
      </div>
      <div v-if="importWarnings.length" class="import-warnings">
        <el-text type="warning">
          导入提示：{{ importWarnings.map((w) => w.message || w.reason).join('；') }}
        </el-text>
      </div>

      <el-table
        :data="draftSteps"
        size="small"
        max-height="380"
        border
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" width="46" />
        <el-table-column prop="desc" label="操作" min-width="120" show-overflow-tooltip />
        <el-table-column prop="method" label="method" width="110" />
        <el-table-column label="质量" width="88" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="qualityTag(row).type">{{ qualityTag(row).text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="定位器" min-width="280">
          <template #default="{ row }">
            <LocatorSelector
              v-if="isLocatorStep(row)"
              :model-value="row.params?.locator || ''"
              :meta="row.meta || {}"
              @update:model-value="(v) => onLocatorChange(row, v)"
            />
            <span v-else class="param-preview">{{ paramPreview(row) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !draftSteps.length" description="无可导入步骤" />
    </div>

    <!-- Agent 固化 -->
    <div v-else class="agent-panel">
      <el-alert type="info" :closable="false" show-icon class="tip">
        <template #title>Playwright UI Agent 重新探索并固化</template>
        基于任务 URL、描述、执行摘要与缓存提示重新执行 Agent，产出可回归定位器。
        适合页面复杂、快速转换弱定位较多、或需正式回归的场景。
      </el-alert>

      <el-form label-width="108px" class="form">
        <el-form-item label="用例名称" required>
          <el-input v-model="form.case_name" maxlength="200" show-word-limit />
        </el-form-item>
        <BrowserLabTaskTextField
          v-model="form.agent_goal"
          label="Agent 固化目标"
          :rows="4"
          :placeholder="'逐步执行目标，如：1. 登录 2. 进入 Web 自动化 3. 搜索用例…'"
          :start-url="taskStartUrl"
          :case-name="form.case_name"
          :project-id="projectId"
          optimize-scene="ui_agent_solidify"
          label-tooltip="固化 job 实际使用的目标描述；与下方「用例描述」不同，后者仅写入导入后的用例元数据"
        />
        <el-form-item label="用例描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="4000" show-word-limit placeholder="导入 Web 用例后的描述（可选）" />
        </el-form-item>
        <el-form-item label="最大步数">
          <el-slider v-model="form.max_steps" :min="3" :max="30" show-input style="max-width: 420px;" />
        </el-form-item>
        <el-form-item label="打开浏览器">
          <el-switch v-model="form.include_open_browser" />
        </el-form-item>
        <BrowserRunModeFields :form="form" />
      </el-form>

      <div v-if="!solidifyJobId && !solidifyDone" class="actions">
        <el-button type="primary" :loading="solidifying" @click="startSolidify">
          开始 Agent 固化
        </el-button>
        <el-button v-if="draftSteps.length" link type="primary" @click="switchToDraft">
          改用快速转换（{{ draftSteps.length }} 步预览）
        </el-button>
      </div>

      <UiAgentProgressPanel
        v-if="solidifyJobId && !solidifyDone"
        :visible="true"
        :job-id="solidifyJobId"
        :project-id="projectId"
        title="固化进度"
        waiting-hint="Agent 正在探索页面并固化定位器…"
        @done="onSolidifyDone"
        @fail="onSolidifyFail"
      />

      <div v-if="solidifyDone && agentSteps.length" class="result-block">
        <el-alert :type="solidifyPartial ? 'warning' : 'success'" :closable="false" show-icon>
          <template v-if="solidifyPartial">
            Agent 探索未完整完成，共 {{ agentSteps.length }} 步，核对后仍可导入
          </template>
          <template v-else>
            Agent 固化完成，共 {{ agentSteps.length }} 步，可直接导入
          </template>
        </el-alert>
        <el-table :data="agentSteps" size="small" max-height="300" border class="steps-table">
          <el-table-column type="index" width="46" />
          <el-table-column prop="desc" label="操作" min-width="140" show-overflow-tooltip />
          <el-table-column prop="method" label="method" width="120" />
          <el-table-column label="定位/参数" min-width="220">
            <template #default="{ row }">
              <span class="param-preview">{{ paramPreview(row) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <template v-if="importMode === 'agent'">
        <el-button
          v-if="solidifyDone"
          type="primary"
          :loading="submitting"
          :disabled="!agentSteps.length"
          @click="submitAgentImport"
        >
          导入并打开编辑
        </el-button>
      </template>
      <template v-else>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!draftSteps.length"
          @click="submitDraftImport"
        >
          导入草稿并打开编辑
        </el-button>
        <el-button
          v-if="weakLocatorCount >= 2"
          link
          type="warning"
          @click="switchToSolidify"
        >
          弱定位较多，去 Agent 固化
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { browserLabApi } from '@/api/modules/ai.js'
import BrowserRunModeFields from '@/components/BrowserRunModeFields.vue'
import BrowserLabTaskTextField from './BrowserLabTaskTextField.vue'
import LocatorSelector from '@/components/LocatorSelector.vue'
import UiAgentProgressPanel from '@/views/AI/components/UiAgentProgressPanel.vue'
import { meaningfulUiAgentSteps, notifyUiAgentJobOutcome } from '@/views/AI/components/uiAgentJobHelpers.js'
import {
  importModeFromRecommended,
  isLocatorStep,
  onLocatorChange,
  paramPreview,
  qualityTag,
} from './browserLabImportHelpers.js'

const props = defineProps({
  taskId: { type: [Number, String], required: true },
  projectId: { type: [Number, String], required: true },
  defaultCaseName: { type: String, default: '' },
  taskText: { type: String, default: '' },
  taskStartUrl: { type: String, default: '' },
  taskDeviceId: { type: String, default: '' },
})

const visible = defineModel({ type: Boolean, default: false })
const router = useRouter()

const importMode = ref('draft')
const stepsSource = ref('auto')
const loading = ref(false)
const submitting = ref(false)
const solidifying = ref(false)
const solidifyJobId = ref(null)
const lastSolidifyJobId = ref(null)
const solidifyDone = ref(false)
const solidifyPartial = ref(false)
const agentSteps = ref([])
const draftSteps = ref([])
const warnings = ref([])
const importWarnings = ref([])
const weakLocatorCount = ref(0)
const stepsWithCandidates = ref(0)
const harvestedCount = ref(0)
const cacheAvailable = ref(false)
const qualityScore = ref(null)
const importPlan = ref({ recommended_mode: 'quick_steps', reason: '' })

const form = reactive({
  case_name: '',
  description: '',
  agent_goal: '',
  include_open_browser: true,
  max_steps: 15,
  run_mode: 'runner',
  device_id: null,
  headless: true,
})

const planModeLabel = computed(() => {
  const m = importPlan.value.recommended_mode
  if (m === 'quick_cache') return '快速转换（动作缓存）'
  if (m === 'solidify') return 'Agent 重新固化'
  if (m === 'quick_steps') return '快速转换（执行记录）'
  return '等待任务完成'
})

const planAlertType = computed(() => {
  const m = importPlan.value.recommended_mode
  if (m === 'solidify') return 'warning'
  if (m === 'quick_cache') return 'success'
  return 'info'
})

watch(visible, async (v) => {
  if (!v) return
  form.case_name = props.defaultCaseName || `BrowserLab-${props.taskId}`
  form.agent_goal = props.taskText || ''
  form.description = props.taskText
    ? `来源：智能浏览器 #${props.taskId}\n${props.taskText}`
    : ''
  form.run_mode = 'runner'
  form.device_id = props.taskDeviceId || null
  stepsSource.value = 'auto'
  resetSolidify()
  await loadPreview()
  importMode.value = importModeFromRecommended(importPlan.value.recommended_mode)
  const rec = importPlan.value.recommended_mode
  if (rec === 'quick_cache' && cacheAvailable.value) {
    stepsSource.value = 'cache'
    await loadPreview()
  } else if (rec === 'quick_steps') {
    stepsSource.value = 'steps'
  }
})

function resetSolidify() {
  solidifyJobId.value = null
  lastSolidifyJobId.value = null
  solidifyDone.value = false
  solidifyPartial.value = false
  agentSteps.value = []
  solidifying.value = false
}

function onModeChange(mode) {
  if (mode === 'draft') loadPreview()
  else resetSolidify()
}

function switchToDraft() {
  importMode.value = 'draft'
}

function switchToSolidify() {
  importMode.value = 'agent'
  resetSolidify()
}

function rowClassName({ row }) {
  const meta = row?.meta || {}
  if (meta.needs_manual_locator || meta.locator_strength === 'weak') return 'weak-locator-row'
  return ''
}

async function loadPreview() {
  if (!props.taskId || !props.projectId) return
  loading.value = true
  try {
    const res = await browserLabApi.previewUiSteps(props.taskId, props.projectId, {
      include_open_browser: form.include_open_browser,
      steps_source: stepsSource.value,
    })
    const data = res.data?.data || res.data
    draftSteps.value = (data?.steps || []).map((s) => ({ ...s, params: { ...(s.params || {}) }, meta: { ...(s.meta || {}) } }))
    warnings.value = data?.warnings || []
    importWarnings.value = data?.import_warnings || []
    weakLocatorCount.value = data?.weak_locator_count || 0
    stepsWithCandidates.value = data?.steps_with_candidates || data?.import_plan?.steps_with_candidates || 0
    harvestedCount.value = data?.import_plan?.harvested_step_count || 0
    cacheAvailable.value = Boolean(data?.cache_available)
    qualityScore.value = data?.quality_score ?? null
    importPlan.value = data?.import_plan || {}
    if (data?.task_device_id && !form.device_id) form.device_id = data.task_device_id
    if (data?.default_case_name && !props.defaultCaseName) form.case_name = data.default_case_name
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '预览步骤失败')
    draftSteps.value = []
  } finally {
    loading.value = false
  }
}

async function startSolidify() {
  if (!form.case_name.trim()) {
    ElMessage.warning('请填写用例名称')
    return
  }
  if (form.run_mode === 'runner' && !form.device_id) {
    ElMessage.warning('Runner 模式请选择在线执行设备')
    return
  }
  solidifyJobId.value = null
  lastSolidifyJobId.value = null
  solidifyDone.value = false
  agentSteps.value = []
  solidifying.value = true
  try {
    const res = await browserLabApi.solidifyUiCase(
      props.taskId,
      {
        case_name: form.case_name.trim(),
        max_steps: form.max_steps,
        run_mode: form.run_mode,
        device_id: form.device_id || undefined,
        include_open_browser: form.include_open_browser,
        headless: form.headless !== false,
        agent_goal_text: form.agent_goal.trim() || undefined,
      },
      props.projectId,
    )
    const data = res.data?.data || res.data
    if (data?.job_id) {
      solidifyJobId.value = data.job_id
      ElMessage.success('Agent 固化已启动')
    } else {
      ElMessage.error('未返回任务 ID')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动固化失败')
  } finally {
    solidifying.value = false
  }
}

function onSolidifyDone(job) {
  solidifyDone.value = true
  lastSolidifyJobId.value = job?.id || solidifyJobId.value
  solidifyJobId.value = null
  agentSteps.value = job?.steps || []
  const outcome = notifyUiAgentJobOutcome(job, ElMessage, {
    partialMessage: 'Agent 探索未完整完成，可核对步骤后仍尝试导入',
    sparseOptions: {
      message: `固化仅 ${meaningfulUiAgentSteps(agentSteps.value).length} 步有效操作，可能未完整执行目标；建议检查后再导入或改用快速转换`,
    },
  })
  solidifyPartial.value = outcome.partial
}

function onSolidifyFail(payload) {
  lastSolidifyJobId.value = payload?.job?.id || solidifyJobId.value
  solidifyJobId.value = null
  ElMessage.error(payload?.error_message || 'Agent 固化失败')
}

async function submitAgentImport() {
  if (!form.case_name.trim() || !agentSteps.value.length || !lastSolidifyJobId.value) {
    ElMessage.warning('无步骤可导入')
    return
  }
  submitting.value = true
  try {
    const res = await browserLabApi.importUiCase(
      props.taskId,
      {
        case_name: form.case_name.trim(),
        description: form.description.trim() || undefined,
        steps: agentSteps.value,
        solidify_job_id: lastSolidifyJobId.value,
        include_open_browser: form.include_open_browser,
      },
      props.projectId,
    )
    await doImportSuccess(res)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    submitting.value = false
  }
}

async function submitDraftImport() {
  if (!form.case_name.trim()) {
    ElMessage.warning('请填写用例名称')
    return
  }
  submitting.value = true
  try {
    const res = await browserLabApi.importUiCase(
      props.taskId,
      {
        case_name: form.case_name.trim(),
        description: form.description.trim() || undefined,
        include_open_browser: form.include_open_browser,
        steps_source: stepsSource.value,
        steps: draftSteps.value,
      },
      props.projectId,
    )
    await doImportSuccess(res)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    submitting.value = false
  }
}

async function doImportSuccess(res) {
  const data = res.data?.data || res.data
  ElMessage.success(res.data?.message || '导入成功')
  visible.value = false
  if (data?.case_id) router.push({ name: 'editCase', params: { id: data.case_id } })
}

function handleClosed() {
  draftSteps.value = []
  warnings.value = []
  importWarnings.value = []
  weakLocatorCount.value = 0
  stepsWithCandidates.value = 0
  harvestedCount.value = 0
  cacheAvailable.value = false
  stepsSource.value = 'auto'
  resetSolidify()
}
</script>

<style scoped>
.mode-switch { margin-bottom: 12px; }
.plan-alert { margin-bottom: 12px; }
.quality-score { margin-left: 8px; font-size: 12px; opacity: 0.85; }
.tip { margin-bottom: 12px; }
.form { margin-bottom: 8px; }
.stats-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.actions { margin: 12px 0; }
.result-block { margin-top: 12px; }
.steps-table { margin-top: 10px; }
.warnings, .import-warnings { margin-bottom: 8px; }
.param-preview { font-family: monospace; font-size: 12px; }
:deep(.weak-locator-row) { background-color: var(--el-color-warning-light-9); }
</style>
