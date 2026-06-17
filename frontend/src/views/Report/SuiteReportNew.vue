<template>
  <PageCard v-if="runInfo.id" class="suite-report-new">
    <template #title>
      <div class="report-header">
        <span>测试套件报告</span>
        <el-button type="success" :icon="Download" @click="showExportDialog">
          导出报告
        </el-button>
        <el-button
          v-if="canAiAnalyze && (runInfo.fail || runInfo.error)"
          type="warning"
          :loading="batchAnalyzing"
          @click="runBatchAnalyze"
        >
          批量 AI 分析失败
        </el-button>
      </div>
    </template>
    
    <template #main>
      <ReportSummaryPanel report-type="ui_suite" :record-id="Number(id)" />
      <!-- 套件概览卡片 -->
      <div class="suite-overview">
        <div class="suite-title">{{ runInfo.suite_name }}</div>
        <el-row :gutter="16">
          <el-col :span="4">
            <div class="stat-card" :class="runInfo.status">
              <div class="stat-icon">
                <el-icon :size="32"><component :is="getStatusIcon(runInfo.status)" /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">执行状态</div>
                <div class="stat-value">{{ getStatusText(runInfo.status) }}</div>
              </div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card">
              <div class="stat-icon time">
                <el-icon :size="32"><Timer /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">执行耗时</div>
                <div class="stat-value">{{ formatDuration(runInfo.duration) }}</div>
              </div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card">
              <div class="stat-icon pass-rate" :style="{ color: getPassRateColor(runInfo.pass_rate) }">
                <el-icon :size="32"><TrendCharts /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">通过率</div>
                <div class="stat-value" :style="{ color: getPassRateColor(runInfo.pass_rate) }">
                  {{ (runInfo.pass_rate || 0).toFixed(2) }}%
                </div>
              </div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card">
              <div class="stat-icon total">
                <el-icon :size="32"><Files /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">用例总数</div>
                <div class="stat-value">{{ runInfo.case_count }}</div>
              </div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card">
              <div class="stat-icon env">
                <el-icon :size="32"><Monitor /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-label">执行环境</div>
                <div class="stat-value stat-value--env">{{ envDisplayName }}</div>
              </div>
            </div>
          </el-col>
        </el-row>
        
        <!-- 统计详情 -->
        <div class="stats-detail">
          <div class="stat-item success">
            <span class="stat-dot"></span>
            <span class="stat-text">通过: {{ runInfo.success }}</span>
          </div>
          <div class="stat-item fail">
            <span class="stat-dot"></span>
            <span class="stat-text">失败: {{ runInfo.fail }}</span>
          </div>
          <div class="stat-item error">
            <span class="stat-dot"></span>
            <span class="stat-text">错误: {{ runInfo.error }}</span>
          </div>
          <div class="stat-item skip">
            <span class="stat-dot"></span>
            <span class="stat-text">跳过: {{ runInfo.skip }}</span>
          </div>
          <div class="stat-item no-run">
            <span class="stat-dot"></span>
            <span class="stat-text">未执行: {{ runInfo.no_run }}</span>
          </div>
        </div>
      </div>

      <!-- 时间轴视图 -->
      <div v-if="showTimeline" class="timeline-view">
        <div class="section-title-with-action">
          <div class="section-title">
            <el-icon><Timer /></el-icon>
            用例执行时间轴
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
              v-for="(caseItem, index) in caseRunList"
              :key="caseItem.id"
              :type="getCaseStatusType(caseItem.status)"
              :icon="getCaseStatusIcon(caseItem.status)"
              :timestamp="formatTime(caseItem.start_time)"
              placement="top"
            >
              <el-card 
                :class="['case-timeline-card', caseItem.status]" 
                shadow="hover"
                @click="toggleCaseDetail(caseItem)"
              >
                <template #header>
                  <div class="case-header">
                    <div class="case-title">
                      <span class="case-index">#{{ index + 1 }}</span>
                      <span class="case-name">{{ caseItem.result_data?.name || '未知用例' }}</span>
                      <el-tag size="small" :type="getCaseStatusType(caseItem.status)">
                        {{ getStatusText(caseItem.status) }}
                      </el-tag>
                    </div>
                    <div class="case-meta">
                      <el-icon><Timer /></el-icon>
                      {{ formatDuration(caseItem.result_data?.duration) }}
                      <el-icon><User /></el-icon>
                      {{ caseItem.username }}
                      <el-button
                        v-if="isUiFailed(caseItem.status) && canAiAnalyze"
                        link
                        type="warning"
                        size="small"
                        @click.stop="openAiAnalyze(caseItem.id)"
                      >AI 分析</el-button>
                    </div>
                  </div>
                </template>
                
                <!-- 展开的用例详情 -->
                <div v-if="expandedCases.includes(caseItem.id)" class="case-detail">
                  <CaseReportTimeline :runInfo="caseItem.result_data" />
                </div>
                
                <!-- 折叠状态提示 -->
                <div v-else class="case-collapsed">
                  <el-icon><ArrowDown /></el-icon>
                  点击查看用例执行详情 ({{ caseItem.result_data?.steps?.length || 0 }} 个步骤)
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
            用例执行列表
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
          :data="caseRunList" 
          style="width: 100%"
          :header-cell-style="{'text-align':'center'}" 
          :cell-style="{'text-align':'center'}" 
          stripe
          v-loading="loading"
        >
          <el-table-column type="expand">
            <template #default="props">
              <CaseReportTimeline :runInfo="props.row.result_data" />
            </template>
          </el-table-column>
          <el-table-column type="index" label="序号" :index="tableRowIndex" width="70"/>
          <el-table-column prop="result_data.name" label="用例名称" min-width='180' show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.result_data?.name || '未知用例' }}
            </template>
          </el-table-column>
          <el-table-column label="执行状态" width="110">
            <template #default="scope">
              <el-tag :type="getCaseStatusType(scope.row.status)">
                {{ getStatusText(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="是否跳过" width="100">
            <template #default="scope">
              {{ scope.row.result_data?.skip ? '是' : '否' }}
            </template>
          </el-table-column>
          <el-table-column label="步骤数" width="80">
            <template #default="scope">
              {{ scope.row.result_data?.steps?.length || 0 }}
            </template>
          </el-table-column>
          <el-table-column label="浏览器" width="100">
            <template #default="scope">
              <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
              <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
              <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="执行模式" width="100">
            <template #default="scope">
              <el-tag v-if='scope.row.env?.headless===false' type="success">界面模式</el-tag>
              <el-tag v-else-if='scope.row.env?.headless===true' type="primary">无头模式</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="username" label="执行人" width="100"/>
          <el-table-column label="执行时间" width="170">
            <template #default="scope">
              {{ formatDateTime(scope.row.start_time) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button
                v-if="isUiFailed(scope.row.status) && canAiAnalyze"
                link
                type="warning"
                size="small"
                @click="openAiAnalyze(scope.row.id)"
              >AI 分析</el-button>
            </template>
          </el-table-column>
        </el-table>
        
        <!-- 分页 -->
        <el-pagination
          class="pagination"
          :hide-on-single-page="true"
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @change="getCaseRunList"
        />
      </div>

      <!-- 套件日志 -->
      <ExecutionLogScroller
        v-if="runInfo.execution_log?.length > 0"
        :logs="runInfo.execution_log"
        container-height="300px"
      >
        <template #title>
          <el-icon><Document /></el-icon>
          套件执行日志
        </template>
      </ExecutionLogScroller>

      <!-- 执行环境 -->
      <div class="env-section">
        <div class="section-title">
          <el-icon><Setting /></el-icon>
          执行环境配置
        </div>
        <ExecutionEnvPanel :env="runInfo.env" />
      </div>
    </template>
    
    <template #bottom>
      <el-button @click="back" icon="CircleClose" type="danger" plain>返回套件时间轴</el-button>
    </template>
  </PageCard>
  
  <!-- 加载状态 -->
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

  <FailureAnalyzer
    v-model="aiAnalyzeVisible"
    target-type="ui"
    :target-id="aiAnalyzeTargetId"
  />
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  View, 
  Download, 
  Timer, 
  Files, 
  Monitor,
  TrendCharts,
  CircleCheck,
  CircleClose,
  Warning,
  InfoFilled,
  User,
  ArrowDown,
  Grid,
  Document,
  Setting,
  Loading
} from '@element-plus/icons-vue'
import http from '@/api/index'
import PageCard from "@/components/PageCard.vue"
import CaseReportTimeline from "@/components/Report/CaseReportTimeline.vue"
import ExecutionLogScroller from '@/components/Report/ExecutionLogScroller.vue'
import ExecutionEnvPanel from '@/components/Report/ExecutionEnvPanel.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import ReportSummaryPanel from '@/views/AI/components/ReportSummaryPanel.vue'
import { aiAnalyzeApi } from '@/api/modules/ai.js'
import { UserStore } from "@/stores/module/UserStore.js"
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { makeTableRowIndex } from '@/utils/tableIndex'
import { fileApi } from '@/api/modules/sys'

const router = useRouter()
const route = useRoute()
const uStore = UserStore()
const proStore = ProjectStore()
const id = route.params.id

const canAiAnalyze = computed(() => uStore.hasPermission('ai_test:execute'))
const aiAnalyzeVisible = ref(false)
const aiAnalyzeTargetId = ref(null)
const batchAnalyzing = ref(false)

const isUiFailed = (status) => ['fail', 'failed', 'error'].includes(status)

const openAiAnalyze = (recordId) => {
  aiAnalyzeTargetId.value = recordId
  aiAnalyzeVisible.value = true
}

const runBatchAnalyze = async () => {
  if (!proStore.projectInfo?.id || !runInfo.value?.id) return
  batchAnalyzing.value = true
  try {
    const res = await aiAnalyzeApi.analyzeFailureBatch(
      { report_type: 'ui_suite', record_id: runInfo.value.id, limit: 5 },
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

// 状态
const loading = ref(false)
const showTimeline = ref(true)
const expandedCases = ref([])

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

// 数据
const runInfo = ref({})
const envDisplayName = computed(() => {
  const env = runInfo.value?.env
  if (!env || typeof env !== 'object') return '-'
  return env.env_name || env.target_host || '-'
})
const caseRunList = ref([])
const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pageConfig)

// 状态映射
const statusMap = {
  no_run: { text: '未运行', type: 'info', icon: InfoFilled },
  running: { text: '运行中', type: 'primary', icon: Loading },
  waiting: { text: '等待中', type: 'info', icon: InfoFilled },
  success: { text: '成功', type: 'success', icon: CircleCheck },
  fail: { text: '失败', type: 'danger', icon: Warning },
  failed: { text: '失败', type: 'danger', icon: Warning },
  error: { text: '错误', type: 'warning', icon: CircleClose },
  skip: { text: '跳过', type: 'info', icon: InfoFilled },
  '执行完成': { text: '执行完成', type: 'success', icon: CircleCheck },
  '等待执行': { text: '等待执行', type: 'info', icon: InfoFilled },
  '运行中': { text: '运行中', type: 'primary', icon: Loading }
}

// 获取套件详情
const getRunInfo = async () => {
  const response = await http.resultApi.getSuiteRecordDetail(id)
  if (response.status === 200) {
    runInfo.value = response.data
    await getCaseRunList()
  }
}

// 获取用例执行列表
const getCaseRunList = async () => {
  loading.value = true
  try {
    const params = {
      suite_execution_id: id,
      page: pageConfig.page,
      size: pageConfig.size
    }
    const response = await http.resultApi.getCaseRecord(params)
    if (response.status === 200) {
      // 处理每条记录的预签名 URL
      const records = response.data.data || []
      for (const record of records) {
        if (record.result_data) {
          record.result_data = await fileApi.processReportUrls(record.result_data)
        }
      }
      caseRunList.value = records
      pageConfig.total = response.data.total
    }
  } finally {
    loading.value = false
  }
}

// 切换用例详情展开
const toggleCaseDetail = (caseItem) => {
  const index = expandedCases.value.indexOf(caseItem.id)
  if (index > -1) {
    expandedCases.value.splice(index, 1)
  } else {
    expandedCases.value.push(caseItem.id)
  }
}

// 导出报告
const exportReport = async () => {
  exportLoading.value = true
  try {
    const { data } = await http.resultApi.exportReportAsync(id, 'suite', {
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
          link.download = statusData.filename || `测试报告-套件-${runInfo.value.suite_name}-${id}.html`
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
const getStatusText = (status) => statusMap[status]?.text || status
const getStatusIcon = (status) => statusMap[status]?.icon || InfoFilled
const getCaseStatusType = (status) => statusMap[status]?.type || 'info'
const getCaseStatusIcon = (status) => statusMap[status]?.icon || InfoFilled

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
  return date.toLocaleTimeString('zh-CN', { 
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const formatDateTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', { 
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 返回
const back = () => {
  router.back()
  uStore.deleteTabs(route.path)
}

// 初始化
getRunInfo()
</script>

<style scoped lang="scss">
.suite-report-new {
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
  
  .suite-overview {
    margin-bottom: 24px;
    
    .suite-title {
      text-align: center;
      font-size: 20px;
      font-weight: bold;
      margin-bottom: 16px;
      color: var(--el-text-color-primary);
    }
    
    .stat-card {
      display: flex;
      align-items: center;
      padding: 16px;
      background: var(--el-fill-color-light);
      border-radius: 8px;
      transition: all 0.3s;
      
      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
      }
      
      &.success { border-left: 4px solid var(--el-color-success); }
      &.fail { border-left: 4px solid var(--el-color-danger); }
      &.error { border-left: 4px solid var(--el-color-warning); }
      &.running { border-left: 4px solid var(--el-color-primary); }
      
      .stat-icon {
        margin-right: 12px;
        color: var(--el-color-primary);
        
        &.time { color: var(--el-color-info); }
        &.total { color: var(--el-color-success); }
        &.env { color: var(--el-color-warning); }
      }
      
      .stat-info {
        .stat-label {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
        
        .stat-value {
          font-size: 18px;
          font-weight: bold;
          color: var(--el-text-color-primary);

          &.stat-value--env {
            font-size: 14px;
            font-weight: 600;
            word-break: break-all;
          }
        }
      }
    }
    
    .stats-detail {
      display: flex;
      justify-content: center;
      gap: 24px;
      margin-top: 16px;
      padding: 12px;
      background: var(--el-fill-color-light);
      border-radius: 8px;
      
      .stat-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 14px;
        
        .stat-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
        }
        
        &.success .stat-dot { background: var(--el-color-success); }
        &.fail .stat-dot { background: var(--el-color-danger); }
        &.error .stat-dot { background: var(--el-color-warning); }
        &.skip .stat-dot { background: var(--el-color-info); }
        &.no-run .stat-dot { background: var(--el-text-color-disabled); }
      }
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
      
      .case-timeline-card {
        cursor: pointer;
        transition: all 0.3s;
        
        &:hover {
          transform: translateX(4px);
        }
        
        &.success { border-left: 3px solid var(--el-color-success); }
        &.fail { border-left: 3px solid var(--el-color-danger); }
        &.error { border-left: 3px solid var(--el-color-warning); }
        &.skip { border-left: 3px solid var(--el-color-info); }
        
        .case-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          
          .case-title {
            display: flex;
            align-items: center;
            gap: 12px;
            
            .case-index {
              font-weight: bold;
              color: var(--el-color-primary);
            }
            
            .case-name {
              flex: 1;
              font-weight: 500;
            }
          }
          
          .case-meta {
            display: flex;
            align-items: center;
            gap: 12px;
            color: var(--el-text-color-secondary);
            font-size: 13px;
          }
        }
        
        .case-collapsed {
          text-align: center;
          color: var(--el-text-color-secondary);
          padding: 12px;
          font-size: 13px;
        }
        
        .case-detail {
          padding: 16px;
          background: var(--el-bg-color);
          border-radius: 8px;
        }
      }
    }
  }
  
  .table-view {
    .pagination {
      margin-top: 16px;
      justify-content: flex-end;
    }
  }
  
  .env-section {
    // 样式由 ExecutionEnvPanel 内部承担
  }
}

.loading-container {
  padding: 40px;
}
</style>
