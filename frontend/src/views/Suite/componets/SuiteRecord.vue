<template>
  <div class="suite-record-panel">
    <div class="toolbar" v-if="selectedRecords.length > 0">
      <el-button type="danger" size="small" @click="handleBatchDelete">
        批量删除({{ selectedRecords.length }})
      </el-button>
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
        <div>暂无数据</div>
      </div>
    </template>
    <el-table-column type="selection" width="48" />
    <el-table-column label="序号" type="index" :index="tableRowIndex" width="90"/>
    <el-table-column prop="suite_name" label="套件名称" min-width='100' show-overflow-tooltip/>
    <el-table-column prop="status" label="执行状态" min-width='100'>
      <template #default="scope">
        <el-tag v-if="scope.row.status === '执行完成'" type="success">执行完成</el-tag>
        <el-tag v-else-if="scope.row.status === '等待执行'" type="info">等待执行</el-tag>
        <el-tag v-else-if="scope.row.status === '执行中'" type="primary">执行中</el-tag>
        <el-tag v-else-if="scope.row.status === '已停止'" type="warning">已停止</el-tag>
        <el-tag v-else type="info">{{ scope.row.status }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="进度" min-width="140">
      <template #default="scope">
        <div class="progress-cell">
          <el-progress
            :percentage="uiExecutionProgress(scope.row).percent"
            :stroke-width="10"
            :status="progressStatus(scope.row)"
          />
          <span class="progress-text">
            {{ uiExecutionProgress(scope.row).done }}/{{ uiExecutionProgress(scope.row).total || '—' }}
          </span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="浏览器" prop="browser">
      <template #default="scope">
        <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
        <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
        <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
        <span v-else class="text-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="headless" label="执行模式" min-width='100'>
      <template #default="scope">
        <el-tag v-if='scope.row.env?.headless === false' type="success">界面模式</el-tag>
        <el-tag v-else-if='scope.row.env?.headless === true' type="primary">无头模式</el-tag>
        <span v-else class="text-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="duration" label="执行耗时">
      <template #default="scope">
        {{ (scope.row.duration ?? 0).toFixed(2) }}秒
      </template>
    </el-table-column>
    <el-table-column label="通过率" min-width='100'>
      <template #default="scope">
        {{ (scope.row.pass_rate || 0).toFixed(2) + '%' }}
      </template>
    </el-table-column>
    <el-table-column prop="case_count" label="用例总数"/>
    <el-table-column prop="success" label="成功数"/>
    <el-table-column prop="fail" label="失败数"/>
    <el-table-column prop="error" label="错误数"/>
    <el-table-column prop="skip" label="跳过数"/>
    <el-table-column prop="no_run" label="未运行数"/>
    <el-table-column prop="username" label="执行人"/>
    <el-table-column prop="create_time" label="执行时间" min-width='200'>
      <template #default="scope">
        {{ dateTools.rTime(scope.row.start_time) }}
      </template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="scope">
        <div class="op-btns">
          <el-button
            v-if="isSuiteStoppable(scope.row.status)"
            type="warning"
            size="small"
            title="停止执行"
            @click="clickStop(scope.row.id)"
          >
            <el-icon><VideoPause /></el-icon>
          </el-button>
          <el-button
            type="success"
            size="small"
            title="查看报告"
            @click="router.push({name: 'suiteReport', params: {id: scope.row.id}})"
          >
            <el-icon><View /></el-icon>
          </el-button>
          <el-tooltip effect="dark" content="仅删除记录，不会停止正在执行的用例" placement="top">
            <el-button type="danger" size="small" title="删除记录" @click="clickDelete(scope.row.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </template>
    </el-table-column>
  </el-table>
  <!-- 分页器-->
  <el-pagination
      :hide-on-single-page="true"
      v-model:current-page="pageConfig.page"
      v-model:page-size="pageConfig.size"
      :page-sizes="[10, 20, 30, 40]"
      layout="total, sizes, prev, pager, next, jumper"
      :total="pageConfig.total"
      @current-change="getRunRecordList"
      @size-change="getRunRecordList"/>
  </div>
</template>

<script setup>
import {ref, reactive, watch} from 'vue'
import {List} from "@element-plus/icons-vue"
import http from '@/api/index'
import {useRouter} from 'vue-router'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import dateTools from "@/tools/dateTools.js"
import { makeTableRowIndex } from '@/utils/tableIndex'
import {
  isUiExecutionActive,
  uiExecutionProgress,
  useUiExecutionProgressPoll,
} from '@/composables/useUiExecutionProgressPoll.js'

const props = defineProps({
  suite_id: {
    type: Number,
    default: 0
  }
})

const router = useRouter()
const RunRecordList = ref([])
const selectedRecords = ref([])
const deleteMode = ref('logical')

const pageConfig = reactive({
  suite_id: 0,
  page: 1,
  size: 10,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pageConfig)

const handleSelectionChange = (rows) => {
  selectedRecords.value = rows
}

const getDeleteConfirmMessage = () => {
  if (deleteMode.value === 'physical') {
    return '将立即从数据库永久删除（含下属用例记录），此操作不可恢复，确定继续吗？'
  }
  return '记录将从列表中隐藏（逻辑删除，含下属用例记录），确定继续吗？'
}

const progressStatus = (row) => {
  if (row.status === '已停止') return 'warning'
  if (row.status === '执行完成') {
    return (row.fail || 0) + (row.error || 0) > 0 ? 'exception' : 'success'
  }
  return undefined
}

const getRunRecordList = async () => {
  pageConfig.suite_id = props.suite_id
  const res = await http.resultApi.getSuiteRecord(pageConfig)
  const payload = res.data || {}
  if (payload.delete_mode) {
    deleteMode.value = payload.delete_mode
  }
  RunRecordList.value = payload.data || []
  pageConfig.total = payload.total || 0
  selectedRecords.value = []
  syncPoll()
}

const { syncPoll } = useUiExecutionProgressPoll(
  getRunRecordList,
  () => (RunRecordList.value || []).some((r) => isUiExecutionActive(r.status)),
  { intervalMs: 3000 }
)

getRunRecordList()

watch(() => props.suite_id, (newVal) => {
  pageConfig.suite_id = newVal
  getRunRecordList()
})

const isSuiteStoppable = (status) => isUiExecutionActive(status)

const clickStop = async (record_id) => {
  try {
    await ElMessageBox.confirm(
      '确定停止当前套件执行吗？已跑完的用例结果会保留；执行器将收到中断信号。删除记录不会停止执行，请使用停止。',
      '停止执行',
      { type: 'warning' }
    )
    await http.runnerApi.stopSuite(record_id)
    ElMessage.success('停止信号已发送')
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '停止失败')
  }
}

const clickDelete = async (record_id) => {
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(), '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      center: true,
      type: 'warning'
    })
    const res = await http.resultApi.deleteSuiteRecord(record_id)
    if (res.status === 204) {
      await getRunRecordList()
      ElNotification({
        type: 'success',
        title: '已成功删除套件运行记录！',
        duration: 1500,
      })
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElNotification({
        type: 'error',
        title: '套件运行记录删除失败！',
        message: e.response?.data?.detail || e.message,
        duration: 2000,
      })
    }
  }
}

const handleBatchDelete = async () => {
  const ids = selectedRecords.value.map((row) => row.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(), '批量删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const res = await http.resultApi.batchDeleteSuiteRecords(ids)
    const count = res.data?.deleted ?? ids.length
    ElMessage.success(`已删除 ${count} 条记录`)
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || e.message || '批量删除失败')
    }
  }
}
</script>

<style scoped>
.suite-record-panel {
  width: 100%;
}
.toolbar {
  margin-bottom: 10px;
}
.op-btns {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.progress-cell {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  padding: 0 4px;
}
.progress-text {
  font-size: 12px;
  color: #909399;
  line-height: 1.2;
}
</style>
