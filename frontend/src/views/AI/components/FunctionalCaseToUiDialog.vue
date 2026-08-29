<template>
  <el-dialog
    v-model="visible"
    title="🤖 功能用例 → Web 自动化"
    width="920px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px;"
    >
      <template #title>
        已选择 {{ caseIds.length }} 条功能用例，将<strong>逐条串行</strong>调用 AI 生成（单次最多 {{ maxBatch }} 条，3 条约需 3～10 分钟）
      </template>
    </el-alert>

    <!-- 配置 -->
    <el-form v-if="phase === 'config'" label-width="110px" class="to-ui-form">
      <FunctionalCaseUiContext v-model="uiContext" :project-id="projectId" />
      <el-form-item label="AI 模型" required>
        <el-select
          v-model="aiConfigId"
          placeholder="请选择已启用的模型"
          style="width: 100%;"
          :loading="loadingConfigs"
        >
          <el-option
            v-for="c in enabledConfigs"
            :key="c.id"
            :label="`${c.name} (${c.model})`"
            :value="c.id"
          />
        </el-select>
        <div class="field-hint">默认选中已启用的默认模型，可手动切换</div>
      </el-form-item>
      <el-form-item label="生成模式">
        <el-radio-group v-model="form.generation_mode">
          <el-radio value="single">单页面</el-radio>
          <el-radio value="explore">多轮探索</el-radio>
          <el-radio value="agent">Agent（MCP）</el-radio>
        </el-radio-group>
        <div class="field-hint" v-if="form.generation_mode === 'single'">
          抓取当前页 DOM，一次性生成（成本低，适合单页操作）
        </div>
        <div class="field-hint" v-else-if="form.generation_mode === 'explore'">
          执行→再抓 DOM→再生成，支持登录跳转（每轮 1 次 LLM）
        </div>
        <div class="field-hint" v-else>
          <strong>Agent（MCP）</strong>：基于无障碍树逐步规划并执行，适合复杂跨页流程；产出后请人工审核，不建议直接用于 CI 定时任务
        </div>
      </el-form-item>
      <el-form-item v-if="form.generation_mode !== 'single'" :label="form.generation_mode === 'agent' ? '最大步数' : '最大轮次'">
        <el-slider
          v-if="form.generation_mode === 'agent'"
          v-model="form.max_steps"
          :min="3"
          :max="30"
          show-stops
          show-input
        />
        <el-slider
          v-else
          v-model="form.max_rounds"
          :min="1"
          :max="5"
          show-stops
          show-input
        />
        <div class="field-hint">
          {{ form.generation_mode === 'agent'
            ? 'Agent 每步 1 次 LLM，条数多时每条串行，耗时较长'
            : '轮次过多易重复探索，建议 2～3 轮' }}
        </div>
      </el-form-item>
      <BrowserRunModeFields
        v-if="uiContext.page_url?.trim()"
        :form="form"
      />
      <el-form-item label="已选用例">
        <ul class="case-title-list">
          <li v-for="c in selectedCases" :key="c.id">{{ c.title }}</li>
        </ul>
      </el-form-item>
    </el-form>

    <!-- 生成中 -->
    <div v-else-if="phase === 'generating'" class="generating-box">
      <template v-if="(form.generation_mode === 'agent' || form.generation_mode === 'explore') && agentJobId">
        <p class="batch-progress">
          第 {{ agentBatchIndex + 1 }} / {{ caseIds.length }} 条：{{ currentCaseTitle }}
        </p>
        <UiAgentProgressPanel
          :visible="true"
          :job-id="agentJobId"
          :project-id="projectId"
          :title="form.generation_mode === 'explore' ? '探索进度' : 'Agent 进度'"
          :waiting-hint="form.generation_mode === 'explore' ? '正在多轮探索页面…' : 'Agent 正在探索页面…'"
          @done="onAgentBatchDone"
          @fail="onAgentBatchFail"
        />
      </template>
      <template v-else>
        <el-icon class="is-loading" :size="36"><Loading /></el-icon>
        <p>AI 正在生成 UI 步骤，请稍候…</p>
        <p class="hint">批量生成按条串行执行，条数较多时可能需数分钟</p>
      </template>
    </div>

    <!-- 预览结果 -->
    <div v-else-if="phase === 'preview'" class="preview-box">
      <div class="preview-summary">
        成功 {{ previewResult.success_count }} 条，失败 {{ previewResult.failed_count }} 条
        <span v-if="previewResult.total_tokens"> · Token {{ previewResult.total_tokens }}</span>
      </div>
      <el-table
        ref="previewTableRef"
        :data="previewItems"
        border
        stripe
        max-height="420"
        @selection-change="onPreviewSelect"
      >
        <el-table-column type="selection" width="45" :selectable="row => row.status === 'success'" />
        <el-table-column prop="title" label="功能用例" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="88" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="步骤数" width="80" align="center">
          <template #default="{ row }">{{ row.steps?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="登录前置" width="88" align="center">
          <template #default="{ row }">
            <span v-if="row.login_prefix_count">{{ row.login_prefix_count }} 步</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="UI 用例名" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.status === 'success'"
              v-model="row.suggested_case_name"
              size="small"
              maxlength="50"
            />
            <span v-else class="err-text">{{ row.error || '生成失败' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="等级" width="100">
          <template #default="{ row }">
            <el-select v-if="row.status === 'success'" v-model="row.suggested_level" size="small">
              <el-option label="P0" value="P0" />
              <el-option label="P1" value="P1" />
              <el-option label="P2" value="P2" />
              <el-option label="P3" value="P3" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="previewItems.some(i => i.errors?.length)"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 10px;"
        title="部分步骤存在校验提示，导入后可在 UI 用例编辑器中调整"
      />
    </div>

    <template #footer>
      <template v-if="phase === 'config'">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="handlePreview">开始生成预览</el-button>
      </template>
      <template v-else-if="phase === 'generating'">
        <el-button disabled>生成中…</el-button>
      </template>
      <template v-else-if="phase === 'preview'">
        <el-button @click="phase = 'config'">返回配置</el-button>
        <el-button @click="visible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!importSelected.length"
          @click="handleImport"
        >导入 UI 用例库 ({{ importSelected.length }})</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { aiFunctionalCaseApi } from '@/api/modules/ai.js'
import FunctionalCaseUiContext from '@/views/AI/components/FunctionalCaseUiContext.vue'
import UiAgentProgressPanel from '@/views/AI/components/UiAgentProgressPanel.vue'
import BrowserRunModeFields from '@/components/BrowserRunModeFields.vue'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const defaultUiContext = () => ({
  page_url: '',
  test_username: '',
  test_password: '',
  login_ui_case_id: null,
  login_strategy: 'none',
  extra_context: ''
})

const props = defineProps({
  modelValue: Boolean,
  caseIds: { type: Array, default: () => [] },
  cases: { type: Array, default: () => [] },
  projectId: { type: [Number, String], required: true }
})

const emit = defineEmits(['update:modelValue', 'done'])

const maxBatch = 10
const visible = ref(false)
const phase = ref('config')
const generating = ref(false)
const importing = ref(false)
const previewTableRef = ref(null)
const previewResult = reactive({ success_count: 0, failed_count: 0, total_tokens: 0 })
const importSelected = ref([])

const form = reactive({
  generation_mode: 'single',
  max_rounds: 3,
  max_steps: 15,
  run_mode: 'runner',
  device_id: null,
  headless: true,
})
const uiContext = reactive(defaultUiContext())

const previewItems = ref([])
const agentJobId = ref(null)
const agentBatchIndex = ref(0)
const currentCaseTitle = ref('')
let agentBatchResolve = null
let agentBatchReject = null

const buildContextPayload = () => ({
  page_url: uiContext.page_url?.trim() || undefined,
  ai_config_id: aiConfigId.value || undefined,
  test_username: uiContext.test_username?.trim() || undefined,
  test_password: uiContext.test_password || undefined,
  login_ui_case_id: uiContext.login_ui_case_id || undefined,
  login_strategy: uiContext.login_strategy || 'none',
  extra_context: uiContext.extra_context?.trim() || undefined,
  source_method: 'ai',
})

const buildPreviewPayload = () => ({
  case_ids: props.caseIds,
  ...buildContextPayload(),
  generation_mode: form.generation_mode,
  max_rounds: form.max_rounds,
  max_steps: form.max_steps,
  device_id: form.device_id || undefined,
  headless: form.headless,
})

const buildImportPayload = (rows) => ({
  ...buildPreviewPayload(),
  items: rows.map(row => ({
    functional_case_id: row.functional_case_id,
    steps: row.steps,
    case_name: row.suggested_case_name,
    level: row.suggested_level,
    record_id: row.record_id,
    login_prefix_count: row.login_prefix_count || 0,
  }))
})

const selectedCases = computed(() =>
  props.cases.filter(c => props.caseIds.includes(c.id))
)

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val) {
    phase.value = 'config'
    previewItems.value = []
    importSelected.value = []
    agentJobId.value = null
    agentBatchIndex.value = 0
    currentCaseTitle.value = ''
    form.run_mode = 'runner'
    form.device_id = null
    form.headless = true
    Object.assign(uiContext, defaultUiContext())
    await loadConfigs()
  }
})

watch(visible, (val) => emit('update:modelValue', val))

function onAgentBatchDone(job) {
  agentBatchResolve?.(job)
  agentBatchResolve = null
  agentBatchReject = null
}

function onAgentBatchFail(payload) {
  agentBatchReject?.(new Error(payload?.error_message || 'Agent 失败'))
  agentBatchResolve = null
  agentBatchReject = null
}

function waitAgentJobDone() {
  return new Promise((resolve, reject) => {
    agentBatchResolve = resolve
    agentBatchReject = reject
  })
}

async function handlePreviewAsyncSerial() {
  const isExplore = form.generation_mode === 'explore'
  const items = []
  let totalTokens = 0
  let successCount = 0
  let failedCount = 0
  const ctxPayload = buildContextPayload()

  for (let i = 0; i < props.caseIds.length; i += 1) {
    const caseId = props.caseIds[i]
    agentBatchIndex.value = i
    currentCaseTitle.value = selectedCases.value.find((c) => c.id === caseId)?.title || `#${caseId}`

    const startApi = isExplore
      ? aiFunctionalCaseApi.startToUiExploreJob
      : aiFunctionalCaseApi.startToUiAgentJob
    const startRes = await startApi({
      functional_case_id: caseId,
      ...(isExplore ? { max_rounds: form.max_rounds } : { max_steps: form.max_steps }),
      run_mode: form.run_mode,
      device_id: form.device_id || undefined,
      headless: form.headless,
      ...ctxPayload,
    }, props.projectId)

    if (startRes.data?.code !== 200) {
      throw new Error(startRes.data?.message || '创建任务失败')
    }
    const startData = startRes.data.data || {}
    agentJobId.value = startData.job_id

    await waitAgentJobDone()

    const finApi = isExplore
      ? aiFunctionalCaseApi.finalizeToUiExploreJob
      : aiFunctionalCaseApi.finalizeToUiAgentJob
    const finRes = await finApi({
      job_id: startData.job_id,
      functional_case_id: caseId,
      ...ctxPayload,
    }, props.projectId)

    if (finRes.data?.code !== 200) {
      throw new Error(finRes.data?.message || '汇总预览失败')
    }
    const item = finRes.data.data || {}
    items.push(item)
    totalTokens += Number(item.tokens_used || 0)
    if (item.status === 'success') successCount += 1
    else failedCount += 1
    agentJobId.value = null
  }

  previewItems.value = items
  previewResult.success_count = successCount
  previewResult.failed_count = failedCount
  previewResult.total_tokens = totalTokens
  phase.value = 'preview'
  const successRows = previewItems.value.filter((i) => i.status === 'success')
  importSelected.value = successRows
  await nextTick()
  successRows.forEach((row) => previewTableRef.value?.toggleRowSelection(row, true))
  ElMessage.success(`预览完成：成功 ${successCount} 条${failedCount ? `，失败 ${failedCount} 条` : ''}`)
}

async function handlePreviewAgentSerial() {
  return handlePreviewAsyncSerial()
}

const handlePreview = async () => {
  if (!enabledConfigs.value.length) {
    ElMessage.warning('没有已启用的 AI 模型，请先在 AI 模型配置中创建并启用')
    return
  }
  if (!aiConfigId.value) {
    ElMessage.warning('请选择 AI 模型')
    return
  }
  if (['explore', 'agent'].includes(form.generation_mode) && !uiContext.page_url?.trim()) {
    ElMessage.warning(`${form.generation_mode === 'agent' ? 'Agent' : '探索'}模式需填写目标页面 URL`)
    return
  }
  if (!uiContext.page_url?.trim()) {
    ElMessage.warning('请填写目标页面 URL（批量/非登录用例必填）')
    return
  }
  if (
    props.caseIds.length > 1 &&
    uiContext.login_strategy === 'none' &&
    !uiContext.extra_context?.trim()
  ) {
    ElMessage.warning('批量生成时建议填写「细节补充」，或选择登录策略')
    return
  }
  if (['prepend_login', 'both'].includes(uiContext.login_strategy) && !uiContext.login_ui_case_id) {
    ElMessage.warning('请选择登录 UI 用例')
    return
  }
  if (['credentials', 'both'].includes(uiContext.login_strategy) && !uiContext.test_username?.trim()) {
    ElMessage.warning('请填写测试账号用户名')
    return
  }
  if (!props.caseIds.length) {
    ElMessage.warning('请先勾选功能用例')
    return
  }
  if (props.caseIds.length > maxBatch) {
    ElMessage.warning(`单次最多 ${maxBatch} 条，请减少勾选数量`)
    return
  }

  if (
    (form.generation_mode === 'agent' || form.generation_mode === 'explore') &&
    !form.device_id
  ) {
    ElMessage.warning('请选择在线 Runner 执行设备')
    return
  }
  if (form.generation_mode === 'single' && uiContext.page_url?.trim() && !form.device_id) {
    ElMessage.warning('填写页面 URL 时请选择在线 Runner 执行设备')
    return
  }

  generating.value = true
  phase.value = 'generating'
  try {
    if (form.generation_mode === 'agent' || form.generation_mode === 'explore') {
      await handlePreviewAsyncSerial()
      return
    }
    const res = await aiFunctionalCaseApi.previewToUi(
      buildPreviewPayload(),
      props.projectId
    )
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      previewItems.value = (d.items || []).map(it => ({ ...it }))
      previewResult.success_count = d.success_count || 0
      previewResult.failed_count = d.failed_count || 0
      previewResult.total_tokens = d.total_tokens || 0
      phase.value = 'preview'
      const successRows = previewItems.value.filter(i => i.status === 'success')
      importSelected.value = successRows
      await nextTick()
      successRows.forEach(row => previewTableRef.value?.toggleRowSelection(row, true))
      ElMessage.success(res.data.message || '预览完成')
    }
  } catch (e) {
    phase.value = 'config'
    agentJobId.value = null
    ElMessage.error(e.response?.data?.detail || e.message || '生成预览失败')
  } finally {
    generating.value = false
  }
}

const onPreviewSelect = (rows) => {
  importSelected.value = rows
}

const handleImport = async () => {
  const rows = importSelected.value.length
    ? importSelected.value
    : previewItems.value.filter(i => i.status === 'success')
  if (!rows.length) {
    ElMessage.warning('请勾选要导入的用例')
    return
  }
  importing.value = true
  try {
    const res = await aiFunctionalCaseApi.importUi(
      buildImportPayload(rows),
      props.projectId
    )
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      ElMessage.success(res.data.message || `已导入 ${d.imported_count} 条`)
      visible.value = false
      emit('done', d)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

const handleClosed = () => {
  phase.value = 'config'
  previewItems.value = []
  importSelected.value = []
  agentJobId.value = null
  agentBatchIndex.value = 0
}
</script>

<style scoped lang="scss">
.to-ui-form { max-height: 55vh; overflow-y: auto; }
.case-title-list {
  margin: 0;
  padding-left: 18px;
  max-height: 120px;
  overflow-y: auto;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.generating-box {
  text-align: center;
  padding: 24px 0;
  .batch-progress {
    margin-bottom: 12px;
    font-size: 14px;
    color: var(--el-text-color-regular);
  }
  .hint { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 8px; }
}
.preview-summary {
  margin-bottom: 10px;
  font-size: 14px;
}
.err-text { color: var(--el-color-danger); font-size: 12px; }
.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
