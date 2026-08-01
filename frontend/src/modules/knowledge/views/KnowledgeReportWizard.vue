<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header><b>报告向导</b></template>
          <el-form :model="form" label-width="108px">
            <el-form-item label="报告类型">
              <el-radio-group v-model="form.report_kind" class="report-kind-group" @change="onReportKindChange">
                <el-radio-button v-for="k in displayReportKinds" :key="k.value" :value="k.value">
                  {{ k.label }}
                </el-radio-button>
              </el-radio-group>
              <div v-if="reportKindHint" class="field-hint kind-hint">{{ reportKindHint }}</div>
            </el-form-item>
            <el-form-item label="迭代文件夹">
              <el-select v-model="form.folder_id" clearable placeholder="可选" style="width: 100%;" @change="onFolderChange">
                <el-option v-for="f in folders" :key="f.id" :label="folderLabel(f)" :value="f.id" />
              </el-select>
            </el-form-item>
            <KnowledgeInputDocPicker
              v-if="form.folder_id && inputSlots.length"
              v-model="inputDocs"
              :slots="inputSlots"
              title="输入文档（按类型选择）"
              hint="仅下方勾选的文档会送入报告；右侧预览「纳入报告的资料」与选择一致。需求文档支持多选。"
            />
            <el-form-item label="输出模板">
              <el-select v-model="form.template_doc_id" clearable placeholder="默认：输出模板页「按类型映射」或内置" style="width: 100%;">
                <el-option v-for="t in templates" :key="t.id" :label="t.title" :value="t.id" />
              </el-select>
              <div class="field-hint">留空时按「输出模板 → 默认模板映射」中当前报告类型的配置生效。</div>
              <div v-if="templateHint" class="field-hint" :class="{ warn: templateHint.empty || templateHint.warn }">
                {{ templateHint.text }}
              </div>
            </el-form-item>
            <el-form-item label="执行记录">
              <el-select
                v-model="selectedExecKeys"
                multiple
                collapse-tags
                collapse-tags-tooltip
                :max-collapse-tags="3"
                placeholder="可选：API / UI / App 自动化执行记录（可多选）"
                style="width: 100%;"
                filterable
              >
                <el-option
                  v-for="r in execRecords"
                  :key="execKey(r)"
                  :label="execLabel(r)"
                  :value="execKey(r)"
                />
              </el-select>
              <div class="field-hint">{{ execRecordsHint }}</div>
            </el-form-item>
            <el-form-item label="AI 模型">
              <el-select v-model="aiConfigId" style="width: 100%;" clearable>
                <el-option
                  v-for="c in enabledConfigs"
                  :key="c.id"
                  :label="`${c.name} (${c.model})`"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="报告标题">
              <el-input v-model="form.title" placeholder="可选，默认同报告类型" />
            </el-form-item>
            <el-form-item label="编写人">
              <el-input v-model="form.author" placeholder="可选，默认同当前用户" />
            </el-form-item>

            <template v-if="wizardUserFields.length">
              <el-divider content-position="left">填写项</el-divider>
              <el-form-item
                v-for="field in wizardUserFields"
                :key="field.name"
                :label="field.label"
              >
                <TemplateVariableTableEditor
                  v-if="field.value_type === 'table'"
                  v-model="customTableRows[field.name]"
                  :schema="field.value_schema"
                  :hint="field.value_hint || '填写后写入 Word 表格循环'"
                />
                <el-date-picker
                  v-else-if="field.value_type === 'date'"
                  v-model="userVars[field.name]"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="选择日期"
                  style="width: 100%;"
                  clearable
                />
                <el-input
                  v-else-if="field.value_type === 'textarea' || field.value_type === 'lines'"
                  v-model="userVars[field.name]"
                  type="textarea"
                  :rows="field.value_type === 'lines' ? 4 : 3"
                  :placeholder="field.value_hint || field.description || field.default_value || ''"
                />
                <el-input
                  v-else
                  v-model="userVars[field.name]"
                  :placeholder="field.value_hint || field.description || field.default_value || ''"
                />
                <div v-if="field.value_hint" class="field-hint">{{ field.value_hint }}</div>
              </el-form-item>
            </template>

            <template v-if="form.report_kind === 'test_plan'">
              <el-divider content-position="left">进度与里程碑</el-divider>
              <div class="milestone-toolbar">
                <span class="field-hint">填写后写入计划第六章表格；留空则该行为空。</span>
                <el-button type="primary" link size="small" @click="addMilestoneRow">添加一行</el-button>
              </div>
              <el-table :data="milestoneRows" size="small" border class="milestone-table">
                <el-table-column label="里程碑" min-width="120">
                  <template #default="{ row }">
                    <el-input v-model="row.name" placeholder="如：测试设计" size="small" />
                  </template>
                </el-table-column>
                <el-table-column label="开始" width="148">
                  <template #default="{ row }">
                    <el-date-picker
                      v-model="row.start_date"
                      type="date"
                      value-format="YYYY-MM-DD"
                      placeholder="开始"
                      size="small"
                      style="width: 100%;"
                      clearable
                    />
                  </template>
                </el-table-column>
                <el-table-column label="结束" width="148">
                  <template #default="{ row }">
                    <el-date-picker
                      v-model="row.end_date"
                      type="date"
                      value-format="YYYY-MM-DD"
                      placeholder="结束"
                      size="small"
                      style="width: 100%;"
                      clearable
                    />
                  </template>
                </el-table-column>
                <el-table-column label="负责人" width="100">
                  <template #default="{ row }">
                    <el-input v-model="row.owner" placeholder="负责人" size="small" />
                  </template>
                </el-table-column>
                <el-table-column label="说明" min-width="100">
                  <template #default="{ row }">
                    <el-input v-model="row.remark" placeholder="可选" size="small" />
                  </template>
                </el-table-column>
                <el-table-column label="" width="52" align="center">
                  <template #default="{ $index }">
                    <el-button
                      link
                      type="danger"
                      size="small"
                      :disabled="milestoneRows.length <= 1"
                      @click="removeMilestoneRow($index)"
                    >删</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>

            <el-form-item>
              <el-button :loading="previewing" @click="previewInputs">预览数据</el-button>
              <el-button v-if="canExecute" type="primary" :loading="generating" @click="generate">生成 Word 报告</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card v-if="previewData" shadow="never" class="preview-card">
          <template #header><b>生成前预览</b></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="模板">{{ previewData.summary?.template_name }}</el-descriptions-item>
            <el-descriptions-item label="占位符">
              {{ previewData.summary?.template_known_count ?? 0 }} 个已知
              <el-tag v-if="previewData.summary?.template_empty" type="danger" size="small">无占位符</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Bug 总数">{{ previewData.summary?.bug_total ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="未关闭 Bug">{{ previewData.summary?.bug_open_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item v-if="previewData.summary?.bug_stats_row_count != null" label="缺陷分布行">
              {{ previewData.summary?.bug_stats_row_count ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item v-if="previewData.summary?.has_bug_data && !previewData.summary?.template_covers_bug" label="模板缺陷占位">
              <el-tag type="warning" size="small">未配置</el-tag>
              <span class="muted mapreduce-hint">
                当前模板缺少 bug_total / bug_stats_rows / bug_analysis_text 等占位符，「缺陷分析」章节可能为空。
                请在 Word 模板中加入 {{ bug_analysis_text }} 或改用内置模板。
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="通过率">{{ formatPassRate(previewData.summary) }}</el-descriptions-item>
            <el-descriptions-item label="用例总数">{{ previewData.summary?.total_cases ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="失败用例">{{ previewData.summary?.failed_case_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item v-if="previewData.summary?.mapreduce_on_generate" label="长文档处理">
              <el-tag type="warning" size="small">生成时将智能处理长文档</el-tag>
              <span class="muted mapreduce-hint">
                资料约 {{ previewData.summary?.knowledge_raw_chars ?? 0 }} 字；
                策略「{{ strategyLabel(previewData.summary?.context_strategy) }}」：
                优先摘要缓存 → RAG 检索 → Map-Reduce 分块提炼（Bug 统计仍完整解析）。
              </span>
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="form.folder_id && inputSlots.length" class="source-block">
            <div class="source-title">输入文档选择</div>
            <ul class="source-list slot-status-list">
              <li v-for="slot in inputSlots" :key="slot.key">
                <el-tag size="small" :type="selectedSlotLabels(slot).length ? 'success' : 'info'">{{ slot.label }}</el-tag>
                <span v-if="selectedSlotLabels(slot).length">{{ selectedSlotLabels(slot).join('；') }}</span>
                <span v-else class="muted">未选择</span>
              </li>
            </ul>
          </div>
          <div v-if="previewData.source_refs?.length" class="source-block">
            <div class="source-title">纳入报告的资料</div>
            <ul class="source-list">
              <li v-for="(ref, idx) in previewData.source_refs" :key="idx">
                <el-tag size="small" type="info">{{ ref.kind_label }}</el-tag>
                {{ ref.title }}
                <span v-if="ref.detail" class="muted">（{{ ref.detail }}）</span>
              </li>
            </ul>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="summaryDialog.visible" title="报告生成完成" width="480px">
      <el-descriptions v-if="summaryDialog.data" :column="1" border size="small">
        <el-descriptions-item label="报告">{{ summaryDialog.title }}</el-descriptions-item>
        <el-descriptions-item label="Bug 总数">{{ summaryDialog.data.bug_total }}</el-descriptions-item>
        <el-descriptions-item label="未关闭 / 已关闭">
          {{ summaryDialog.data.bug_open_count }} / {{ summaryDialog.data.bug_closed_count }}
        </el-descriptions-item>
        <el-descriptions-item label="通过率">{{ formatPassRate(summaryDialog.data) }}</el-descriptions-item>
        <el-descriptions-item label="用例总数">{{ summaryDialog.data.total_cases }}</el-descriptions-item>
        <el-descriptions-item label="失败用例">{{ summaryDialog.data.failed_case_count }}</el-descriptions-item>
        <el-descriptions-item label="模板占位符">
          {{ summaryDialog.data.template_known_count }} 个已知
          <span v-if="summaryDialog.data.template_empty">（无占位符，输出可能与原模板相同）</span>
        </el-descriptions-item>
      </el-descriptions>
      <div v-if="summaryDialog.sourceRefs?.length" class="source-block">
        <div class="source-title">本次报告使用的数据</div>
        <ul class="source-list">
          <li v-for="(ref, idx) in summaryDialog.sourceRefs" :key="idx">
            <el-tag size="small" type="info">{{ ref.kind_label }}</el-tag>
            {{ ref.title }}
            <span v-if="ref.detail" class="muted">（{{ ref.detail }}）</span>
          </li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="summaryDialog.visible = false">关闭</el-button>
        <el-button type="primary" @click="downloadFromSummary">下载报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import KnowledgeInputDocPicker from '@/modules/knowledge/components/KnowledgeInputDocPicker.vue'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import { pollIterationReportStatus } from '@/composables/useIterationReportPoll.js'
import TemplateVariableTableEditor from '@/modules/knowledge/components/TemplateVariableTableEditor.vue'
import {
  USER_WIZARD_BUILTIN,
  emptyTableRow,
  mapVariableToWizardField
} from '@/modules/knowledge/utils/templateVariableTypes.js'
import { parseExecQuery } from '@/utils/knowledgeReportNav.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'

const route = useRoute()

const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canExecute } = useKnowledgePermissions()
const { aiConfigId, enabledConfigs, loadConfigs, setScene } = useAiConfigSelect({ scene: 'iteration_report' })

function emptyMilestoneRow() {
  return { name: '', start_date: '', end_date: '', owner: '', remark: '' }
}

const folders = ref([])
const templates = ref([])
const execRecords = ref([])
const allVariables = ref([])
const selectedExecKeys = ref([])
const userVars = ref({})
const customTableRows = ref({})
const milestoneRows = ref([emptyMilestoneRow()])
const generating = ref(false)
const previewing = ref(false)
const previewData = ref(null)
const templateInspect = ref(null)
const inputSlots = ref([])
const inputDocs = ref({})
const summaryDialog = ref({ visible: false, data: null, reportId: null, title: '', sourceRefs: [] })
const reportKinds = ref([])

const DEFAULT_REPORT_KINDS = [
  { value: 'iteration_report', label: '迭代自动化测试报告', description: '汇总 API/UI/App 多份自动化执行记录与缺陷，适合迭代自动化收尾' },
  { value: 'functional_report', label: '功能测试报告', description: '侧重功能范围与手工/功能用例验证、缺陷分析' },
  { value: 'performance_report', label: '性能测试报告', description: '侧重性能指标、瓶颈与优化建议' },
  { value: 'test_plan', label: '测试计划', description: '测试目标、范围、策略与环境' },
  { value: 'test_scheme', label: '测试方案', description: '方案级说明，含策略、环境与准入准出' }
]

const reportKindHint = computed(() => {
  const list = reportKinds.value.length ? reportKinds.value : DEFAULT_REPORT_KINDS
  const hit = list.find(k => k.value === form.value.report_kind)
  return hit?.description || ''
})

const execRecordsHint = computed(() => {
  if (form.value.report_kind === 'iteration_report') {
    return '迭代自动化测试报告支持多选执行记录，将合并统计通过率、用例总数与失败用例摘要。不选则不含自动化执行数据。'
  }
  return '用于写入自动化通过率、用例总数、失败用例摘要。不选则不含执行数据。'
})

const displayReportKinds = computed(() => (
  reportKinds.value.length ? reportKinds.value : DEFAULT_REPORT_KINDS
))

const form = ref({
  report_kind: 'iteration_report',
  folder_id: null,
  template_doc_id: null,
  title: '',
  author: ''
})

const customVariables = computed(() => allVariables.value.filter(v => !v.builtin))

const wizardUserFields = computed(() => {
  const fields = []
  for (const v of allVariables.value) {
    if (!v.builtin || v.category !== 'user' || v.name === 'milestone_rows') continue
    if (!USER_WIZARD_BUILTIN.has(v.name)) continue
    if (['plan_start_date', 'plan_end_date', 'plan_owner'].includes(v.name) && form.value.report_kind !== 'test_plan') {
      continue
    }
    fields.push(mapVariableToWizardField(v))
  }
  for (const v of customVariables.value) {
    if (v.value_type === 'table' && !(v.value_schema?.columns || []).length) continue
    fields.push(mapVariableToWizardField(v))
  }
  return fields
})

const templateHint = computed(() => {
  const t = templateInspect.value
  if (!t) return null
  if (t.empty) {
    return { empty: true, warn: true, text: `模板「${t.template_name}」未发现占位符，生成结果将与原文件相同` }
  }
  const bugMissing = t.covers_bug_data === false
  const bugWarn = bugMissing
    ? '；模板未含缺陷占位符，「缺陷分析」可能为空（建议加入 {{ bug_analysis_text }}）'
    : ''
  if (t.unknown_count > 0) {
    return {
      empty: false,
      warn: bugMissing,
      text: `已识别 ${t.known_count} 个变量，${t.unknown_count} 个未注册${bugWarn}`
    }
  }
  return {
    empty: false,
    warn: bugMissing,
    text: `模板「${t.template_name}」已识别 ${t.known_count} 个占位符${bugWarn}`
  }
})

const REPORT_TYPE_LABEL = {
  api_suite: 'API套件',
  api_plan: 'API计划',
  ui_suite: 'UI套件',
  ui_task: 'UI计划',
  app_suite: 'App套件',
  app_plan: 'App计划'
}

function folderLabel(f) {
  return f.iteration_label ? `${f.name} (${f.iteration_label})` : f.name
}

function execKey(r) {
  return `${r.report_type}:${r.record_id}`
}

function execLabel(r) {
  const t = REPORT_TYPE_LABEL[r.report_type] || r.report_type
  return `[${t}] ${r.name} · ${r.pass_rate}% · ${r.total_cases}例`
}

function formatPassRate(summary) {
  if (!summary) return '-'
  const hasExec = (summary.exec_record_count ?? 0) > 0 || (summary.total_cases ?? 0) > 0
  if (!hasExec || summary.pass_rate == null) return '-'
  return `${summary.pass_rate}%`
}

const STRATEGY_LABEL = {
  auto: '自动',
  mapreduce: 'Map-Reduce',
  rag: 'RAG 检索',
  truncate: '硬截断'
}

function strategyLabel(v) {
  return STRATEGY_LABEL[v] || v || '自动'
}

function parseExecKeys(keys) {
  return keys.flatMap((k) => {
    const sep = k.indexOf(':')
    if (sep <= 0) return []
    const report_type = k.slice(0, sep)
    const record_id = Number(k.slice(sep + 1))
    if (!report_type || !Number.isFinite(record_id)) return []
    return [{ report_type, record_id }]
  })
}

function compactInputDocs(docs) {
  const out = {}
  for (const [key, val] of Object.entries(docs || {})) {
    if (Array.isArray(val)) {
      const ids = val.filter(Boolean)
      if (ids.length) out[key] = ids
    } else if (val) {
      out[key] = val
    }
  }
  return out
}

function resolvedInputDocs() {
  const out = { ...(inputDocs.value || {}) }
  for (const slot of inputSlots.value) {
    if (slot.multiple) {
      if (!Array.isArray(out[slot.key]) || !out[slot.key].length) {
        if (slot.default_ids?.length) out[slot.key] = [...slot.default_ids]
      }
      continue
    }
    if (!out[slot.key] && slot.default_id) out[slot.key] = slot.default_id
  }
  return compactInputDocs(out)
}

function selectedSlotLabels(slot) {
  const val = inputDocs.value?.[slot.key]
  const ids = slot.multiple
    ? (Array.isArray(val) ? val : val ? [val] : [])
    : (val ? [val] : [])
  return ids.map(id => {
    const hit = (slot.candidates || []).find(c => c.id === id)
    return hit?.file_name || hit?.title || `#${id}`
  })
}

function buildPayload(extra = {}) {
  const vars = {}
  for (const field of wizardUserFields.value) {
    if (field.value_type === 'table') {
      const rows = (customTableRows.value[field.name] || [])
        .map(r => {
          const out = {}
          for (const [k, v] of Object.entries(r || {})) {
            out[k] = v == null ? '' : String(v).trim()
          }
          return out
        })
        .filter(r => Object.values(r).some(v => v))
      if (rows.length) vars[field.name] = rows
      continue
    }
    const val = userVars.value[field.name]
    if (val == null || String(val).trim() === '') continue
    if (field.value_type === 'lines') {
      const lines = String(val).split('\n').map(s => s.trim()).filter(Boolean)
      if (lines.length) vars[field.name] = lines.map(line => ({ line }))
      continue
    }
    vars[field.name] = String(val).trim()
  }
  if (form.value.report_kind === 'test_plan') {
    const rows = milestoneRows.value
      .map(r => ({
        name: (r.name || '').trim(),
        start_date: r.start_date || '',
        end_date: r.end_date || '',
        owner: (r.owner || '').trim(),
        remark: (r.remark || '').trim()
      }))
      .filter(r => r.name || r.start_date || r.end_date || r.owner || r.remark)
    if (rows.length) vars.milestone_rows = rows
  }
  return {
    report_kind: form.value.report_kind,
    folder_id: form.value.folder_id || undefined,
    template_doc_id: form.value.template_doc_id || undefined,
    input_docs: form.value.folder_id ? resolvedInputDocs() : undefined,
    exec_records: parseExecKeys(selectedExecKeys.value),
    ai_config_id: aiConfigId.value || undefined,
    title: form.value.title || undefined,
    author: form.value.author || undefined,
    user_vars: Object.keys(vars).length ? vars : undefined,
    ...extra
  }
}

function initUserVars() {
  const next = { ...userVars.value }
  const tables = { ...customTableRows.value }
  for (const field of wizardUserFields.value) {
    if (field.value_type === 'table') {
      if (!tables[field.name]?.length) {
        tables[field.name] = [emptyTableRow(field.value_schema)]
      }
      continue
    }
    if (next[field.name] === undefined) {
      next[field.name] = field.default_value || ''
    }
  }
  userVars.value = next
  customTableRows.value = tables
}

function addMilestoneRow() {
  milestoneRows.value.push(emptyMilestoneRow())
}

function removeMilestoneRow(index) {
  if (milestoneRows.value.length <= 1) return
  milestoneRows.value.splice(index, 1)
}

function resetMilestoneRows() {
  milestoneRows.value = [emptyMilestoneRow()]
}

async function refreshTemplateInspect() {
  if (!projectId.value) return
  try {
    const res = await knowledgeApi.inspectReportTemplate(projectId.value, {
      template_doc_id: form.value.template_doc_id || undefined,
      report_kind: form.value.report_kind
    })
    templateInspect.value = res.data || null
  } catch {
    templateInspect.value = null
  }
}

watch(wizardUserFields, () => initUserVars(), { deep: true })

async function onReportKindChange(kind) {
  setScene(kind)
  aiConfigId.value = null
  if (kind !== 'test_plan') {
    resetMilestoneRows()
  }
  await loadConfigs(kind)
  await loadTemplatesForKind(kind)
  await refreshTemplateInspect()
  await loadFolderInputSlots()
  initUserVars()
}

async function loadTemplatesForKind(kind) {
  if (!projectId.value) return
  try {
    const res = await knowledgeApi.listDocuments(projectId.value, { doc_type: 'report_template', size: 50 })
    templates.value = res.data?.items || []
  } catch {
    templates.value = []
  }
}

async function onFolderChange() {
  await loadFolderInputSlots()
}

async function loadFolderInputSlots() {
  if (!projectId.value || !form.value.folder_id) {
    inputSlots.value = []
    inputDocs.value = {}
    return
  }
  try {
    const res = await knowledgeApi.getFolderReportInputSlots(
      form.value.folder_id,
      projectId.value,
      form.value.report_kind
    )
    inputSlots.value = res.data?.input_slots || []
    inputDocs.value = { ...(res.data?.default_input_docs || {}) }
    for (const slot of inputSlots.value) {
      if (slot.multiple && slot.default_ids?.length && !inputDocs.value[slot.key]?.length) {
        inputDocs.value[slot.key] = [...slot.default_ids]
      }
    }
  } catch {
    inputSlots.value = []
    inputDocs.value = {}
  }
}

async function loadVariables() {
  if (!projectId.value) return
  try {
    const res = await knowledgeApi.getTemplateVariables(projectId.value)
    allVariables.value = res.data?.items || []
    initUserVars()
  } catch {
    allVariables.value = []
  }
}

async function loadMeta() {
  if (!projectId.value) return
  const [fRes, eRes, metaRes] = await Promise.all([
    knowledgeApi.listFolders(projectId.value),
    knowledgeApi.listRecentExecRecords(projectId.value),
    knowledgeApi.getMeta()
  ])
  folders.value = fRes.data?.items || []
  execRecords.value = eRes.data?.items || []
  reportKinds.value = metaRes.data?.report_kinds || []
  await loadTemplatesForKind(form.value.report_kind)
}

async function previewInputs() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  previewing.value = true
  try {
    const res = await knowledgeApi.previewIterationReport(buildPayload(), projectId.value)
    previewData.value = res.data || null
    templateInspect.value = res.data?.template || null
  } catch (e) {
    ElMessage.error(e?.message || '预览失败')
  } finally {
    previewing.value = false
  }
}

async function confirmTemplateIfNeeded() {
  if (!templateInspect.value) {
    await refreshTemplateInspect()
  }
  const t = templateInspect.value
  if (t?.empty) {
    try {
      await ElMessageBox.confirm(
        `模板「${t.template_name}」未发现任何 {{ 变量 }} 占位符，生成结果将与原模板相同。是否仍继续？`,
        '模板占位符警告',
        { type: 'warning', confirmButtonText: '仍要生成', cancelButtonText: '取消' }
      )
    } catch {
      return false
    }
  }
  if (t?.covers_bug_data === false && (previewData.value?.summary?.has_bug_data || previewData.value?.summary?.bug_total > 0)) {
    try {
      await ElMessageBox.confirm(
        '当前输出模板未包含缺陷相关占位符（如 bug_analysis_text），Word 中「缺陷分析」章节可能无数据。'
        + '建议在模板中加入 {{ bug_analysis_text }} 或清空「输出模板」使用内置模板。是否仍继续？',
        '缺陷分析占位符缺失',
        { type: 'warning', confirmButtonText: '仍要生成', cancelButtonText: '取消' }
      )
    } catch {
      return false
    }
  }
  return true
}

async function generate() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!(await confirmTemplateIfNeeded())) return

  generating.value = true
  try {
    const res = await knowledgeApi.createIterationReport(buildPayload(), projectId.value)
    const rid = res.data?.id
    if (!rid) {
      ElMessage.success(res.message || '任务已提交')
      return
    }
    if (res.data?.status === 'ready') {
      summaryDialog.value = {
        visible: true,
        data: res.data.summary || null,
        reportId: rid,
        title: res.data.title || '报告',
        sourceRefs: res.data.source_refs || []
      }
      return
    }
    ElMessage.info('报告生成中，请稍候…')
    const finalData = await pollIterationReportStatus(rid, projectId.value)
    summaryDialog.value = {
      visible: true,
      data: finalData.summary || null,
      reportId: rid,
      title: finalData.title || '报告',
      sourceRefs: finalData.source_refs || []
    }
  } catch (e) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value = false
  }
}

async function applyRoutePrefill() {
  const q = route.query || {}
  if (q.report_kind) {
    const kind = String(q.report_kind)
    const allowed = displayReportKinds.value.map((k) => k.value)
    form.value.report_kind = allowed.includes(kind) ? kind : 'iteration_report'
    setScene(form.value.report_kind)
  }
  if (q.title) form.value.title = String(q.title)
  if (q.folder_id) form.value.folder_id = Number(q.folder_id) || null
  const execKeys = parseExecQuery(q.exec)
  if (execKeys.length) {
    selectedExecKeys.value = execKeys.filter((k) =>
      execRecords.value.some((r) => execKey(r) === k)
    )
    if (!selectedExecKeys.value.length) {
      selectedExecKeys.value = execKeys
    }
  }
}

watch(() => route.query, async () => {
  if (execRecords.value.length) await applyRoutePrefill()
})

onMounted(async () => {
  await loadConfigs('iteration_report')
  await loadVariables()
  await loadMeta()
  await refreshTemplateInspect()
  await applyRoutePrefill()
})

async function download(row) {
  try {
    const blob = await knowledgeApi.downloadIterationReport(row.id, projectId.value)
    triggerDownload(blob, `${row.title || '迭代报告'}.docx`)
  } catch (e) {
    ElMessage.error(e?.message || '下载失败')
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadFromSummary() {
  const { reportId, title } = summaryDialog.value
  if (!reportId) return
  await download({ id: reportId, title })
  summaryDialog.value.visible = false
}

watch(
  () => [form.value.template_doc_id, form.value.report_kind],
  () => { refreshTemplateInspect() }
)

watch(projectId, async () => {
  previewData.value = null
  await loadVariables()
  await loadMeta()
  await refreshTemplateInspect()
})
</script>

<style scoped>
.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: 4px;
}
.field-hint.warn {
  color: var(--el-color-warning);
}
.kind-hint {
  color: var(--el-text-color-regular);
}
.report-kind-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.source-block {
  margin-top: 12px;
}
.source-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.source-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
}
.source-list .muted {
  color: var(--el-text-color-secondary);
}
.mapreduce-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.preview-card {
  margin-bottom: 0;
}
.milestone-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.milestone-table {
  margin-bottom: 12px;
}
</style>
