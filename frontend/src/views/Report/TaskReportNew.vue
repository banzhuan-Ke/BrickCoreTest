<template>
  <PageCard v-if="taskRunDetail" class="task-report-new">
    <template #title>
      <div class="report-header">
        <span>测试计划报告</span>
        <el-button type="success" :icon="Download" @click="showExportDialog">
          导出报告
        </el-button>
        <el-button
          v-if="canAiAnalyze && ((taskRunDetail?.fail || 0) + (taskRunDetail?.error || 0) > 0)"
          type="warning"
          :loading="batchAnalyzing"
          @click="runBatchAnalyze"
        >
          批量 AI 分析失败
        </el-button>
      </div>
    </template>
    
    <template #main>
      <ReportSummaryPanel report-type="ui_task" :record-id="Number(task_id)" />
      <!-- 任务概览 -->
      <div class="task-overview">
        <div class="task-title">{{ taskRunDetail.task_name }}</div>
        <el-row :gutter="16">
          <el-col :span="4" v-for="stat in taskStats" :key="stat.key">
            <div class="stat-card" :class="stat.class">
              <div class="stat-value" :style="{ color: stat.color }">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
            </div>
          </el-col>
        </el-row>
        
        <!-- 任务信息 -->
        <div class="task-info">
          <el-descriptions :column="4" border>
            <el-descriptions-item label="执行状态">
              <el-tag :type="getStatusType(taskRunDetail.status)">
                {{ taskRunDetail.status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="执行人">{{ taskRunDetail.username }}</el-descriptions-item>
            <el-descriptions-item label="执行时间">
              {{ dateTools.rTime(taskRunDetail.start_time) }}
            </el-descriptions-item>
            <el-descriptions-item label="执行环境">
              {{ taskEnvDisplayName }}
            </el-descriptions-item>
            <el-descriptions-item label="执行耗时">
              {{ formatDuration(taskRunDetail.duration) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </div>

      <!-- 图表概览 -->
      <el-row :gutter="16" class="charts-row">
        <el-col :span="14">
          <el-card>
            <template #header>
              <span class="card-title">用例执行统计</span>
            </template>
            <div ref="chart1Ref" class="chart-container"></div>
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card>
            <template #header>
              <span class="card-title">通过率分布</span>
            </template>
            <div ref="chart2Ref" class="chart-container"></div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 时间轴视图 - 套件执行流程 -->
      <div v-if="showTimeline" class="timeline-view">
        <div class="section-title-with-action">
          <div class="section-title">
            <el-icon><Timer /></el-icon>
            套件执行时间轴
          </div>
          <el-button 
            type="primary" 
            :icon="Grid"
            @click="showTimeline = false"
            size="small"
          >
            切换表格视图
          </el-button>
        </div>
        <div class="timeline-container">
          <el-timeline>
            <el-timeline-item
              v-for="(suite, index) in SuiteRunList"
              :key="suite.id"
              :type="getSuiteStatusType(suite.status)"
              :icon="getSuiteStatusIcon(suite.status)"
              :timestamp="formatTime(suite.start_time)"
              placement="top"
            >
              <el-card 
                :class="['suite-timeline-card', suite.status]" 
                shadow="hover"
                @click="goToSuiteReport(suite)"
              >
                <template #header>
                  <div class="suite-header">
                    <div class="suite-info">
                      <span class="suite-index">#{{ index + 1 }}</span>
                      <span class="suite-name">{{ suite.suite_name }}</span>
                      <el-tag size="small" :type="getSuiteStatusType(suite.status)">
                        {{ suite.status }}
                      </el-tag>
                    </div>
                    <div class="suite-stats">
                      <span class="stat-item">
                        <el-icon><Timer /></el-icon>
                        {{ formatDuration(suite.duration) }}
                      </span>
                      <span class="stat-item">
                        <el-icon><TrendCharts /></el-icon>
                        {{ (suite.pass_rate || 0).toFixed(2) }}%
                      </span>
                    </div>
                  </div>
                </template>
                <div class="suite-detail">
                  <div class="detail-row">
                    <span class="detail-label">浏览器:</span>
                    <el-tag size="small" :type="getBrowserType(suite.env?.browser)">
                      {{ getBrowserText(suite.env?.browser) }}
                    </el-tag>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">执行模式:</span>
                    <el-tag size="small" :type="suite.env?.headless ? 'primary' : 'success'">
                      {{ suite.env?.headless ? '无头模式' : '界面模式' }}
                    </el-tag>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">用例统计:</span>
                    <span class="case-stats">
                      <span class="success">通过: {{ suite.success }}</span>
                      <span class="fail">失败: {{ suite.fail }}</span>
                      <span class="error">错误: {{ suite.error }}</span>
                      <span class="skip">跳过: {{ suite.skip }}</span>
                    </span>
                  </div>
                </div>
                <div class="suite-footer">
                  <el-button type="primary" link :icon="View">查看详细报告</el-button>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>

      <!-- 表格视图 -->
      <div v-else class="table-view">
        <div class="section-title-with-action">
          <div class="section-title">
            <el-icon><Grid /></el-icon>
            套件执行列表
          </div>
          <el-button 
            type="primary" 
            :icon="Timer"
            @click="showTimeline = true"
            size="small"
          >
            切换时间轴视图
          </el-button>
        </div>
        <el-table 
          :data="SuiteRunList" 
          style="width: 100%"
          :header-cell-style="{'text-align':'center'}" 
          :cell-style="{'text-align':'center'}" 
          stripe
          v-loading="loading"
        >
          <el-table-column label="序号" type="index" :index="tableRowIndex" width="70"/>
          <el-table-column prop="suite_name" label="套件名称" min-width='150' show-overflow-tooltip/>
          <el-table-column label="执行状态" width="110">
            <template #default="scope">
              <el-tag :type="getSuiteStatusType(scope.row.status)">
                {{ scope.row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="浏览器" width="100">
            <template #default="scope">
              <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
              <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
              <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="执行模式" width="100">
            <template #default="scope">
              <el-tag v-if='scope.row.env?.headless===false' type="success">界面模式</el-tag>
              <el-tag v-else-if='scope.row.env?.headless===true' type="primary">无头模式</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="执行耗时" width="110">
            <template #default="scope">
              {{ formatDuration(scope.row.duration) }}
            </template>
          </el-table-column>
          <el-table-column label="通过率" width="100">
            <template #default="scope">
              <span :style="{ color: getPassRateColor(scope.row.pass_rate) }">
                {{ (scope.row.pass_rate || 0).toFixed(2) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="case_count" label="用例总数" width="90"/>
          <el-table-column prop="success" label="通过" width="70">
            <template #default="scope">
              <span class="text-success">{{ scope.row.success }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="fail" label="失败" width="70">
            <template #default="scope">
              <span class="text-danger">{{ scope.row.fail }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="error" label="错误" width="70">
            <template #default="scope">
              <span class="text-warning">{{ scope.row.error }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="username" label="执行人" width="100"/>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button 
                @click="goToSuiteReport(scope.row)" 
                type="primary" 
                link
                icon="View"
              >
                报告
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        
        <!-- 分页 -->
        <el-pagination
          class="pagination"
          :hide-on-single-page="true"
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @change="getSuiteList"
        />
      </div>

      <!-- 任务日志 -->
      <ExecutionLogScroller
        v-if="taskRunDetail.execution_log?.length > 0"
        :logs="taskRunDetail.execution_log"
        container-height="300px"
        show-time
        show-level
      >
        <template #title>
          <el-icon><Document /></el-icon>
          任务执行日志
        </template>
      </ExecutionLogScroller>
    </template>
    
    <template #bottom>
      <el-button type="danger" @click="back" icon="CircleClose" plain>关闭</el-button>
    </template>
  </PageCard>
  
  <div v-else class="loading-container">
    <el-skeleton :rows="10" animated />
  </div>
  
  <!-- 导出选项弹窗 -->
  <el-dialog
    v-model="exportDialogVisible"
    title="导出报告选项"
    width="400px"
    :close-on-click-modal="false"
  >
    <el-form :model="exportOptions" label-width="120px">
      <el-form-item label="包含图片">
        <el-switch v-model="exportOptions.include_images" />
      </el-form-item>
      
      <el-form-item label="图片范围" v-if="exportOptions.include_images">
        <el-radio-group v-model="exportOptions.image_mode">
          <el-radio label="all">全部</el-radio>
          <el-radio label="failed">仅失败</el-radio>
        </el-radio-group>
      </el-form-item>
      

      
      <el-form-item label="包含视频">
        <el-switch v-model="exportOptions.include_video" />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="exportDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="exportReport" :loading="exportLoading">
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUpdated, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  View, 
  Download,
  Timer,
  TrendCharts,
  CircleCheck,
  CircleClose,
  Warning,
  InfoFilled,
  Loading,
  Grid,
  Document
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { useDark } from '@vueuse/core'

import http from '@/api/index'
import PageCard from "@/components/PageCard.vue"
import ExecutionLogScroller from '@/components/Report/ExecutionLogScroller.vue'
import dateTools from '@/tools/dateTools'
import chart from '@/tools/chart'
import { UserStore } from "@/stores/module/UserStore.js"
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { makeTableRowIndex } from '@/utils/tableIndex'
import ReportSummaryPanel from '@/views/AI/components/ReportSummaryPanel.vue'
import { aiAnalyzeApi } from '@/api/modules/ai.js'

const router = useRouter()
const route = useRoute()
const isDark = useDark()
const uStore = UserStore()
const proStore = ProjectStore()
const canAiAnalyze = computed(() => uStore.hasPermission('ai_test:execute'))
const batchAnalyzing = ref(false)

const runBatchAnalyze = async () => {
  if (!proStore.projectInfo?.id || !task_id) return
  batchAnalyzing.value = true
  try {
    const res = await aiAnalyzeApi.analyzeFailureBatch(
      { report_type: 'ui_task', record_id: Number(task_id), limit: 5 },
      proStore.projectInfo.id
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

const task_id = route.params.id
const loading = ref(false)
// 根据 query 参数设置初始视图：normal=表格视图, chart=时间轴视图(默认)
const showTimeline = ref(route.query.mode === 'chart' || !route.query.mode)

// 图表引用
const chart1Ref = ref(null)
const chart2Ref = ref(null)
let chart1Instance = null
let chart2Instance = null

// 数据
const taskRunDetail = ref(null)
const taskEnvDisplayName = computed(() => {
  const env = taskRunDetail.value?.env
  if (!env || typeof env !== 'object') return '-'
  return env.env_name || env.target_host || '-'
})
const SuiteRunList = ref([])
const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pageConfig)

// 状态映射
const statusMap = {
  '执行完成': { type: 'success', icon: CircleCheck },
  '等待执行': { type: 'info', icon: InfoFilled },
  '运行中': { type: 'primary', icon: Loading }
}

// 计算统计数据
const taskStats = computed(() => [
  { key: 'pass_rate', label: '通过率', value: `${(taskRunDetail.value?.pass_rate || 0).toFixed(2)}%`, color: getPassRateColor(taskRunDetail.value?.pass_rate), class: 'highlight' },
  { key: 'case_count', label: '用例总数', value: taskRunDetail.value?.case_count || 0, color: '#409eff', class: 'total' },
  { key: 'success', label: '通过', value: taskRunDetail.value?.success || 0, color: '#67c23a', class: 'success' },
  { key: 'fail', label: '失败', value: taskRunDetail.value?.fail || 0, color: '#f56c6c', class: 'danger' },
  { key: 'error', label: '错误', value: taskRunDetail.value?.error || 0, color: '#e6a23c', class: 'warning' },
  { key: 'skip', label: '跳过', value: taskRunDetail.value?.skip || 0, color: '#909399', class: 'info' }
])

// 获取任务报告
const getTaskReport = async () => {
  const response = await http.resultApi.getTaskRecordDetail(task_id)
  if (response.status === 200) {
    taskRunDetail.value = response.data
    nextTick(() => initCharts())
  }
}

// 获取套件列表
const getSuiteList = async () => {
  loading.value = true
  try {
    const params = {
      task_records_id: task_id,
      page: showTimeline.value ? 1 : pageConfig.page,
      size: showTimeline.value ? 100 : pageConfig.size
    }
    const response = await http.resultApi.getSuiteRecord(params)
    if (response.status === 200) {
      SuiteRunList.value = response.data.data
      pageConfig.total = response.data.total
    }
  } finally {
    loading.value = false
  }
}

// 初始化图表
const initCharts = () => {
  if (!chart1Ref.value || !chart2Ref.value || !taskRunDetail.value) return
  
  // 销毁旧实例
  if (chart1Instance) echarts.dispose(chart1Instance)
  if (chart2Instance) echarts.dispose(chart2Instance)
  
  // 执行信息图表
  const value = [
    taskRunDetail.value.case_count,
    taskRunDetail.value.success,
    taskRunDetail.value.fail,
    taskRunDetail.value.error,
    taskRunDetail.value.skip,
    taskRunDetail.value.no_run
  ]
  const label = ['用例总数', '通过用例', '失败用例', '错误用例', '跳过用例', '未运行用例']
  chart1Instance = echarts.init(chart1Ref.value)
  chart1Instance.setOption(chart.getChart1Option(value, label, isDark.value))
  
  // 通过率图表
  const datas = [
    { value: taskRunDetail.value.success || 0, name: '通过用例' },
    { value: taskRunDetail.value.fail || 0, name: '失败用例' },
    { value: taskRunDetail.value.error || 0, name: '错误用例' },
    { value: taskRunDetail.value.skip || 0, name: '跳过用例' },
    { value: taskRunDetail.value.no_run || 0, name: '未运行用例' }
  ]
  chart2Instance = echarts.init(chart2Ref.value)
  chart2Instance.setOption(chart.getChart2Option(datas, isDark.value))
}

// 跳转套件报告
const goToSuiteReport = (suite) => {
  router.push({ name: 'suiteReport', params: { id: suite.id } })
}

// 导出选项弹窗
const exportDialogVisible = ref(false)
const exportLoading = ref(false)
const exportOptions = reactive({
  include_images: true,
  image_mode: 'failed',
  include_video: false
})

// 显示导出弹窗
const showExportDialog = () => {
  exportDialogVisible.value = true
}

// 导出报告
const exportReport = async () => {
  exportLoading.value = true
  try {
    const { data } = await http.resultApi.exportReportAsync(task_id, 'task', {
      include_images: exportOptions.include_images,
      image_mode: exportOptions.image_mode,
      include_video: exportOptions.include_video
    })
    const taskId = data.task_id
    exportDialogVisible.value = false
    ElMessage.info('报告生成中，请稍候...')
    
    const timer = setInterval(async () => {
      try {
        const { data: statusData } = await http.resultApi.getExportStatus(taskId)
        if (statusData.status === 'completed') {
          clearInterval(timer)
          exportLoading.value = false
          const link = document.createElement('a')
          link.href = statusData.download_url
          link.download = statusData.filename || `测试报告-任务-${taskRunDetail.value.task_name}-${task_id}.html`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          ElMessage.success('报告导出成功')
        } else if (statusData.status === 'failed') {
          clearInterval(timer)
          exportLoading.value = false
          ElMessage.error('报告导出失败：' + (statusData.error || '未知错误'))
        }
      } catch (e) {
        clearInterval(timer)
        exportLoading.value = false
        ElMessage.error('查询导出状态失败')
      }
    }, 2000)
  } catch (error) {
    exportLoading.value = false
    ElMessage.error('提交导出任务失败')
  }
}

// 工具函数
const getStatusType = (status) => statusMap[status]?.type || 'info'
const getSuiteStatusType = (status) => statusMap[status]?.type || 'info'
const getSuiteStatusIcon = (status) => statusMap[status]?.icon || InfoFilled
const getPassRateColor = (rate) => {
  if (rate >= 90) return '#67c23a'
  if (rate >= 70) return '#e6a23c'
  return '#f56c6c'
}
const formatDuration = (duration) => {
  if (!duration) return '-'
  if (duration < 1) return `${(duration * 1000).toFixed(0)}ms`
  if (duration < 60) return `${duration.toFixed(2)}s`
  const mins = Math.floor(duration / 60)
  const secs = (duration % 60).toFixed(2)
  return `${mins}m ${secs}s`
}
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}
const getBrowserType = (type) => {
  const map = { chromium: 'success', firefox: 'warning', webkit: 'info' }
  return map[type] || 'info'
}
const getBrowserText = (type) => {
  const map = { chromium: '谷歌', firefox: '火狐', webkit: 'Safari' }
  return map[type] || type
}

// 返回
const back = () => {
  router.back()
  uStore.deleteTabs(route.path)
}

// 监听暗黑模式
watch(isDark, () => {
  nextTick(() => initCharts())
})

// 初始化
getTaskReport()
getSuiteList()
</script>

<style scoped lang="scss">
.task-report-new {
  .report-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding-right: 20px;
    
    .header-actions {
      display: flex;
      gap: 12px;
    }
  }
  
  .task-overview {
    margin-bottom: 24px;
    
    .task-title {
      text-align: center;
      font-size: 22px;
      font-weight: bold;
      margin-bottom: 16px;
      color: var(--el-text-color-primary);
    }
    
    .stat-card {
      text-align: center;
      padding: 16px 8px;
      background: var(--el-fill-color-light);
      border-radius: 8px;
      transition: all 0.3s;
      
      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
      }
      
      &.success { border-top: 3px solid var(--el-color-success); }
      &.warning { border-top: 3px solid var(--el-color-warning); }
      &.danger { border-top: 3px solid var(--el-color-danger); }
      &.info { border-top: 3px solid var(--el-color-info); }
      &.total { border-top: 3px solid var(--el-color-primary); }
      &.highlight { 
        border-top: 3px solid var(--el-color-primary);
        background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, var(--el-fill-color-light) 100%);
      }
      
      .stat-value {
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 4px;
      }
      
      .stat-label {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
    
    .task-info {
      margin-top: 16px;
    }
  }
  
  .charts-row {
    margin-bottom: 24px;
    
    .card-title {
      font-weight: bold;
    }
    
    .chart-container {
      height: 300px;
    }
  }
  
  .section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: bold;
    margin: 0;
    padding-left: 12px;
    border-left: 4px solid var(--el-color-primary);
  }
  
  .section-title-with-action {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 24px 0 16px;
  }
  
  .timeline-view {
    .timeline-container {
      max-height: 700px;
      overflow-y: auto;
      padding: 16px;
      background: var(--el-fill-color-light);
      border-radius: 8px;
      
      .suite-timeline-card {
        cursor: pointer;
        transition: all 0.3s;
        
        &:hover {
          transform: translateX(4px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        &.执行完成 { border-left: 3px solid var(--el-color-success); }
        &.等待执行 { border-left: 3px solid var(--el-color-info); }
        &.运行中 { border-left: 3px solid var(--el-color-primary); }
        
        .suite-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          
          .suite-info {
            display: flex;
            align-items: center;
            gap: 12px;
            
            .suite-index {
              font-weight: bold;
              color: var(--el-color-primary);
            }
            
            .suite-name {
              font-weight: 500;
            }
          }
          
          .suite-stats {
            display: flex;
            gap: 16px;
            color: var(--el-text-color-secondary);
            font-size: 13px;
            
            .stat-item {
              display: flex;
              align-items: center;
              gap: 4px;
            }
          }
        }
        
        .suite-detail {
          padding: 12px 0;
          
          .detail-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
            
            .detail-label {
              color: var(--el-text-color-secondary);
              width: 70px;
            }
            
            .case-stats {
              display: flex;
              gap: 16px;
              font-size: 13px;
              
              .success { color: var(--el-color-success); }
              .fail { color: var(--el-color-danger); }
              .error { color: var(--el-color-warning); }
              .skip { color: var(--el-text-color-secondary); }
            }
          }
        }
        
        .suite-footer {
          text-align: right;
          padding-top: 8px;
          border-top: 1px solid var(--el-border-color-light);
        }
      }
    }
  }
  
  .table-view {
    .text-success { color: var(--el-color-success); }
    .text-warning { color: var(--el-color-warning); }
    .text-danger { color: var(--el-color-danger); }
    
    .pagination {
      margin-top: 16px;
      justify-content: flex-end;
    }
  }
}

.loading-container {
  padding: 40px;
}
</style>
