<template>
  <div class="run-detail">
    <!-- 执行概览 -->
    <div class="overview" v-if="record">
      <div class="overview-header">
        <h3>{{ isPlanRecord ? '计划执行概览' : '执行概览' }}</h3>
        <div class="overview-actions">
          <IterationReportShortcut
            v-if="recordId"
            :record-id="recordId"
            :report-type="isPlanRecord ? 'api_plan' : 'api_suite'"
            :title="record?.suite_name || record?.plan_name"
          />
          <ReportKnowledgeBridge
            v-if="recordId && projectId"
            :project-id="projectId"
            :report-type="isPlanRecord ? 'api_plan' : 'api_suite'"
            :record-id="recordId"
            :title="record?.suite_name || record?.plan_name"
          />
          <el-button type="success" size="small" @click="exportReport">导出报告</el-button>
        </div>
      </div>
      <ReportSummaryPanel
        v-if="record"
        :report-type="isPlanRecord ? 'api_plan' : 'api_suite'"
        :record-id="recordId"
      />
      <ReportFailureBatchBar
        v-if="canAiAnalyze && record && record.failed_cases > 0"
        :project-id="projectId"
        :report-type="isPlanRecord ? 'api_plan' : 'api_suite'"
        :record-id="recordId"
        :record-title="record?.suite_name || record?.plan_name"
      />
      <el-row :gutter="20">
        <el-col :span="overviewColSpan">
          <div class="stat-card">
            <div class="label">执行状态</div>
            <el-tag :type="getStatusType(record.status)" size="large">
              {{ getStatusText(record.status) }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="overviewColSpan">
          <div class="stat-card">
            <div class="label">用例总数</div>
            <div class="value">{{ record.total_cases }}</div>
          </div>
        </el-col>
        <el-col :span="overviewColSpan">
          <div class="stat-card">
            <div class="label">成功率</div>
            <div class="value" :style="{ color: getSuccessRateColor() }">
              {{ getSuccessRate() }}%
            </div>
          </div>
        </el-col>
        <el-col :span="overviewColSpan">
          <div class="stat-card">
            <div class="label">执行总耗时</div>
            <div class="value">{{ record.duration ? record.duration.toFixed(0) : '-' }}ms</div>
          </div>
        </el-col>
        <el-col :span="overviewColSpan">
          <div class="stat-card stat-card--http">
            <div class="label">接口总耗时</div>
            <div class="value value--http">
              {{ totalHttpMs != null ? totalHttpMs.toFixed(0) : '-' }}ms
            </div>
          </div>
        </el-col>
        <el-col :span="overviewColSpan" v-if="isPlanRecord">
          <div class="stat-card">
            <div class="label">套件数</div>
            <div class="value">{{ planItems.length }}</div>
          </div>
        </el-col>
        <el-col :span="overviewColSpan">
          <div class="stat-card">
            <div class="label">执行环境</div>
            <div class="value value--env">{{ record.env_name || '-' }}</div>
          </div>
        </el-col>
      </el-row>
      <div v-if="record && !isPlanRecord && caseResults.length > 0" style="margin-top:10px; font-size:12px; color:#909399; text-align:right">
        <span>💡 套件总耗时包含用例执行及额外开销（加载、切换、数据库写入等），</span>
        <span>与各用例总耗时之和（{{ caseResults.reduce((sum, c) => sum + (c.response_time || 0), 0).toFixed(0) }}ms）、</span>
        <span>接口总耗时（{{ totalHttpMs != null ? totalHttpMs.toFixed(0) : 0 }}ms）为各用例纯 HTTP 之和，与执行总耗时可能存在差异。</span>
      </div>
      <div v-if="isPlanRecord" style="margin-top:10px; font-size:12px; color:#909399; text-align:right">
        <span>💡 计划执行总耗时包含调度与各 item 开销；</span>
        <span>接口总耗时（{{ totalHttpMs != null ? totalHttpMs.toFixed(0) : 0 }}ms）为全部用例纯 HTTP 之和。</span>
      </div>
    </div>
    
    <!-- 计划执行记录 -->
    <el-collapse v-model="planActiveNames" v-if="isPlanRecord">
      <el-collapse-item
        v-for="(planItem, idx) in planItems"
        :key="idx"
        :name="idx"
      >
        <template #title>
          <div class="case-title">
            <span class="exec-order-tag">#{{ idx + 1 }}</span>
            <el-tag :type="planItem.item_type === 'suite' ? 'primary' : 'info'" size="small">
              {{ planItem.item_type === 'suite' ? '套件' : '用例' }}
            </el-tag>
            <span class="case-name">{{ planItem.name }}</span>
            <el-tag :type="planItem.status === 'success' ? 'success' : 'danger'" size="small">
              {{ planItem.status === 'success' ? '通过' : '失败' }}
            </el-tag>
            <span class="case-meta">
              共{{ planItem.total }}个用例, 成功{{ planItem.success }}, 失败{{ planItem.failed }}
            </span>
            <span class="case-meta">{{ planItem.duration ? planItem.duration.toFixed(0) : 0 }}ms</span>
          </div>
        </template>
        
        <div v-if="planItem.error" style="padding:10px 15px">
          <el-alert :title="planItem.error" type="error" :closable="false" show-icon />
        </div>
        
        <div v-for="(caseItem, cidx) in (planItem.case_results || [])" :key="caseItem.record_id || cidx" class="plan-case-item">
          <div class="plan-case-header">
            <span class="exec-order-tag" style="background:#67c23a">#{{ cidx + 1 }}</span>
            <el-tag :type="caseItem.status === 'success' ? 'success' : 'danger'" size="small">
              {{ caseItem.status === 'success' ? '通过' : '失败' }}
            </el-tag>
            <span class="case-name">{{ caseItem.case_name }}</span>
            <span class="case-meta case-meta--http" v-if="getHttpResponseMs(caseItem) != null">
              接口 {{ getHttpResponseMs(caseItem).toFixed(0) }}ms
            </span>
            <span class="case-meta" v-if="caseItem.response_time">
              总 {{ caseItem.response_time.toFixed ? caseItem.response_time.toFixed(0) : caseItem.response_time }}ms
            </span>
            <span class="case-meta" v-if="caseItem.response_status">HTTP {{ caseItem.response_status }}</span>
            <el-button
              v-if="isApiFailed(caseItem) && canAnalyzeRecord(caseItem)"
              link
              type="warning"
              size="small"
              @click.stop="openAiAnalyze('api', caseItem.record_id)"
            >AI 分析</el-button>
          </div>
          <CaseResultItem :item="caseItem" />
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 套件/单用例执行记录 -->
    <el-collapse v-model="activeNames" v-else>
      <el-collapse-item
        v-for="(item, index) in caseResults"
        :key="item.record_id"
        :name="index"
      >
        <template #title>
          <div class="case-title">
            <span class="exec-order-tag">#{{ index + 1 }}</span>
            <el-tag :type="item.status === 'success' ? 'success' : 'danger'" size="small">
              {{ item.status === 'success' ? '通过' : '失败' }}
            </el-tag>
            <span class="case-name">{{ item.case_name }}</span>
            <span class="case-meta case-meta--http" v-if="getHttpResponseMs(item) != null">
              接口 {{ getHttpResponseMs(item).toFixed(0) }}ms
            </span>
            <span class="case-meta" v-if="item.response_time">
              总 {{ item.response_time.toFixed(0) }}ms
            </span>
            <span class="case-meta" v-if="item.response_status">
              HTTP {{ item.response_status }}
            </span>
            <el-button
              v-if="isApiFailed(item) && canAnalyzeRecord(item)"
              link
              type="warning"
              size="small"
              @click.stop="openAiAnalyze('api', item.record_id)"
            >AI 分析</el-button>
          </div>
        </template>
        <CaseResultItem :item="item" />
      </el-collapse-item>
    </el-collapse>
    
    <el-empty v-if="!loading && !isPlanRecord && !caseResults.length" description="暂无执行数据" />
    <el-empty v-if="!loading && isPlanRecord && !planItems.length" description="暂无执行数据" />

    <FailureAnalyzer
      v-model="aiAnalyzeVisible"
      :target-type="aiAnalyzeTarget.type"
      :target-id="aiAnalyzeTarget.id"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/api/index'
import CaseResultItem from './CaseResultItem.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import ReportSummaryPanel from '@/views/AI/components/ReportSummaryPanel.vue'
import ReportFailureBatchBar from '@/components/ReportFailureBatchBar.vue'
import ReportKnowledgeBridge from '@/components/ReportKnowledgeBridge.vue'
import IterationReportShortcut from '@/components/IterationReportShortcut.vue'
import { useFailureAnalysisGate } from '@/composables/useFailureAnalysisGate.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { getHttpResponseMs, sumHttpResponseMs, sumHttpFromPlanItems } from '../utils/runTiming'

const proStore = ProjectStore()
const { canShowFailureAnalysis: canAiAnalyze, loadExecSettings, canAnalyzeExecution } = useFailureAnalysisGate(ref(null), { syncProject: true })
const projectId = computed(() => proStore.projectInfo?.id)

const props = defineProps({
  recordId: {
    type: Number,
    required: true
  },
  recordType: {
    type: String,
    default: ''   // 'suite' | 'plan' | '' 自动检测
  }
})

const loading = ref(false)
const record = ref(null)
const canAnalyzeRecord = (row) => canAnalyzeExecution(row, record.value?.env)
const caseResults = ref([])
const activeNames = ref([0])
const isPlanRecord = ref(false)
const planItems = ref([])
const planActiveNames = ref([0])

const aiAnalyzeVisible = ref(false)
const aiAnalyzeTarget = ref({ type: 'api', id: null })

const isApiFailed = (item) => item && item.status && item.status !== 'success'

const openAiAnalyze = (type, id) => {
  if (!id) return
  aiAnalyzeTarget.value = { type, id }
  aiAnalyzeVisible.value = true
}

const getStatusType = (status) => {
  const types = {
    success: 'success',
    failed: 'danger',
    running: 'info',
    partial: 'warning'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    success: '成功',
    failed: '失败',
    running: '执行中',
    partial: '部分失败'
  }
  return texts[status] || status
}

const getSuccessRate = () => {
  if (!record.value || !record.value.total_cases) return 0
  return ((record.value.success_cases / record.value.total_cases) * 100).toFixed(1)
}

const getSuccessRateColor = () => {
  const rate = parseFloat(getSuccessRate())
  if (rate === 100) return '#67c23a'
  if (rate >= 80) return '#e6a23c'
  return '#f56c6c'
}

const overviewColSpan = computed(() => (isPlanRecord.value ? 3 : 4))

const totalHttpMs = computed(() => {
  if (record.value?.http_duration != null) {
    return Number(record.value.http_duration)
  }
  if (isPlanRecord.value) {
    return sumHttpFromPlanItems(planItems.value)
  }
  return sumHttpResponseMs(caseResults.value)
})

const fetchDetail = async () => {
  loading.value = true
  isPlanRecord.value = false
  planItems.value = []
  caseResults.value = []
  record.value = null
  try {
    // 如果明确指定了类型，直接走对应分支
    if (props.recordType === 'plan') {
      const res = await http.apiModuleApi.getPlanRecordById(props.recordId)
      const data = res.data || res
      isPlanRecord.value = true
      record.value = {
        id: data.id,
        name: data.plan_name || '测试计划',
        status: data.status,
        total_cases: data.total_cases,
        success_cases: data.success_cases,
        failed_cases: data.failed_cases,
        duration: data.duration,
        http_duration: data.http_duration,
        env_name: data.env_name,
        trigger_type: data.trigger_type,
        run_by: data.run_by,
        start_time: data.start_time,
        end_time: data.end_time
      }
      planItems.value = data.item_results || []
      return
    }

    if (props.recordType === 'suite') {
      const res = await http.apiModuleApi.getRunRecordDetail(props.recordId)
      const data = res.data || res
      record.value = {
        id: data.id,
        name: data.suite_name,
        status: data.status,
        total_cases: data.total_cases,
        success_cases: data.success_cases,
        failed_cases: data.failed_cases,
        duration: data.duration,
        http_duration: data.http_duration,
        env_name: data.env_name
      }
      caseResults.value = data.case_results || []
      return
    }

    // 未指定类型，自动检测：先套件 → 再计划 → 最后用例
    try {
      const res = await http.apiModuleApi.getRunRecordDetail(props.recordId)
      const data = res.data || res
      record.value = {
        id: data.id,
        name: data.suite_name,
        status: data.status,
        total_cases: data.total_cases,
        success_cases: data.success_cases,
        failed_cases: data.failed_cases,
        duration: data.duration,
        http_duration: data.http_duration,
        env_name: data.env_name
      }
      caseResults.value = data.case_results || []
      return
    } catch (suiteError) {
      if (suiteError.response?.status === 404) {
        try {
          const res = await http.apiModuleApi.getPlanRecordById(props.recordId)
          const data = res.data || res
          isPlanRecord.value = true
          record.value = {
            id: data.id,
            name: data.plan_name || '测试计划',
            status: data.status,
            total_cases: data.total_cases,
            success_cases: data.success_cases,
            failed_cases: data.failed_cases,
            duration: data.duration,
            http_duration: data.http_duration,
            env_name: data.env_name,
            trigger_type: data.trigger_type,
            run_by: data.run_by,
            start_time: data.start_time,
            end_time: data.end_time
          }
          planItems.value = data.item_results || []
          return
        } catch (planError) {
          if (planError.response?.status === 404) {
            // 尝试加载单条用例执行记录
            const res = await http.apiModuleApi.getCaseRecordDetail(props.recordId)
            const data = res.data || res
            record.value = {
              id: data.id,
              name: data.case_name,
              status: data.status,
              total_cases: 1,
              success_cases: data.status === 'success' ? 1 : 0,
              failed_cases: data.status !== 'success' ? 1 : 0,
              duration: data.response_time || 0,
              http_duration: data.http_response_time,
              env_name: data.env_name
            }
            caseResults.value = [{
              record_id: data.id,
              case_id: data.case_id,
              case_name: data.case_name,
              status: data.status,
              response_status: data.response_status,
              response_time: data.response_time,
              http_response_time: data.request_detail?.stage_timings?.request_ms,
              response_body: data.response_body,
              response_headers: data.response_headers,
              assertions: data.assertions_result || [],
              extracted_vars: data.extracted_vars || {},
              error_msg: data.error_msg,
              start_time: data.start_time,
              request_detail: data.request_detail || {},
              retry_info: data.request_detail?.retry_info || null
            }]
            return
          }
          throw planError
        }
      }
      throw suiteError
    }
  } catch (error) {
    console.error('获取执行详情失败:', error)
    ElMessage.error('获取执行详情失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchDetail()
})

const exportReport = async () => {
  try {
    const isPlan = props.recordType === 'plan' || isPlanRecord.value
    const res = isPlan
      ? await http.apiModuleApi.exportPlanReport(props.recordId)
      : await http.apiModuleApi.exportApiSuiteReport(props.recordId)
    const blob = new Blob([res.data], { type: 'text/html' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = isPlan
      ? `api_plan_report_${props.recordId}_${new Date().getTime()}.html`
      : `api_report_${props.recordId}_${new Date().getTime()}.html`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (error) {
    console.error('导出报告失败:', error)
    ElMessage.error(error?.response?.data?.detail || '导出报告失败')
  }
}

// 监听 recordId 变化，重新获取数据
watch(() => props.recordId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    fetchDetail()
  }
})
</script>

<style lang="scss" scoped>
.run-detail {
  .overview {
    margin-bottom: 20px;

    .overview-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 15px;

      h3 {
        margin: 0;
        font-size: 16px;
        color: #333;
      }
    }

    .overview-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    
    .stat-card {
      text-align: center;
      padding: 15px;
      background: #f5f7fa;
      border-radius: 4px;
      
      .label {
        color: #666;
        font-size: 14px;
        margin-bottom: 8px;
      }
      
      .value {
        font-size: 24px;
        font-weight: bold;
        color: #333;
      }

      &.stat-card--http .value--http {
        color: #67c23a;
      }

      .value--env {
        font-size: 14px;
        font-weight: 600;
        word-break: break-all;
      }
    }
  }
  
  .case-title {
    display: flex;
    align-items: center;
    gap: 12px;

    .exec-order-tag {
      flex-shrink: 0;
      min-width: 28px;
      padding: 0 8px;
      height: 22px;
      line-height: 22px;
      text-align: center;
      border-radius: 11px;
      background: var(--el-color-primary);
      color: #fff;
      font-size: 12px;
      font-weight: 600;
    }
    
    .case-name {
      flex: 1;
      font-weight: 500;
    }
    
    .case-meta {
      font-size: 12px;
      color: #666;
    }

    .case-meta--http {
      color: #67c23a;
      font-weight: 600;
    }
  }
  
  .case-detail {
    padding: 15px;
    
    .section {
      margin-bottom: 20px;
      
      h4 {
        margin: 0 0 10px;
        color: #333;
        font-size: 14px;
      }
    }
  }
  
  .json-viewer {
    background: #f5f7fa;
    padding: 12px;
    border-radius: 4px;
    margin: 0;
    font-family: monospace;
    font-size: 12px;
    max-height: 400px;
    overflow: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  
  .detail-block {
    margin-bottom: 15px;
    
    .detail-title {
      font-weight: 600;
      font-size: 13px;
      color: #333;
      margin-bottom: 8px;
      padding-left: 8px;
      border-left: 3px solid #409eff;
    }
    
    .detail-content {
      background: #f5f7fa;
      border-radius: 4px;
      padding: 10px;
      
      .compare-row {
        display: flex;
        align-items: center;
        margin-bottom: 6px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .label {
          width: 50px;
          color: #666;
          font-size: 12px;
        }
        
        code {
          flex: 1;
          padding: 3px 6px;
          border-radius: 3px;
          font-family: monospace;
          font-size: 12px;
          word-break: break-all;
          
          &.original {
            background: #eee;
            color: #999;
            text-decoration: line-through;
          }
          
          &.final {
            background: #e6f7ff;
            color: #1890ff;
          }
        }
      }
    }
  }

  .plan-case-item {
    margin: 0 15px 15px;
    border: 1px solid #ebeef5;
    border-radius: 4px;
    overflow: hidden;
    
    .plan-case-header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 15px;
      background: #f5f7fa;
      border-bottom: 1px solid #ebeef5;
    }
  }

  .retry-timeline {
    padding-left: 8px;

    .retry-item {
      display: flex;
      gap: 12px;
      padding: 10px 0;
      border-left: 2px solid #dcdfe6;
      padding-left: 16px;
      position: relative;

      &.success { border-left-color: #67C23A; }
      &.failed { border-left-color: #F56C6C; }
      &.error { border-left-color: #F56C6C; }

      .retry-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #dcdfe6;
        position: absolute;
        left: -6px;
        top: 14px;

        &.success { background: #67C23A; }
        &.failed { background: #F56C6C; }
        &.error { background: #F56C6C; }
      }

      .retry-content {
        .retry-title {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;

          .retry-status-code {
            color: #909399;
            font-size: 12px;
          }

          .retry-time {
            color: #67c23a;
            font-size: 12px;
          }
        }

        .retry-error {
          margin-top: 4px;
          font-size: 12px;
          color: #F56C6C;
        }

        .retry-assertions {
          margin-top: 4px;
          font-size: 12px;
          color: #606266;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
        }

        .retry-assert-badge {
          display: inline-flex;
          align-items: center;
          gap: 3px;
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 11px;
          border: 1px solid;

          &.passed {
            background: #f0f9eb;
            border-color: #b3e19d;
            color: #67c23a;
          }

          &.failed {
            background: #fef0f0;
            border-color: #fbc4c4;
            color: #f56c6c;
          }

          .assert-op { color: #909399; margin: 0 2px; }
          .assert-expected { font-weight: 600; }
          .assert-actual { color: #f56c6c; margin-left: 4px; }
        }

        .retry-body {
          margin-top: 6px;
        }
      }
    }
  }
}
</style>
