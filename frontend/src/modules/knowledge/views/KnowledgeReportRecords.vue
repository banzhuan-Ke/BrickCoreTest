<template>
  <div>
    <div class="toolbar">
      <el-select v-model="kindFilter" clearable placeholder="报告类型" size="small" style="width: 140px;">
        <el-option label="迭代自动化测试报告" value="iteration_report" />
        <el-option label="功能测试报告" value="functional_report" />
        <el-option label="性能测试报告" value="performance_report" />
        <el-option label="测试计划" value="test_plan" />
        <el-option label="测试方案" value="test_scheme" />
        <el-option label="定制方案" :value="PACK_KIND_SCHEME" />
        <el-option label="定制报告" :value="PACK_KIND_REPORT" />
        <el-option label="质量回顾" :value="PACK_KIND_QUALITY" />
        <el-option label="Bug统计" :value="PACK_KIND_BUG_WORKBOOK" />
      </el-select>
      <el-input
        v-model="titleFilter"
        clearable
        placeholder="按标题搜索"
        size="small"
        class="title-filter"
      />
      <el-button size="small" @click="loadReports">刷新</el-button>
      <el-tag v-if="polling" type="warning" size="small">生成中，自动刷新…</el-tag>
      <router-link to="/ai-knowledge/reports" class="wizard-link">去报告向导生成</router-link>
    </div>

    <div v-if="selectedReports.length && (canExecute || canEdit)" class="batch-select-bar">
      <span>已选 <b>{{ selectedReports.length }}</b> 条记录</span>
      <el-button
        size="small"
        :disabled="batchRunning"
        :loading="batchRunning && batchKind === 'download'"
        @click="batchDownload"
      >
        批量下载
      </el-button>
      <el-button
        v-if="canExecute"
        size="small"
        type="warning"
        :disabled="batchRunning"
        :loading="batchRunning && batchKind === 'retry'"
        @click="batchRetry"
      >
        批量重试
      </el-button>
      <el-button
        v-if="canEdit"
        size="small"
        type="danger"
        :disabled="batchRunning"
        :loading="batchRunning && batchKind === 'delete'"
        @click="batchDelete"
      >
        批量删除
      </el-button>
      <el-button size="small" link :disabled="batchRunning" @click="clearSelection">取消选择</el-button>
    </div>

    <el-table
      ref="reportTableRef"
      row-key="id"
      :data="paginatedReports"
      v-loading="loading"
      stripe
      size="small"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="46" fixed="left" reserve-selection :selectable="rowSelectable" />
      <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
      <el-table-column label="类型" width="108">
        <template #default="{ row }">{{ reportKindLabel(row.report_kind) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_by" label="创建人" width="100" show-overflow-tooltip />
      <el-table-column prop="create_time" label="生成时间" width="168">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showDetail(row)">详情</el-button>
          <el-button v-if="row.status === 'ready'" link type="primary" @click="download(row)">下载</el-button>
          <el-button v-if="row.status === 'failed' && canExecute" link type="warning" :loading="retryingId === row.id" @click="retry(row)">重试</el-button>
          <el-button link type="info" @click="showSources(row)">来源</el-button>
          <el-button v-if="canEdit" link type="danger" :loading="deletingId === row.id" @click="removeReport(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="filteredReports.length"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        small
        background
      />
    </div>

    <el-dialog v-model="sourceDialog.visible" title="报告数据来源" width="520px">
      <el-empty v-if="!sourceDialog.refs?.length" description="暂无记录" />
      <ul v-else class="source-list">
        <li v-for="(ref, idx) in sourceDialog.refs" :key="idx">
          <el-tag size="small" type="info">{{ ref.kind_label }}</el-tag>
          {{ ref.title }}
          <span v-if="ref.detail" class="muted">（{{ ref.detail }}）</span>
        </li>
      </ul>
    </el-dialog>

    <el-dialog v-model="detailDialog.visible" :title="detailDialog.title" width="640px">
      <div v-loading="detailDialog.loading">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="状态">{{ statusLabel(detailDialog.data?.status) }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ reportKindLabel(detailDialog.data?.report_kind) }}</el-descriptions-item>
          <el-descriptions-item label="Token">{{ detailDialog.data?.tokens_used ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(detailDialog.data?.duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ detailDialog.data?.created_by || '—' }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ formatTime(detailDialog.data?.create_time) }}</el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="detailDialog.data?.error" type="error" :title="detailDialog.data.error" show-icon :closable="false" style="margin-top: 12px;" />
        <div v-if="detailDialog.data?.summary" class="summary-block">
          <div class="summary-title">生成摘要</div>
          <pre class="summary-pre">{{ formatSummary(detailDialog.data.summary) }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button v-if="detailDialog.data?.status === 'ready'" type="primary" @click="downloadFromDetail">下载</el-button>
        <el-button v-if="detailDialog.data?.status === 'failed' && canExecute" type="warning" @click="retryFromDetail">重试</el-button>
        <el-button v-if="canEdit" type="danger" @click="removeFromDetail">删除</el-button>
        <el-button @click="detailDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'
import { hasInFlightReports, mergeReportRow } from '@/composables/useIterationReportPoll.js'

const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canEdit, canExecute } = useKnowledgePermissions()
const PACK_PREFIX = ['digi', 'tech'].join('')
const PACK_KIND_SCHEME = `${PACK_PREFIX}_scheme`
const PACK_KIND_REPORT = `${PACK_PREFIX}_report`
const PACK_KIND_QUALITY = `${PACK_PREFIX}_quality`
const PACK_KIND_BUG_WORKBOOK = `${PACK_PREFIX}_bug_workbook`

const REPORT_KIND_LABEL = {
  iteration_report: '自动化',
  functional_report: '功能',
  performance_report: '性能',
  test_plan: '计划',
  test_scheme: '方案',
  [PACK_KIND_SCHEME]: '定制方案',
  [PACK_KIND_REPORT]: '定制报告',
  [PACK_KIND_QUALITY]: '质量回顾',
  [PACK_KIND_BUG_WORKBOOK]: 'Bug统计',
  quality_review: '质量回顾（历史）'
}

const loading = ref(false)
const polling = ref(false)
const retryingId = ref(null)
const deletingId = ref(null)
const batchRunning = ref(false)
const batchKind = ref('')
const deleteMode = ref('logical')
const reports = ref([])
const reportTableRef = ref(null)
const selectedReports = ref([])
const kindFilter = ref('')
const titleFilter = ref('')
const page = ref(1)
const pageSize = ref(20)
const sourceDialog = ref({ visible: false, refs: [] })
const detailDialog = ref({ visible: false, loading: false, title: '', data: null, row: null })
let pollTimer = null

function reportKindLabel(k) {
  return REPORT_KIND_LABEL[k] || k || '迭代'
}

function statusLabel(s) {
  return { ready: '就绪', failed: '失败', generating: '生成中', pending: '待处理' }[s] || s
}

function statusTagType(s) {
  if (s === 'ready') return 'success'
  if (s === 'failed') return 'danger'
  return 'info'
}

function formatTime(v) {
  if (!v) return '-'
  return String(v).replace('T', ' ').slice(0, 19)
}

function formatDuration(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

function formatSummary(summary) {
  if (!summary) return ''
  if (typeof summary === 'string') return summary
  try {
    return JSON.stringify(summary, null, 2)
  } catch {
    return String(summary)
  }
}

const filteredReports = computed(() => {
  let list = reports.value
  if (kindFilter.value) {
    list = list.filter(r => r.report_kind === kindFilter.value)
  }
  const q = titleFilter.value.trim().toLowerCase()
  if (q) {
    list = list.filter(r => (r.title || '').toLowerCase().includes(q))
  }
  return list
})

const paginatedReports = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredReports.value.slice(start, start + pageSize.value)
})

watch([kindFilter, titleFilter], () => {
  page.value = 1
  clearSelection()
})

function rowSelectable() {
  return !batchRunning.value
}

function onSelectionChange(rows) {
  selectedReports.value = rows || []
}

function clearSelection() {
  reportTableRef.value?.clearSelection?.()
  selectedReports.value = []
}

function getReportFileExt(reportKind) {
  if (reportKind === PACK_KIND_QUALITY) return '.pptx'
  if (reportKind === PACK_KIND_BUG_WORKBOOK) return '.xlsx'
  return '.docx'
}

function getDeleteConfirmMessage(count = 1) {
  const subject = count > 1 ? `选中的 ${count} 条记录` : '该记录'
  if (deleteMode.value === 'physical') {
    return `将永久删除${subject}及已生成的输出文件，此操作不可恢复，确定继续吗？`
  }
  return `将从列表中隐藏${subject}（逻辑删除），输出文件仍保留在存储中，确定继续吗？`
}

async function loadReports(silent = false) {
  if (!projectId.value) return
  if (!silent) loading.value = true
  try {
    const res = await knowledgeApi.listIterationReports(projectId.value, { size: 100 })
    const payload = res.data || {}
    if (payload.delete_mode) {
      deleteMode.value = payload.delete_mode
    }
    reports.value = payload.items || []
    syncPolling()
  } catch (e) {
    if (!silent) ElMessage.error(e?.message || '加载失败')
    if (!silent) reports.value = []
  } finally {
    if (!silent) loading.value = false
  }
}

function syncPolling() {
  if (hasInFlightReports(reports.value)) {
    startPolling()
  } else {
    stopPolling()
  }
}

function startPolling() {
  if (pollTimer) return
  polling.value = true
  pollTimer = setInterval(async () => {
    if (!projectId.value) return
    const inFlight = reports.value.filter(r => r.status === 'generating' || r.status === 'pending')
    if (!inFlight.length) {
      stopPolling()
      return
    }
    for (const row of inFlight) {
      try {
        const res = await knowledgeApi.getIterationReport(row.id, projectId.value)
        reports.value = mergeReportRow(reports.value, { ...row, ...res.data })
        if (detailDialog.value.visible && detailDialog.value.row?.id === row.id) {
          detailDialog.value.data = res.data
        }
      } catch {
        /* ignore single poll error */
      }
    }
    if (!hasInFlightReports(reports.value)) {
      stopPolling()
    }
  }, 2500)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  polling.value = false
}

function showSources(row) {
  sourceDialog.value = { visible: true, refs: row.source_refs || [] }
}

async function showDetail(row) {
  detailDialog.value = { visible: true, loading: true, title: row.title || '报告详情', data: null, row }
  try {
    const res = await knowledgeApi.getIterationReport(row.id, projectId.value)
    detailDialog.value.data = res.data || null
  } catch (e) {
    ElMessage.error(e?.message || '加载详情失败')
    detailDialog.value.visible = false
  } finally {
    detailDialog.value.loading = false
  }
}

async function retry(row) {
  if (!projectId.value || !row?.id) return
  retryingId.value = row.id
  try {
    await knowledgeApi.retryIterationReport(row.id, projectId.value)
    ElMessage.success('已重新提交生成')
    row.status = 'generating'
    syncPolling()
  } catch (e) {
    ElMessage.error(e?.message || '重试失败')
  } finally {
    retryingId.value = null
  }
}

async function retryFromDetail() {
  if (!detailDialog.value.row) return
  await retry(detailDialog.value.row)
  await showDetail(detailDialog.value.row)
}

async function removeReport(row) {
  if (!projectId.value || !row?.id) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(), '删除生成记录', { type: 'warning' })
  } catch {
    return
  }
  deletingId.value = row.id
  try {
    await knowledgeApi.deleteIterationReport(row.id, projectId.value)
    ElMessage.success('已删除')
    if (detailDialog.value.visible && detailDialog.value.row?.id === row.id) {
      detailDialog.value.visible = false
    }
    reports.value = reports.value.filter(r => r.id !== row.id)
    selectedReports.value = selectedReports.value.filter(r => r.id !== row.id)
  } catch (e) {
    ElMessage.error(e?.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

async function batchDelete() {
  if (!projectId.value) return
  const targets = [...selectedReports.value]
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(targets.length), '批量删除', { type: 'warning' })
  } catch {
    return
  }
  batchRunning.value = true
  batchKind.value = 'delete'
  let ok = 0
  const deletedIds = new Set()
  try {
    for (const row of targets) {
      try {
        await knowledgeApi.deleteIterationReport(row.id, projectId.value)
        ok += 1
        deletedIds.add(row.id)
      } catch {
        /* next */
      }
    }
    reports.value = reports.value.filter(r => !deletedIds.has(r.id))
    if (detailDialog.value.visible && deletedIds.has(detailDialog.value.row?.id)) {
      detailDialog.value.visible = false
    }
    clearSelection()
    ElMessage.success(`已删除 ${ok}/${targets.length} 条记录`)
  } finally {
    batchRunning.value = false
    batchKind.value = ''
  }
}

async function batchRetry() {
  if (!projectId.value) return
  const targets = selectedReports.value.filter(r => r.status === 'failed')
  if (!targets.length) {
    ElMessage.info('请选择状态为「失败」的记录')
    return
  }
  if (targets.length < selectedReports.value.length) {
    ElMessage.warning(`仅 ${targets.length}/${selectedReports.value.length} 条可重试（需状态为失败）`)
  }
  try {
    await ElMessageBox.confirm(`将为 ${targets.length} 条失败记录重新提交生成，是否继续？`, '批量重试')
  } catch {
    return
  }
  batchRunning.value = true
  batchKind.value = 'retry'
  let ok = 0
  try {
    for (const row of targets) {
      try {
        await knowledgeApi.retryIterationReport(row.id, projectId.value)
        row.status = 'generating'
        const item = reports.value.find((r) => r.id === row.id)
        if (item) item.status = 'generating'
        ok += 1
      } catch {
        /* next */
      }
    }
    syncPolling()
    ElMessage.success(`已提交 ${ok}/${targets.length} 条重试`)
  } finally {
    batchRunning.value = false
    batchKind.value = ''
  }
}

async function downloadReportBlob(row) {
  if (!projectId.value || !row?.id) return
  const blob = await knowledgeApi.downloadIterationReport(row.id, projectId.value)
  const ext = getReportFileExt(row.report_kind)
  triggerDownload(blob, `${row.title || '测试报告'}${ext}`)
}

async function batchDownload() {
  if (!projectId.value) return
  const targets = selectedReports.value.filter(r => r.status === 'ready')
  if (!targets.length) {
    ElMessage.info('请选择状态为「就绪」的记录')
    return
  }
  if (targets.length < selectedReports.value.length) {
    ElMessage.warning(`仅 ${targets.length}/${selectedReports.value.length} 条可下载（需状态为就绪）`)
  }
  batchRunning.value = true
  batchKind.value = 'download'
  let ok = 0
  try {
    for (const row of targets) {
      try {
        await downloadReportBlob(row)
        ok += 1
        if (targets.length > 1) {
          await new Promise((resolve) => setTimeout(resolve, 350))
        }
      } catch {
        /* next */
      }
    }
    ElMessage.success(`已下载 ${ok}/${targets.length} 个文件`)
  } finally {
    batchRunning.value = false
    batchKind.value = ''
  }
}

async function removeFromDetail() {
  if (!detailDialog.value.row) return
  await removeReport(detailDialog.value.row)
}

async function download(row) {
  try {
    await downloadReportBlob(row)
  } catch (e) {
    ElMessage.error(e?.message || '下载失败')
  }
}

async function downloadFromDetail() {
  if (!detailDialog.value.row) return
  await download(detailDialog.value.row)
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

watch(projectId, loadReports)
onMounted(loadReports)
onUnmounted(stopPolling)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.title-filter {
  width: 200px;
}
.wizard-link {
  margin-left: auto;
  color: var(--el-color-primary);
  text-decoration: none;
  font-size: 13px;
}
.batch-select-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  font-size: 13px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.source-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
}
.source-list .muted {
  color: var(--el-text-color-secondary);
}
.summary-block {
  margin-top: 12px;
}
.summary-title {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 13px;
}
.summary-pre {
  background: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  margin: 0;
}
</style>
