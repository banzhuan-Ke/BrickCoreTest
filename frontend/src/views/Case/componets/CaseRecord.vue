<template>
  <div class="case-record-panel">
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
      :data="RunRecordList"
      style="width: calc(100% - 40px)"
      :header-cell-style="{'text-align':'center'}"
      :cell-style="{'text-align':'center'}"
      stripe
      @selection-change="handleSelectionChange"
    >
      <template #empty>
        <div class="table-empty">
          <div class="empty-icon">
            <el-icon :size="40" color="#909399"><List /></el-icon>
          </div>
          <div>{{ viewMode === 'recycle' ? '回收站为空' : '暂无数据' }}</div>
        </div>
      </template>
      <el-table-column type="selection" width="48" />
      <el-table-column type="expand">
        <template #default="props">
          <CaseReportTimeline :runInfo="props.row.result_data"/>
        </template>
      </el-table-column>
      <el-table-column label="序号" type="index" :index="tableRowIndex" width="90"></el-table-column>
      <el-table-column prop="case" label="用例名称" min-width='150' show-overflow-tooltip>
        <template #default="scope">
          {{ scope.row.result_data?.name || scope.row.case_name }}
        </template>
      </el-table-column>
      <el-table-column prop="skip" label="是否跳过" min-width='150'>
        <template #default="scope">
          {{ scope.row.result_data?.skip ? '是' : '否' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="运行结果">
        <template #default="scope">
          <el-tag v-if='scope.row.status==="no_run"' type="info">未运行</el-tag>
          <el-tag v-else-if='scope.row.status==="running"' type="primary">运行中</el-tag>
          <el-tag v-else-if='scope.row.status==="success"' type="success">运行成功</el-tag>
          <el-tag v-else-if='scope.row.status==="fail" || scope.row.status==="failed"' type="danger">运行失败</el-tag>
          <el-tag v-else-if='scope.row.status==="skip"' type="warning">跳过运行</el-tag>
          <el-tag v-else-if='scope.row.status==="error"' type="danger">运行错误</el-tag>
          <el-tag v-else type="info">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="浏览器" min-width='90' prop="browser">
        <template #default="scope">
          <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
          <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
          <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="headless" label="运行模式">
        <template #default="scope">
          <el-tag v-if='scope.row.env?.headless === false' type="success">界面模式</el-tag>
          <el-tag v-else-if='scope.row.env?.headless === true' type="primary">无头模式</el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="运行人" min-width='150'/>
      <el-table-column prop="create_time" label="运行时间" min-width='150'>
        <template #default="scope">
          {{ dateTools.rTime(scope.row.start_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="scope">
          <div class="op-btns">
            <template v-if="viewMode === 'active'">
              <el-button
                v-if="scope.row.status === 'running'"
                type="warning"
                size="small"
                title="停止执行"
                @click="clickStop(scope.row.id)"
              >
                <el-icon><VideoPause /></el-icon>
              </el-button>
              <el-button
                v-if="isUiFailed(scope.row.status)"
                type="primary"
                size="small"
                title="在编辑页高亮失败步骤"
                @click="goEditWithFailureHints(scope.row.id)"
              >
                定位失败
              </el-button>
              <el-button
                v-if="isUiFailed(scope.row.status) && canAnalyzeRecord(scope.row)"
                type="warning"
                size="small"
                title="AI 分析"
                @click="openAiAnalyze(scope.row.id)"
              >
                <el-icon><MagicStick /></el-icon>
              </el-button>
              <el-tooltip effect="dark" content="仅删除记录，不会停止正在执行的用例" placement="top">
                <el-button type="danger" size="small" title="删除记录" @click="clickDelete(scope.row.id, false)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </template>
            <template v-else>
              <el-button type="primary" size="small" title="恢复" @click="clickRestore(scope.row.id)">
                恢复
              </el-button>
              <el-button type="danger" size="small" title="永久删除" @click="clickDelete(scope.row.id, true)">
                永久删除
              </el-button>
            </template>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      :hide-on-single-page="true"
      v-model:current-page="pageConfig.page"
      v-model:page-size="pageConfig.size"
      :page-sizes="[10, 20, 30, 40]"
      layout="total, sizes, prev, pager, next, jumper"
      :total="pageConfig.total"
      @current-change="getRunRecordList"
      @size-change="getRunRecordList"
    />

    <FailureAnalyzer
      v-model="aiAnalyzeVisible"
      target-type="ui"
      :target-id="aiAnalyzeTargetId"
    />
  </div>
</template>

<script setup>
import { ref, reactive, watch, computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { List, VideoPause, MagicStick, Delete } from '@element-plus/icons-vue'
import http from '@/api/index'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import { ElMessageBox, ElMessage, ElNotification } from 'element-plus'
import dateTools from '@/tools/dateTools.js'
import { fileApi } from '@/api/modules/sys'
import { useFailureAnalysisGate } from '@/composables/useFailureAnalysisGate.js'
import { makeTableRowIndex } from '@/utils/tableIndex'

const { canAnalyzeExecution } = useFailureAnalysisGate(ref(null), { syncProject: true })
const canAnalyzeRecord = (row) => canAnalyzeExecution(row)
const aiAnalyzeVisible = ref(false)
const aiAnalyzeTargetId = ref(null)

const isUiFailed = (status) => ['fail', 'failed', 'error'].includes(status)

const goEditWithFailureHints = (executionId) => {
  if (!props.case_id) return
  router.push({
    path: `/case/edit/${props.case_id}`,
    query: { execution_id: executionId },
  })
}

const openAiAnalyze = (recordId) => {
  aiAnalyzeTargetId.value = recordId
  aiAnalyzeVisible.value = true
}

const props = defineProps({
  case_id: {
    type: Number,
    default: 0
  }
})

const router = useRouter()

const RunRecordList = ref([])
const selectedRecords = ref([])
const deleteMode = ref('logical')
const viewMode = ref('active')

const showRecycleBin = computed(() => deleteMode.value === 'recycle_bin')

const pageConfig = reactive({
  case_id: 0,
  page: 1,
  size: 10,
  total: 0,
  recycle_bin: false,
})

let pollTimer = null

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startPollingIfNeeded = () => {
  stopPolling()
  const hasRunning = RunRecordList.value.some((row) => row.status === 'running')
  if (hasRunning && viewMode.value === 'active') {
    pollTimer = setInterval(() => {
      getRunRecordList()
    }, 3000)
  }
}

onBeforeUnmount(() => {
  stopPolling()
})

const tableRowIndex = makeTableRowIndex(pageConfig)

const handleSelectionChange = (rows) => {
  selectedRecords.value = rows
}

const onViewModeChange = () => {
  pageConfig.page = 1
  pageConfig.recycle_bin = viewMode.value === 'recycle'
  selectedRecords.value = []
  getRunRecordList()
}

const getDeleteConfirmMessage = (permanent) => {
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

const getRunRecordList = async () => {
  pageConfig.case_id = props.case_id
  pageConfig.recycle_bin = viewMode.value === 'recycle'
  const res = await http.resultApi.getCaseRecord(pageConfig)

  const payload = res.data || {}
  if (payload.delete_mode) {
    deleteMode.value = payload.delete_mode
    if (deleteMode.value !== 'recycle_bin' && viewMode.value === 'recycle') {
      viewMode.value = 'active'
      pageConfig.recycle_bin = false
    }
  }

  const records = payload.data || []
  for (const record of records) {
    if (record.result_data) {
      record.result_data = await fileApi.processReportUrls(record.result_data)
    }
  }

  RunRecordList.value = records
  pageConfig.total = payload.total || 0
  selectedRecords.value = []
  startPollingIfNeeded()
}

getRunRecordList()

watch(() => props.case_id, () => {
  pageConfig.case_id = props.case_id
  pageConfig.page = 1
  getRunRecordList()
})

const clickStop = async (record_id) => {
  try {
    await ElMessageBox.confirm(
      '确定停止当前用例执行吗？执行器将收到中断信号。删除记录不会停止执行，请使用停止。',
      '停止执行',
      { type: 'warning' }
    )
    await http.runnerApi.stopCase(record_id)
    ElMessage.success('停止信号已发送')
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '停止失败')
  }
}

const clickDelete = async (record_id, permanent) => {
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(permanent), '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      center: true,
      type: 'warning',
    })
    const res = await http.resultApi.deleteCaseRecord(record_id, permanent ? { permanent: true } : {})
    if (res.status === 204) {
      await getRunRecordList()
      ElNotification({
        type: 'success',
        title: permanent ? '已永久删除' : '删除成功',
        duration: 1500,
      })
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElNotification({
        type: 'error',
        title: '删除失败',
        message: e.response?.data?.detail || e.message,
        duration: 2000,
      })
    }
  }
}

const handleBatchDelete = async (permanent) => {
  const ids = selectedRecords.value.map((row) => row.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(permanent), '批量删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const res = await http.resultApi.batchDeleteCaseRecords(ids, permanent)
    const count = res.data?.deleted ?? ids.length
    ElMessage.success(permanent ? `已永久删除 ${count} 条记录` : `已删除 ${count} 条记录`)
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '批量删除失败')
    }
  }
}

const clickRestore = async (record_id) => {
  try {
    await ElMessageBox.confirm('确定恢复该运行记录吗？', '恢复记录', { type: 'info' })
    await http.resultApi.restoreCaseRecord(record_id)
    ElMessage.success('已恢复')
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '恢复失败')
  }
}

const handleBatchRestore = async () => {
  const ids = selectedRecords.value.map((row) => row.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定恢复选中的 ${ids.length} 条记录吗？`, '批量恢复', { type: 'info' })
    await http.resultApi.batchRestoreCaseRecords(ids)
    ElMessage.success('已恢复')
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '批量恢复失败')
  }
}
</script>

<style scoped>
.case-record-panel {
  width: 100%;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 12px;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.op-btns {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
</style>
