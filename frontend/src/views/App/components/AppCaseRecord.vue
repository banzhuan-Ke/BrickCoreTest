<template>
  <div class="app-run-record">
    <div class="toolbar">
      <el-radio-group v-if="showRecycleBin" v-model="viewMode" size="small" @change="onViewModeChange">
        <el-radio-button value="active">运行记录</el-radio-button>
        <el-radio-button value="recycle">回收站</el-radio-button>
      </el-radio-group>
      <div class="toolbar-actions">
        <template v-if="viewMode === 'active'">
          <el-button
            v-if="selectedRecords.length > 0"
            type="danger"
            size="small"
            @click="handleBatchDelete(false)"
          >
            批量删除({{ selectedRecords.length }})
          </el-button>
        </template>
        <template v-else>
          <el-button
            v-if="selectedRecords.length > 0"
            type="primary"
            size="small"
            @click="handleBatchRestore"
          >
            批量恢复({{ selectedRecords.length }})
          </el-button>
          <el-button
            v-if="selectedRecords.length > 0"
            type="danger"
            size="small"
            @click="handleBatchDelete(true)"
          >
            永久删除({{ selectedRecords.length }})
          </el-button>
        </template>
      </div>
    </div>

    <el-table
      :data="records"
      stripe
      :header-cell-style="{ 'text-align': 'center' }"
      :cell-style="{ 'text-align': 'center' }"
      v-loading="loading"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column type="expand">
        <template #default="{ row }">
          <CaseReportTimeline v-if="row.result_data" :runInfo="row.result_data" profile="app" />
          <el-empty v-else description="暂无步骤详情" />
        </template>
      </el-table-column>
      <el-table-column type="index" label="序号" width="70" />
      <el-table-column prop="status" label="结果" width="110">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status).type">{{ statusTag(row.status).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="执行人" width="100" />
      <el-table-column prop="start_time" label="执行时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <template v-if="viewMode === 'active'">
            <el-button v-if="isRunning(row.status)" type="warning" size="small" @click="stopRun(row.id)">停止</el-button>
            <el-button type="success" size="small" @click="exportReport(row.id)">导出</el-button>
            <el-button type="danger" size="small" plain @click="deleteRecord(row.id, false)">删除</el-button>
          </template>
          <template v-else>
            <el-button type="primary" size="small" plain @click="restoreRecord(row.id)">恢复</el-button>
            <el-button type="danger" size="small" plain @click="deleteRecord(row.id, true)">永久删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="page.total > page.size"
      v-model:current-page="page.page"
      v-model:page-size="page.size"
      :total="page.total"
      layout="total, prev, pager, next"
      class="pager"
      @current-change="loadList"
    />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import { appExecApi, appRecordApi } from '@/api'
import dateTools from '@/tools/dateTools.js'

const props = defineProps({
  caseId: { type: Number, required: true },
  projectId: { type: Number, required: true },
})

const records = ref([])
const loading = ref(false)
const selectedRecords = ref([])
const deleteMode = ref('logical')
const viewMode = ref('active')
const page = reactive({ page: 1, size: 10, total: 0 })

const showRecycleBin = computed(() => deleteMode.value === 'recycle_bin')

function formatTime(v) {
  return v ? dateTools.rTime(v) : '-'
}

function statusTag(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'success') return { text: '成功', type: 'success' }
  if (s === 'fail' || s === 'failed') return { text: '失败', type: 'danger' }
  if (s === 'error') return { text: '错误', type: 'warning' }
  if (s === 'running') return { text: '运行中', type: 'primary' }
  if (s === 'skip') return { text: '跳过', type: 'info' }
  return { text: status || '-', type: 'info' }
}

function isRunning(status) {
  return String(status || '').toLowerCase() === 'running'
}

function getDeleteConfirmMessage(permanent) {
  if (permanent) {
    return '永久删除后无法恢复，确定继续吗？'
  }
  if (deleteMode.value === 'physical') {
    return '将立即从数据库永久删除，此操作不可恢复，确定继续吗？'
  }
  if (deleteMode.value === 'recycle_bin') {
    return '记录将移入回收站，可在回收站中恢复或永久删除，确定继续吗？'
  }
  return '记录将从列表中隐藏（逻辑删除），确定继续吗？'
}

function handleSelectionChange(rows) {
  selectedRecords.value = rows
}

function onViewModeChange() {
  page.page = 1
  selectedRecords.value = []
  loadList()
}

async function loadList() {
  if (!props.caseId || !props.projectId) return
  loading.value = true
  try {
    const res = await appRecordApi.listCases({
      project_id: props.projectId,
      case_id: props.caseId,
      page: page.page,
      size: page.size,
      recycle_bin: viewMode.value === 'recycle',
    })
    const payload = res.data || {}
    if (payload.delete_mode) {
      deleteMode.value = payload.delete_mode
      if (deleteMode.value !== 'recycle_bin' && viewMode.value === 'recycle') {
        viewMode.value = 'active'
      }
    }
    records.value = payload.data || []
    page.total = payload.total || 0
    selectedRecords.value = []
  } finally {
    loading.value = false
  }
}

async function stopRun(recordId) {
  try {
    await ElMessageBox.confirm('确定停止当前用例执行吗？', '停止执行', { type: 'warning' })
    await appExecApi.stopCase(recordId)
    ElMessage.success('停止信号已发送')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '停止失败')
  }
}

async function exportReport(recordId) {
  try {
    const res = await appRecordApi.exportReport(recordId, { record_type: 'case' })
    const blob = new Blob([res.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `app-case-report-${recordId}.html`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  }
}

async function deleteRecord(recordId, permanent) {
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(permanent), '删除记录', { type: 'warning' })
    await appRecordApi.deleteCase(recordId, permanent ? { permanent: true } : {})
    ElMessage.success(permanent ? '已永久删除' : '已删除')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function restoreRecord(recordId) {
  try {
    await appRecordApi.restoreCase(recordId)
    ElMessage.success('已恢复')
    await loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '恢复失败')
  }
}

async function handleBatchDelete(permanent) {
  const ids = selectedRecords.value.map((row) => row.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(permanent), '批量删除', { type: 'warning' })
    const res = await appRecordApi.batchDeleteCases(ids, permanent)
    const count = res.data?.deleted ?? ids.length
    ElMessage.success(`已删除 ${count} 条记录`)
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '批量删除失败')
  }
}

async function handleBatchRestore() {
  const ids = selectedRecords.value.map((row) => row.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定恢复选中的 ${ids.length} 条记录吗？`, '批量恢复', { type: 'info' })
    const res = await appRecordApi.batchRestoreCases(ids)
    const count = res.data?.restored ?? ids.length
    ElMessage.success(`已恢复 ${count} 条记录`)
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '批量恢复失败')
  }
}

watch(() => [props.caseId, props.projectId], loadList, { immediate: true })
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
