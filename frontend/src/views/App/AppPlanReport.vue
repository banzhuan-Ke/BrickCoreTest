<template>
  <PageCard v-if="runInfo.id" class="app-plan-report">
    <template #title>
      <div class="report-header">
        <span>App 计划报告</span>
        <div>
          <el-button
            v-if="canAiAnalyze && ((runInfo.fail || 0) + (runInfo.error || 0) > 0)"
            type="warning"
            plain
            :loading="batchAnalyzing"
            @click="runBatchAnalyze"
          >批量 AI 分析失败</el-button>
          <el-button v-if="runInfo.plan_id" type="primary" plain @click="goEditPlan">编辑计划</el-button>
          <el-button type="success" :loading="exportLoading" @click="exportReport">导出 HTML</el-button>
        </div>
      </div>
    </template>
    <template #main>
      <ReportSummaryPanel report-type="app_plan" :record-id="Number(route.params.id)" />
      <AppReportOverview
        :title="runInfo.plan_name"
        :status="runInfo.status"
        :pass-rate="runInfo.pass_rate"
        :success="runInfo.success"
        :fail="runInfo.fail"
        :error="runInfo.error"
        :skip="runInfo.skip"
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
      <el-table :data="suites" stripe row-key="id" class="app-report-table">
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table :data="row.cases || []" size="small" stripe class="nested-case-table">
              <el-table-column type="expand">
                <template #default="{ row: caseRow }">
                  <div class="app-report-expand">
                    <CaseReportTimeline v-if="caseRow.result_data" :runInfo="caseRow.result_data" profile="app" />
                    <el-empty v-else description="暂无步骤详情" :image-size="60" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="case_name" label="用例" min-width="140" />
              <el-table-column prop="status" label="结果" width="100">
                <template #default="{ row: caseRow }">
                  <el-tag :type="caseTag(caseRow.status).type">{{ caseTag(caseRow.status).text }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="start_time" label="开始时间" min-width="150">
                <template #default="{ row: caseRow }">{{ formatTime(caseRow.start_time) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="200">
                <template #default="{ row: caseRow }">
                  <el-button
                    v-if="isFailed(caseRow.status) && canAiAnalyze"
                    type="warning"
                    link
                    @click="openAiAnalyze(caseRow.id)"
                  >AI 分析</el-button>
                  <el-button
                    v-if="isFailed(caseRow.status)"
                    type="primary"
                    link
                    @click="goEditWithFailure(caseRow)"
                  >定位失败</el-button>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column prop="suite_name" label="套件" min-width="160" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="pass_rate" label="通过率" width="100">
          <template #default="{ row }">{{ (row.pass_rate || 0).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column prop="duration" label="耗时(s)" width="90" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button type="primary" link @click="openSuiteReport(row.id)">套件报告</el-button>
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
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import AppReportOverview from '@/views/App/components/AppReportOverview.vue'
import AppReportEnvSummary from '@/views/App/components/AppReportEnvSummary.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import ReportSummaryPanel from '@/views/AI/components/ReportSummaryPanel.vue'
import { appRecordApi } from '@/api'
import { aiAnalyzeApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import dateTools from '@/tools/dateTools.js'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const runInfo = ref({})
const suites = ref([])
const exportLoading = ref(false)
const batchAnalyzing = ref(false)
const aiAnalyzeVisible = ref(false)
const aiAnalyzeTargetId = ref(null)

const canAiAnalyze = computed(() => uStore.hasPermission('ai_test:execute'))

async function runBatchAnalyze() {
  if (!proStore.projectInfo?.id || !route.params.id) return
  batchAnalyzing.value = true
  try {
    const res = await aiAnalyzeApi.analyzeFailureBatch(
      { report_type: 'app_plan', record_id: Number(route.params.id), limit: 5 },
      proStore.projectInfo.id,
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '批量分析完成')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '批量分析失败')
  } finally {
    batchAnalyzing.value = false
  }
}

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
    const res = await appRecordApi.planDetail(route.params.id)
    const data = res.data || {}
    runInfo.value = data
    suites.value = data.suites || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载计划报告失败')
  }
}

function goEditPlan() {
  router.push({ name: 'appPlanEdit', params: { id: runInfo.value.plan_id } })
}

function openSuiteReport(suiteExecutionId) {
  router.push({ name: 'appSuiteReport', params: { id: suiteExecutionId } })
}

async function exportReport() {
  exportLoading.value = true
  try {
    const res = await appRecordApi.exportReport(route.params.id, { record_type: 'task' })
    const blob = new Blob([res.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `app-plan-report-${route.params.id}.html`
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
.nested-case-table {
  margin: 8px 0 8px 24px;
}
</style>
