<template>
  <PageCard v-if="runInfo.id" class="app-suite-report">
    <template #title>
      <div class="report-header">
        <span>App 套件报告</span>
        <div>
          <IterationReportShortcut
            v-if="runInfo.id"
            :record-id="runInfo.id"
            report-type="app_suite"
            :title="runInfo.suite_name"
          />
          <ReportKnowledgeBridge
            v-if="runInfo.id && proStore.projectInfo?.id"
            :project-id="proStore.projectInfo.id"
            report-type="app_suite"
            :record-id="runInfo.id"
            :title="runInfo.suite_name"
          />
          <el-button v-if="runInfo.suite_id" type="primary" plain @click="goEditSuite">编辑套件</el-button>
          <el-button type="success" :loading="exportLoading" @click="exportReport">导出 HTML</el-button>
        </div>
      </div>
    </template>
    <template #main>
      <ReportSummaryPanel report-type="app_suite" :record-id="Number(route.params.id)" />
      <ReportFailureBatchBar
        v-if="canAiAnalyze && ((runInfo.fail || 0) + (runInfo.error || 0) > 0)"
        :project-id="proStore.projectInfo?.id"
        report-type="app_suite"
        :record-id="runInfo.id"
        :record-title="runInfo.suite_name"
      />
      <AppReportOverview
        :title="runInfo.suite_name"
        :status="runInfo.status"
        :pass-rate="runInfo.pass_rate"
        :success="runInfo.success"
        :fail="runInfo.fail"
        :error="runInfo.error"
        :skip="runInfo.skip"
        :quarantine-skip="runInfo.quarantine_skip"
        :case-count="runInfo.case_count"
        :duration="runInfo.duration"
        :username="runInfo.username"
        :start-time="runInfo.start_time"
      />
      <AppReportEnvSummary
        :env="runInfo.env"
        :device-id="runInfo.device_id"
        :username="runInfo.username"
        :start-time="runInfo.start_time"
        :driver-mode="runInfo.env?.driver_mode"
      />
      <el-table :data="cases" stripe class="app-report-table">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="app-report-expand">
              <CaseReportTimeline v-if="row.result_data" :runInfo="row.result_data" profile="app" />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="case_name" label="用例" min-width="160" />
        <el-table-column prop="status" label="结果" width="110">
          <template #default="{ row }">
            <el-tag :type="caseTag(row.status).type">{{ caseTag(row.status).text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="isFailed(row.status) && canAnalyzeExecution(row)"
              type="warning"
              link
              @click="openAiAnalyze(row.id)"
            >AI 分析</el-button>
            <el-button
              v-if="isFailed(row.status)"
              type="primary"
              link
              @click="goEditWithFailure(row)"
            >定位失败</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </PageCard>
  <el-empty v-else description="加载中或记录不存在" />

  <FailureAnalyzer
    v-model="aiAnalyzeVisible"
    target-type="app"
    :target-id="aiAnalyzeTargetId"
  />
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import AppReportOverview from '@/views/App/components/AppReportOverview.vue'
import AppReportEnvSummary from '@/views/App/components/AppReportEnvSummary.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import ReportSummaryPanel from '@/views/AI/components/ReportSummaryPanel.vue'
import ReportFailureBatchBar from '@/components/ReportFailureBatchBar.vue'
import ReportKnowledgeBridge from '@/components/ReportKnowledgeBridge.vue'
import IterationReportShortcut from '@/components/IterationReportShortcut.vue'
import { appRecordApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { useFailureAnalysisGate } from '@/composables/useFailureAnalysisGate.js'
import dateTools from '@/tools/dateTools.js'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const runInfo = ref({})
const cases = ref([])
const exportLoading = ref(false)
const aiAnalyzeVisible = ref(false)
const aiAnalyzeTargetId = ref(null)

const { canShowFailureAnalysis: canAiAnalyze, loadExecSettings, canAnalyzeExecution } = useFailureAnalysisGate(runInfo, { syncProject: true })

function openAiAnalyze(recordId) {
  aiAnalyzeTargetId.value = recordId
  aiAnalyzeVisible.value = true
}

function formatTime(v) {
  return v ? dateTools.rTime(v) : '-'
}

function caseTag(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'success') return { text: '成功', type: 'success' }
  if (s === 'fail' || s === 'failed') return { text: '失败', type: 'danger' }
  if (s === 'error') return { text: '错误', type: 'warning' }
  if (s === 'running') return { text: '运行中', type: 'primary' }
  return { text: status || '-', type: 'info' }
}

function isFailed(status) {
  return ['fail', 'failed', 'error'].includes(String(status || '').toLowerCase())
}

function goEditWithFailure(row) {
  if (!row?.case_id) return
  router.push({
    name: 'appCaseEdit',
    params: { id: row.case_id },
    query: { execution_id: row.id },
  })
}

async function loadDetail() {
  try {
    const res = await appRecordApi.suiteDetail(route.params.id)
    runInfo.value = res.data || {}
    cases.value = res.data?.cases || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载套件报告失败')
  }
}

function goEditSuite() {
  router.push({ name: 'appSuiteEdit', params: { id: runInfo.value.suite_id } })
}

async function exportReport() {
  exportLoading.value = true
  try {
    const res = await appRecordApi.exportReport(route.params.id, { record_type: 'suite' })
    const blob = new Blob([res.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `app-suite-report-${route.params.id}.html`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  } finally {
    exportLoading.value = false
  }
}

onMounted(loadDetail)
</script>

<style scoped lang="scss">
@use '@/styles/app-report.scss';

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
</style>
