<template>
  <PageCard>
    <template #title>
      <div class="record-title">
        <span>App 执行记录</span>
        <el-radio-group v-model="viewMode" size="small" @change="onViewModeChange">
          <el-radio-button label="active">有效记录</el-radio-button>
          <el-radio-button label="recycle">回收站</el-radio-button>
        </el-radio-group>
      </div>
    </template>
    <template #main>
      <el-radio-group v-model="recordType" style="margin-bottom: 12px" @change="onTypeChange">
        <el-radio-button label="plan">计划记录</el-radio-button>
        <el-radio-button label="suite">套件记录</el-radio-button>
        <el-radio-button label="case">用例记录</el-radio-button>
      </el-radio-group>
      <el-table :data="records" stripe :header-cell-style="{ 'text-align': 'center' }" :cell-style="{ 'text-align': 'center' }">
        <el-table-column type="index" label="序号" width="70" />
        <el-table-column :prop="nameKey" :label="nameLabel" min-width="140" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status).type">{{ statusTag(row.status).text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="recordType !== 'case'" prop="pass_rate" label="通过率" width="100">
          <template #default="{ row }">{{ (row.pass_rate || 0).toFixed(2) }}%</template>
        </el-table-column>
        <el-table-column prop="username" label="执行人" width="100" />
        <el-table-column prop="start_time" label="执行时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="460">
          <template #default="{ row }">
            <el-button
              v-if="viewMode === 'active'"
              type="primary"
              plain
              size="small"
              icon="View"
              @click="showDetail(row)"
            >详情</el-button>
            <el-button
              v-if="viewMode === 'active' && recordType === 'case' && isUiFailed(row.status) && canAiAnalyze"
              type="warning"
              plain
              size="small"
              @click="openAiAnalyze(row.id)"
            >AI 分析</el-button>
            <el-button
              v-if="viewMode === 'active' && (recordType === 'plan' || recordType === 'suite')"
              type="primary"
              plain
              size="small"
              @click="openFullReport(row.id)"
            >完整报告</el-button>
            <el-button
              v-if="viewMode === 'active' && recordType === 'case' && isUiFailed(row.status)"
              type="primary"
              plain
              size="small"
              title="在编辑页高亮失败步骤"
              @click="goEditWithFailureHints(row)"
            >定位失败</el-button>
            <el-button
              v-if="viewMode === 'active' && recordType !== 'case'"
              type="success"
              plain
              size="small"
              icon="Download"
              @click="exportReport(row.id)"
            >导出</el-button>
            <el-button
              v-if="viewMode === 'active' && recordType === 'case'"
              type="success"
              plain
              size="small"
              icon="Download"
              @click="exportCaseReport(row.id)"
            >导出</el-button>
            <el-button
              v-if="viewMode === 'active'"
              type="danger"
              plain
              size="small"
              @click="deleteRecord(row.id)"
            >删除</el-button>
            <el-button
              v-if="viewMode === 'recycle'"
              type="primary"
              plain
              size="small"
              @click="restoreRecord(row.id)"
            >恢复</el-button>
            <el-button
              v-if="viewMode === 'active' && canStop(row.status)"
              type="danger"
              plain
              size="small"
              icon="VideoPause"
              @click="stopRecord(row.id)"
            >停止</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <template #bottom>
      <el-pagination
        v-model:current-page="page.page"
        v-model:page-size="page.size"
        :total="page.total"
        layout="total, sizes, prev, pager, next"
        @current-change="loadList"
        @size-change="loadList"
      />
    </template>
  </PageCard>

  <el-dialog v-model="detailDlg" :title="detailTitleText" width="920px" destroy-on-close>
    <div v-if="detail" v-loading="detailLoading" class="detail-body">
      <AppReportOverview
        v-if="recordType === 'case'"
        :title="detail.case_name"
        :status="detail.status"
        :duration="detail.duration"
        :username="detail.username"
        :start-time="detail.start_time"
        :show-stats="false"
      />
      <AppReportOverview
        v-else
        :title="detailTitleText.replace('执行详情 · ', '')"
        :status="detail.status"
        :pass-rate="detail.pass_rate"
        :success="detail.success"
        :fail="detail.fail"
        :error="detail.error"
        :skip="detail.skip"
        :case-count="detail.case_count"
        :duration="detail.duration"
        :username="detail.username"
        :start-time="detail.start_time"
        :show-meta="false"
      />
      <AppReportEnvSummary
        :env="detail.env"
        :device-id="detail.device_id"
        :username="detail.username"
        :start-time="detail.start_time"
        :driver-mode="detail.env?.driver_mode"
      />

      <template v-if="recordType === 'case' && detail.result_data">
        <CaseReportTimeline :runInfo="detail.result_data" profile="app" />
      </template>

      <template v-else-if="detail.suites?.length">
        <h4 class="section-title">套件列表</h4>
        <el-table :data="detail.suites" size="small" stripe>
          <el-table-column prop="suite_name" label="套件" min-width="140" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="pass_rate" label="通过率" width="90">
            <template #default="{ row }">{{ (row.pass_rate || 0).toFixed(1) }}%</template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button type="primary" link @click="openSuiteReport(row.id)">套件报告</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="detail.cases?.length">
        <h4 class="section-title">用例列表</h4>
        <el-table :data="detail.cases" size="small" stripe>
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="app-report-expand">
                <CaseReportTimeline v-if="row.result_data" :runInfo="row.result_data" profile="app" />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="case_name" label="用例" min-width="140" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status).type">{{ statusTag(row.status).text }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button
                v-if="isUiFailed(row.status) && canAiAnalyze"
                type="warning"
                link
                @click="openAiAnalyze(row.id)"
              >AI 分析</el-button>
              <el-button
                v-if="isUiFailed(row.status) && row.case_id"
                type="primary"
                link
                @click="goEditWithFailureHints(row)"
              >定位失败</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>
    <template #footer>
      <el-button
        v-if="detail && recordType === 'case' && isUiFailed(detail.status) && canAiAnalyze"
        type="warning"
        @click="openAiAnalyze(detail.id)"
      >AI 分析</el-button>
      <el-button v-if="detail && (recordType === 'plan' || recordType === 'suite')" type="primary" @click="openFullReport(detail.id)">打开完整报告页</el-button>
      <el-button @click="detailDlg = false">关闭</el-button>
    </template>
  </el-dialog>

  <FailureAnalyzer
    v-model="aiAnalyzeVisible"
    target-type="app"
    :target-id="aiAnalyzeTargetId"
  />
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import AppReportOverview from '@/views/App/components/AppReportOverview.vue'
import AppReportEnvSummary from '@/views/App/components/AppReportEnvSummary.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import { appRecordApi, appExecApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import dateTools from '@/tools/dateTools.js'

const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()
const records = ref([])
const recordType = ref('plan')
const viewMode = ref('active')
const page = reactive({ page: 1, size: 10, total: 0 })
const detailDlg = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const aiAnalyzeVisible = ref(false)
const aiAnalyzeTargetId = ref(null)

const canAiAnalyze = computed(() => uStore.hasPermission('ai_test:execute'))

function openAiAnalyze(recordId) {
  aiAnalyzeTargetId.value = recordId
  aiAnalyzeVisible.value = true
}

const nameKey = computed(() => (recordType.value === 'plan' ? 'plan_name' : recordType.value === 'suite' ? 'suite_name' : 'case_name'))
const nameLabel = computed(() => (recordType.value === 'plan' ? '计划名称' : recordType.value === 'suite' ? '套件名称' : '用例名称'))
const detailTitleText = computed(() => {
  const name = detail.value?.plan_name || detail.value?.suite_name || detail.value?.case_name || ''
  return name ? `执行详情 · ${name}` : '执行详情'
})

function formatTime(v) {
  return v ? dateTools.rTime(v) : '-'
}

function statusTag(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'success' || status === '执行完成') return { text: status === 'success' ? '成功' : status, type: 'success' }
  if (s === 'fail' || s === 'failed') return { text: '失败', type: 'danger' }
  if (s === 'error') return { text: '错误', type: 'warning' }
  if (s === 'running' || status === '执行中') return { text: status === 'running' ? '运行中' : status, type: 'primary' }
  if (status === '等待执行') return { text: '等待执行', type: 'info' }
  if (status === '已停止') return { text: '已停止', type: 'warning' }
  return { text: status || '-', type: 'info' }
}

function canStop(status) {
  return status === '执行中' || status === '等待执行'
}

const isUiFailed = (status) => ['fail', 'failed', 'error'].includes(String(status || '').toLowerCase())

function goEditWithFailureHints(row) {
  if (!row?.case_id) return
  router.push({
    name: 'appCaseEdit',
    params: { id: row.case_id },
    query: { execution_id: row.id },
  })
}

function onTypeChange() {
  page.page = 1
  loadList()
}

function onViewModeChange() {
  page.page = 1
  loadList()
}

async function loadList() {
  const params = {
    project_id: proStore.projectInfo.id,
    page: page.page,
    size: page.size,
    recycle_bin: viewMode.value === 'recycle',
  }
  let res
  if (recordType.value === 'plan') res = await appRecordApi.listPlans(params)
  else if (recordType.value === 'suite') res = await appRecordApi.listSuites(params)
  else res = await appRecordApi.listCases(params)
  records.value = res.data?.data || []
  page.total = res.data?.total || 0
}

async function showDetail(row) {
  detailDlg.value = true
  detailLoading.value = true
  detail.value = null
  try {
    if (recordType.value === 'plan') {
      const res = await appRecordApi.planDetail(row.id)
      detail.value = res.data
    } else if (recordType.value === 'suite') {
      const res = await appRecordApi.suiteDetail(row.id)
      detail.value = res.data
    } else {
      const res = await appRecordApi.caseDetail(row.id)
      detail.value = res.data
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载详情失败')
    detailDlg.value = false
  } finally {
    detailLoading.value = false
  }
}

function openFullReport(recordId) {
  if (recordType.value === 'plan') {
    router.push({ name: 'appPlanReport', params: { id: recordId } })
  } else if (recordType.value === 'suite') {
    router.push({ name: 'appSuiteReport', params: { id: recordId } })
  }
  detailDlg.value = false
}

function openSuiteReport(suiteExecutionId) {
  router.push({ name: 'appSuiteReport', params: { id: suiteExecutionId } })
  detailDlg.value = false
}

async function exportReport(recordId) {
  const record_type = recordType.value === 'plan' ? 'task' : 'suite'
  try {
    const res = await appRecordApi.exportReport(recordId, { record_type })
    const blob = new Blob([res.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `app-report-${recordId}.html`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  }
}

async function exportCaseReport(recordId) {
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

async function deleteRecord(recordId) {
  try {
    await ElMessageBox.confirm('删除后该记录将从列表中隐藏，确定继续吗？', '删除记录', { type: 'warning' })
    if (recordType.value === 'plan') await appRecordApi.deletePlan(recordId)
    else if (recordType.value === 'suite') await appRecordApi.deleteSuite(recordId)
    else await appRecordApi.deleteCase(recordId)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function restoreRecord(recordId) {
  try {
    if (recordType.value === 'plan') await appRecordApi.restorePlan(recordId)
    else if (recordType.value === 'suite') await appRecordApi.restoreSuite(recordId)
    else await appRecordApi.restoreCase(recordId)
    ElMessage.success('已恢复')
    loadList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '恢复失败')
  }
}

async function stopRecord(recordId) {
  if (recordType.value === 'plan') {
    await appExecApi.stopPlan(recordId)
  } else if (recordType.value === 'suite') {
    await appExecApi.stopSuite(recordId)
  } else {
    await appExecApi.stopCase(recordId)
  }
  ElMessage.success('已发送停止指令')
  loadList()
}

loadList()
</script>

<style scoped lang="scss">
@use '@/styles/app-report.scss';

.record-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}
.detail-body {
  min-height: 120px;
}
.section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}
</style>
