<template>
  <div class="task-record-panel">
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
    <el-table-column prop="task_name" label="计划名称" min-width='100' show-overflow-tooltip/>
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
    <el-table-column prop="status" label="执行状态" min-width='100'>
      <template #default="scope">
        <el-tag v-if="scope.row.status === '执行完成'" type="success">执行完成</el-tag>
        <el-tag v-if="scope.row.status === '执行中'" type="primary">执行中</el-tag>
        <el-tag v-if="scope.row.status === '等待执行'" type="info">等待执行</el-tag>
        <el-tag v-if="scope.row.status === '已停止'" type="warning">已停止</el-tag>
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
    <el-table-column label="触发方式" width="90" align="center">
      <template #default="scope">
        <el-tag
          :type="scope.row.env?.trigger_source === 'assistant' ? 'success' : 'info'"
          size="small"
        >
          {{ scope.row.env?.trigger_source === 'assistant' ? '小测' : '手动' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="case_count" label="用例总数"/>
    <el-table-column prop="success" label="成功数"/>
    <el-table-column prop="fail" label="失败数"/>
    <el-table-column prop="error" label="错误数"/>
    <el-table-column prop="skip" label="跳过数"/>
    <el-table-column prop="no_run" label="未运行数"/>
    <el-table-column label="通过率" min-width='100'>
      <template #default="scope">
        {{ (scope.row.pass_rate || 0).toFixed(2) + '%' }}
      </template>
    </el-table-column>
    <el-table-column prop="username" label="执行人"/>
    <el-table-column prop="create_time" label="执行时间" min-width='200'>
      <template #default="scope">
        {{ dateTools.rTime(scope.row.start_time) }}
      </template>
    </el-table-column>
    <el-table-column prop="duration" label="执行耗时">
      <template #default="scope">
        <!-- 保留两位小数-->
        {{ (scope.row.duration ?? 0).toFixed(2) }}秒
      </template>
    </el-table-column>
    <el-table-column label="操作" width="200" fixed="right">
      <template #default="scope">
        <div class="op-btns">
          <el-button
            v-if="isPlanStoppable(scope.row.status)"
            type="warning"
            size="small"
            title="停止执行"
            @click="clickStop(scope.row.id)"
          >
            <el-icon><VideoPause /></el-icon>
          </el-button>
          <el-button
            v-if="scope.row.status === '执行完成' || scope.row.status === '已停止'"
            type="warning"
            size="small"
            title="再次运行（打开运行配置）"
            @click="clickRerun(scope.row)"
          >
            <el-icon><RefreshRight /></el-icon>
          </el-button>
          <el-button type="success" size="small" title="查看报告" @click="showReport(scope.row.id)">
            <el-icon><View /></el-icon>
          </el-button>
          <el-button
            v-if="canSendReport(scope.row)"
            type="warning"
            size="small"
            title="推送报告邮件"
            :loading="sendingReportId === scope.row.id"
            @click="sendReport(scope.row)"
          >
            <el-icon><Message /></el-icon>
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

  <!--  分页器-->
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

  <SendReportDialog
    v-model="sendDialogVisible"
    :project-id="pageConfig.project_id"
    :send-fn="doSendReport"
  />
  </div>
</template>

<script setup>
import {ref, reactive, watch} from 'vue'
import {List, RefreshRight} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import {useRouter} from 'vue-router'
import { makeTableRowIndex } from '@/utils/tableIndex'
import SendReportDialog from '@/components/SendReportDialog.vue'
import {
  isUiExecutionActive,
  uiExecutionProgress,
  useUiExecutionProgressPoll,
} from '@/composables/useUiExecutionProgressPoll.js'

const router = useRouter()
const emit = defineEmits(['rerun'])
// 定义props
const props = defineProps({
  task_id: {
    type: Number,
    default: 0
  }
})

const proStore = ProjectStore()
// 获取运行记录列表数据
const RunRecordList = ref([])
const selectedRecords = ref([])
const deleteMode = ref('logical')

const pageConfig = reactive({
  task_id: 0,
  page: 1,
  size: 10,
  total: 0,
  project_id: proStore.projectInfo.id
})

const tableRowIndex = makeTableRowIndex(pageConfig)

const handleSelectionChange = (rows) => {
  selectedRecords.value = rows
}

const getDeleteConfirmMessage = () => {
  if (deleteMode.value === 'physical') {
    return '将立即从数据库永久删除（含下属套件与用例记录），此操作不可恢复，确定继续吗？'
  }
  return '记录将从列表中隐藏（逻辑删除，含下属套件与用例记录），确定继续吗？'
}

const progressStatus = (row) => {
  if (row.status === '已停止') return 'warning'
  if (row.status === '执行完成') {
    return (row.fail || 0) + (row.error || 0) > 0 ? 'exception' : 'success'
  }
  return undefined
}

// 获取运行记录数据
const getRunRecordList = async () => {
  pageConfig.task_id = props.task_id
  const res = await http.resultApi.getTaskRecord(pageConfig)
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

// 侦听器 监听计划id
watch(() => props.task_id, (newVal) => {
  pageConfig.task_id = newVal
  getRunRecordList()
})

// 再次运行：交由父级打开「计划运行配置」（不静默一键重跑，避免缺 device_id / 设备已离线）
const clickRerun = (row) => {
  const env = row.env || {}
  const envId = env.environment_id || env.env_id
  if (!envId) {
    ElMessage.warning('该记录缺少环境信息，请关闭本窗口后在计划列表点击「运行」')
    return
  }
  emit('rerun', {
    task_id: row.task_id || props.task_id,
    env_id: envId,
    browser_type: env.browser || env.browser_type || 'chromium',
    headless: env.headless ?? false,
    device_id: row.device_id || null,
    device_assignments: Array.isArray(env.device_assignments) ? env.device_assignments : [],
    concurrency: env.device_assignments?.[0]?.concurrency || 3,
    ai_heal_enabled: typeof env.ai_heal_enabled === 'boolean' ? env.ai_heal_enabled : undefined,
    ai_act_enabled: typeof env.ai_act_enabled === 'boolean' ? env.ai_act_enabled : undefined,
    failure_analysis_on_report:
      typeof env.failure_analysis_on_report === 'boolean' ? env.failure_analysis_on_report : undefined,
  })
}

const showReport = (id) => {
  router.push({
    name: 'taskReport',
    params: {id},
    query: {mode: 'chart'}
  })
}

const isPlanStoppable = (status) => isUiExecutionActive(status)

const sendingReportId = ref(null)
const sendDialogVisible = ref(false)
const sendTargetId = ref(null)
const canSendReport = (row) => !isUiExecutionActive(row.status)

const doSendReport = async (configIds) => {
  sendingReportId.value = sendTargetId.value
  try {
    return await http.resultApi.sendTaskReport(sendTargetId.value, { config_ids: configIds })
  } finally {
    sendingReportId.value = null
  }
}

const sendReport = (row) => {
  if (!canSendReport(row)) return
  sendTargetId.value = row.id
  sendDialogVisible.value = true
}

// 停止计划执行
const clickStop = async (record_id) => {
  try {
    await ElMessageBox.confirm(
      '确定停止当前 UI 计划执行吗？已跑完的用例结果会保留；执行器将收到中断信号。删除记录不会停止执行，请使用停止。',
      '停止执行',
      { type: 'warning' }
    )
    await http.runnerApi.stopPlan(record_id)
    ElMessage.success('停止信号已发送')
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '停止失败')
  }
}

// 删除任务运行记录
const clickDelete = async (record_id) => {
  try {
    await ElMessageBox.confirm(getDeleteConfirmMessage(), '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      center: true,
      type: 'warning'
    })
    const res = await http.resultApi.deleteTaskRecord(record_id)
    if (res.status === 204) {
      await getRunRecordList()
      ElNotification({
        type: 'success',
        title: '已成功删除任务运行记录！',
        duration: 1500,
      })
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElNotification({
        type: 'error',
        title: '任务运行记录删除失败！',
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
    const res = await http.resultApi.batchDeleteTaskRecords(ids)
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
.task-record-panel {
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