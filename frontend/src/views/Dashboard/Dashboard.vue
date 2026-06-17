<template>
  <div class="dashboard-page">
    <!-- 头部筛选区 -->
    <div class="dashboard-header">
      <div class="header-left">
        <h2 class="page-title">📊 首页看板</h2>
        <p class="page-subtitle">
          实时掌握测试平台运行态势
          <el-tag v-if="useProjectFilter && proStore.projectInfo?.name" type="warning" size="small" effect="dark" style="margin-left: 10px;">
            {{ proStore.projectInfo.name }}
          </el-tag>
        </p>
      </div>
      <div class="header-right">
        <div class="project-filter">
          <span class="filter-label">全部项目</span>
          <el-switch v-model="useProjectFilter" active-text="" inactive-text="" />
          <span class="filter-label">当前项目</span>
        </div>
        <el-radio-group v-model="activeTab" size="default" class="tab-group">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="ui">Web</el-radio-button>
          <el-radio-button label="api">接口</el-radio-button>
          <el-radio-button label="perf">性能</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          :shortcuts="dateShortcuts"
          size="default"
          @change="handleDateChange"
        />
        <el-button type="primary" :icon="Refresh" circle size="default" @click="fetchData" />
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <!-- Web/API 模式 -->
      <template v-if="activeTab !== 'perf'">
        <div class="stat-card gradient-blue">
          <div class="stat-icon">🧪</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.caseTotal }}</div>
            <div class="stat-label">用例总数</div>
          </div>
          <div class="stat-sub" v-if="activeTab === 'all'">
            Web {{ stats.ui_case_total }} / 接口 {{ stats.api_case_total }}
          </div>
        </div>
        <div class="stat-card gradient-purple">
          <div class="stat-icon">📦</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.suiteTotal }}</div>
            <div class="stat-label">套件总数</div>
          </div>
          <div class="stat-sub" v-if="activeTab === 'all'">
            Web {{ stats.ui_suite_total }} / 接口 {{ stats.api_suite_total }}
          </div>
        </div>
        <div class="stat-card gradient-green">
          <div class="stat-icon">✅</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.successTotal }}</div>
            <div class="stat-label">成功执行</div>
          </div>
          <div class="stat-sub">时间范围内</div>
        </div>
        <div class="stat-card gradient-red">
          <div class="stat-icon">❌</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.failTotal }}</div>
            <div class="stat-label">失败执行</div>
          </div>
          <div class="stat-sub">时间范围内</div>
        </div>
      </template>
      <!-- 性能测试模式 -->
      <template v-else>
        <div class="stat-card gradient-blue">
          <div class="stat-icon">🎯</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.sceneTotal }}</div>
            <div class="stat-label">场景总数</div>
          </div>
        </div>
        <div class="stat-card gradient-purple">
          <div class="stat-icon">⚡</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.execTotal }}</div>
            <div class="stat-label">执行次数</div>
          </div>
          <div class="stat-sub">时间范围内</div>
        </div>
        <div class="stat-card gradient-green">
          <div class="stat-icon">📈</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.avgQps }}</div>
            <div class="stat-label">平均 QPS</div>
          </div>
          <div class="stat-sub">时间范围内</div>
        </div>
        <div class="stat-card gradient-red">
          <div class="stat-icon">🚨</div>
          <div class="stat-info">
            <div class="stat-value">{{ displayStats.avgErrorRate }}%</div>
            <div class="stat-label">平均错误率</div>
          </div>
          <div class="stat-sub">时间范围内</div>
        </div>
      </template>
    </div>

    <!-- B1：资产/执行占比 + 待执行定时任务 -->
    <div class="analytics-grid">
      <div class="panel chart-panel">
        <div class="panel-header">
          <h3>📊 用例资产占比</h3>
        </div>
        <div v-show="caseProportion.length" ref="casePieRef" class="mini-chart"></div>
        <el-empty v-if="!caseProportion.length" description="暂无资产数据" :image-size="60" />
      </div>
      <div class="panel chart-panel">
        <div class="panel-header">
          <h3>📈 执行结果占比</h3>
          <span class="panel-sub">时间范围内</span>
        </div>
        <div v-show="executionProportion.length" ref="execPieRef" class="mini-chart"></div>
        <el-empty v-if="!executionProportion.length" description="暂无执行数据" :image-size="60" />
      </div>
      <div class="panel">
        <div class="panel-header">
          <h3>⏰ 待执行定时任务</h3>
          <span class="panel-sub">48 小时内</span>
        </div>
        <el-table :data="pendingCronJobs" size="small" :show-header="true" class="fancy-table">
          <el-table-column prop="name" label="任务" min-width="100" show-overflow-tooltip />
          <el-table-column prop="type" label="域" width="64">
            <template #default="{ row }">
              <el-tag size="small" :type="getExecTagType(row.type)">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="next_run_time" label="下次执行" width="140" />
        </el-table>
        <el-empty v-if="!pendingCronJobs.length" description="暂无待执行任务" :image-size="60" />
      </div>
    </div>

    <!-- AI 摘要条 -->
    <div class="ai-summary-bar" @click="router.push('/ai-test')">
      <div class="ai-summary-main">
        <span class="ai-summary-title">🤖 AI 工作台摘要</span>
        <span class="ai-summary-item">进行中任务 <strong>{{ aiSummary.running_jobs }}</strong></span>
        <span class="ai-summary-divider">|</span>
        <span class="ai-summary-item">近 7 日 AI 生成 <strong>{{ aiSummary.recent_generate_count }}</strong> 次</span>
        <span class="ai-summary-divider">|</span>
        <span class="ai-summary-item">需求用例生成 <strong>{{ aiSummary.recent_requirement_cases }}</strong> 次</span>
        <span class="ai-summary-divider">|</span>
        <span class="ai-summary-item">Runner 在线 <strong>{{ aiSummary.device_online }}</strong> / {{ aiSummary.device_total }}</span>
      </div>
      <el-button type="primary" link>进入 AI 工作台 →</el-button>
    </div>

    <!-- B3：Token 统计 + AI 生成趋势 + 活跃度排行 -->
    <div class="analytics-grid b3-grid">
      <div class="panel token-panel">
        <div class="panel-header">
          <h3>🪙 Token 消耗</h3>
          <span class="panel-sub">时间范围内 · AI 生成记录 + 需求任务</span>
        </div>
        <div class="token-stats">
          <div class="token-stat-main">
            <div class="token-value">{{ formatTokenCount(tokenStats.month_tokens_used) }}</div>
            <div class="token-label">总 Token</div>
          </div>
          <div class="token-stat-sub">
            <div class="token-sub-item">
              <span>生成记录</span>
              <strong>{{ tokenStats.month_generate_count }}</strong>
            </div>
            <div class="token-sub-item">
              <span>批量任务</span>
              <strong>{{ tokenStats.month_job_count }}</strong>
            </div>
            <div class="token-sub-item">
              <span>记录 Token</span>
              <strong>{{ formatTokenCount(tokenStats.month_record_tokens) }}</strong>
            </div>
            <div class="token-sub-item">
              <span>任务 Token</span>
              <strong>{{ formatTokenCount(tokenStats.month_job_tokens) }}</strong>
            </div>
          </div>
        </div>
      </div>
      <div class="panel chart-panel">
        <div class="panel-header">
          <h3>📉 AI 生成趋势</h3>
          <span class="panel-sub">近 {{ generateTrend.length || 7 }} 日</span>
        </div>
        <div v-show="generateTrend.length" ref="aiTrendRef" class="mini-chart"></div>
        <el-empty v-if="!generateTrend.length" description="暂无 AI 生成数据" :image-size="60" />
      </div>
      <div class="panel">
        <div class="panel-header">
          <h3>🏆 用户活跃度 Top 5</h3>
          <span class="panel-sub">时间范围内</span>
        </div>
        <el-table :data="userActivityTop" size="small" :show-header="true" class="fancy-table">
          <el-table-column type="index" width="45" />
          <el-table-column prop="username" label="用户" min-width="100" show-overflow-tooltip />
          <el-table-column prop="activity_score" label="活跃分" width="90" align="center">
            <template #default="{ row }">
              <span class="activity-score">{{ row.activity_score }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!userActivityTop.length" description="暂无活跃数据" :image-size="60" />
      </div>
    </div>

    <!-- B4：MCP 接入面板 -->
    <div class="mcp-section panel" v-loading="mcpLoading">
      <div class="panel-header">
        <h3>🔌 BrickCore MCP Server</h3>
        <div class="mcp-header-tags">
          <el-tag :type="mcpInfo.enabled ? 'success' : 'info'" size="small">
            {{ mcpInfo.enabled ? '已启用' : '未启用' }}
          </el-tag>
          <el-tag v-if="mcpInfo.tool_count" size="small" type="info">
            {{ mcpInfo.tool_count }} 个工具
          </el-tag>
        </div>
      </div>
      <div v-if="mcpInfo.enabled" class="mcp-body">
        <div class="mcp-row">
          <span class="mcp-label">接入地址</span>
          <code class="mcp-code">{{ mcpInfo.endpoint }}</code>
          <el-button size="small" @click="copyText(mcpInfo.endpoint)">复制</el-button>
        </div>
        <div class="mcp-row">
          <span class="mcp-label">认证方式</span>
          <span class="mcp-text">{{ mcpInfo.auth_hint }}</span>
        </div>
        <div class="mcp-row">
          <span class="mcp-label">客户端配置</span>
          <el-button size="small" type="primary" plain @click="copyMcpConfig">一键复制 JSON</el-button>
        </div>
        <div class="mcp-tools">
          <span class="mcp-label">工具分组</span>
          <div class="mcp-tool-tags">
            <el-tag v-for="g in mcpToolGroups" :key="g" size="small" effect="plain">{{ g }}</el-tag>
          </div>
        </div>
        <div class="mcp-danger">
          <span class="mcp-label">危险操作</span>
          <ul>
            <li v-for="d in mcpInfo.dangerous_ops || []" :key="d">{{ d }}</li>
          </ul>
        </div>
      </div>
      <el-empty v-else description="MCP Server 未启用，请设置环境变量 MCP_ENABLED=true" :image-size="60" />
    </div>

    <!-- 资源中心 -->
    <div class="resource-section">
      <div class="section-header">
        <h3>📎 资源中心</h3>
      </div>
      <div class="resource-grid">
        <div class="resource-card resource-card--docs" @click="goDocs()">
          <div class="resource-icon">📚</div>
          <div class="resource-body">
            <div class="resource-title">文档中心</div>
            <div class="resource-desc">快速开始、UI/API/AI 指南、部署说明</div>
          </div>
          <el-icon class="resource-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="resource-card resource-card--download" @click="goDocs('project-setup')">
          <div class="resource-icon">⚙️</div>
          <div class="resource-body">
            <div class="resource-title">入门配置</div>
            <div class="resource-desc">项目、环境、模块与通知配置说明</div>
          </div>
          <el-icon class="resource-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="resource-card resource-card--ai" @click="router.push('/ai-test')">
          <div class="resource-icon">🤖</div>
          <div class="resource-body">
            <div class="resource-title">AI 工作台</div>
            <div class="resource-desc">需求用例、生成任务、失败分析入口</div>
          </div>
          <el-icon class="resource-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="resource-card resource-card--device" @click="router.push('/device')">
          <div class="resource-icon">🖥️</div>
          <div class="resource-body">
            <div class="resource-title">执行器 / 设备</div>
            <div class="resource-desc">Runner 节点在线状态与设备管理</div>
          </div>
          <el-icon class="resource-arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="chart-section">
      <div class="section-header">
        <h3>执行趋势</h3>
        <div class="legend-hint">
          <span class="dot success"></span> 成功
          <span class="dot fail"></span> 失败
        </div>
      </div>
      <div ref="trendChartRef" class="trend-chart"></div>
    </div>

    <!-- 底部两栏 -->
    <div class="bottom-grid">
      <!-- Top 5 失败用例 / 失败场景 -->
      <div class="panel">
        <div class="panel-header">
          <h3>{{ activeTab === 'perf' ? '🔥 Top 5 错误场景' : '🔥 Top 5 失败用例' }}</h3>
          <span class="panel-sub">时间范围内</span>
        </div>
        <!-- Web/API 失败用例 -->
        <template v-if="activeTab !== 'perf'">
          <el-table :data="topFailedCases" size="default" :show-header="true" class="fancy-table">
            <el-table-column type="index" width="45" />
            <el-table-column prop="case_name" label="用例名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="type" label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'Web' ? 'primary' : 'success'">{{ row.type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="失败次数" width="90" align="center" sortable>
              <template #default="{ row }">
                <span class="fail-count">{{ row.count }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!topFailedCases.length" description="暂无失败用例" :image-size="80" />
        </template>
        <!-- 性能测试错误场景 -->
        <template v-else>
          <el-table :data="perfTopFailedScenes" size="default" :show-header="true" class="fancy-table">
            <el-table-column type="index" width="45" />
            <el-table-column prop="scene_name" label="场景名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="error_rate" label="错误率" width="90" align="center">
              <template #default="{ row }">
                <span class="fail-count">{{ row.error_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column prop="fail_count" label="失败请求" width="90" align="center" />
          </el-table>
          <el-empty v-if="!perfTopFailedScenes.length" description="暂无错误场景" :image-size="80" />
        </template>
      </div>

      <!-- 最近执行记录 -->
      <div class="panel">
        <div class="panel-header">
          <h3>🚀 最近 5 条执行记录</h3>
          <span class="panel-sub">平台最近执行动态</span>
        </div>
        <el-table
          :data="filteredRecentExecutions"
          size="default"
          :show-header="true"
          class="fancy-table clickable-table"
          @row-click="openExecutionReport"
        >
          <el-table-column type="index" width="45" />
          <el-table-column prop="name" label="执行名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="type" label="类型" width="70">
            <template #default="{ row }">
              <el-tag size="small" :type="getExecTagType(row.type)" effect="dark">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="run_by" label="执行人" width="80" />
          <el-table-column prop="start_time" label="执行时间" width="135" />
          <el-table-column label="指标" width="100" align="center">
            <template #default="{ row }">
              <template v-if="row.type === '性能'">
                <div class="perf-metric">QPS {{ row.qps || 0 }}</div>
                <div class="perf-metric-error" v-if="row.error_rate > 0">错误 {{ row.error_rate }}%</div>
              </template>
              <template v-else-if="row.pass_rate !== undefined">
                <span :class="row.pass_rate >= 100 ? 'pass-rate-ok' : 'pass-rate-warn'">
                  {{ row.pass_rate }}%
                </span>
              </template>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="getExecStatusType(row.status)">
                {{ formatExecStatus(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!filteredRecentExecutions.length" description="暂无执行记录" :image-size="80" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Refresh, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import http from '@/api/index'
import { mcpApi } from '@/api/modules/sys.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { copyToClipboard } from '@/utils/clipboard.js'

// 注册 echarts 组件
echarts.use([LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, CanvasRenderer])

const proStore = ProjectStore()
const router = useRouter()
const loading = ref(false)
const activeTab = ref('all')
const useProjectFilter = ref(true)
const trendChartRef = ref(null)
const casePieRef = ref(null)
const execPieRef = ref(null)
const aiTrendRef = ref(null)
let trendChart = null
let casePieChart = null
let execPieChart = null
let aiTrendChart = null

const dateRange = ref([])
const dateShortcuts = [
  {
    text: '近7天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 6)
      return [formatDate(start), formatDate(end)]
    }
  },
  {
    text: '近30天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 29)
      return [formatDate(start), formatDate(end)]
    }
  },
  {
    text: '本月',
    value: () => {
      const end = new Date()
      const start = new Date(end.getFullYear(), end.getMonth(), 1)
      return [formatDate(start), formatDate(end)]
    }
  }
]

function formatDate(d) {
  const date = new Date(d)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const goDocs = (docId = 'highlights') => {
  router.push({ path: '/docs', query: docId ? { doc: docId } : {} })
}

const formatTokenCount = (n) => {
  const v = Number(n) || 0
  if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`
  return String(v)
}

const fetchMcpInfo = async () => {
  mcpLoading.value = true
  try {
    const res = await mcpApi.getInfo()
    const data = res.data || res
    Object.assign(mcpInfo, data)
  } catch (e) {
    console.error(e)
  } finally {
    mcpLoading.value = false
  }
}

const copyText = async (text) => {
  const ok = await copyToClipboard(text)
  if (ok) {
    ElMessage.success('已复制到剪贴板')
  } else {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

const copyMcpConfig = async () => {
  const cfg = mcpInfo.client_config
  if (!cfg || typeof cfg !== 'object') {
    ElMessage.warning('客户端配置尚未加载，请刷新页面后重试')
    return
  }
  await copyText(JSON.stringify(cfg, null, 2))
}

// 默认近7天
const initDateRange = () => {
  const end = new Date()
  const start = new Date()
  start.setTime(start.getTime() - 3600 * 1000 * 24 * 6)
  dateRange.value = [formatDate(start), formatDate(end)]
}

const stats = reactive({
  ui_case_total: 0,
  ui_suite_total: 0,
  api_case_total: 0,
  api_suite_total: 0,
  perf_scene_total: 0,
  total_case: 0,
  total_suite: 0
})

const uiTrend = ref([])
const apiTrend = ref([])
const perfTrend = ref([])
const topFailedCases = ref([])
const perfTopFailedScenes = ref([])
const recentExecutions = ref([])
const caseProportion = ref([])
const executionProportion = ref([])
const pendingCronJobs = ref([])
const aiSummary = reactive({
  running_jobs: 0,
  recent_generate_count: 0,
  recent_requirement_cases: 0,
  device_online: 0,
  device_total: 0
})
const tokenStats = reactive({
  month_generate_count: 0,
  month_job_count: 0,
  month_tokens_used: 0,
  month_record_tokens: 0,
  month_job_tokens: 0
})
const generateTrend = ref([])
const userActivityTop = ref([])
const mcpLoading = ref(false)
const mcpInfo = reactive({
  enabled: false,
  endpoint: '',
  auth_hint: '',
  tool_count: 0,
  tool_groups: [],
  dangerous_ops: [],
  client_config: null,
})
const mcpToolGroups = computed(() => {
  const groups = mcpInfo.tool_groups
  if (Array.isArray(groups) && groups.length) return groups
  return ['项目上下文', '需求用例', '功能用例库', '接口与 UI 测试', '执行记录与压测', '测试执行', '失败分析']
})

const displayStats = computed(() => {
  if (activeTab.value === 'perf') {
    return {
      sceneTotal: stats.perf_scene_total,
      execTotal: stats.perf_exec_total,
      avgQps: stats.perf_avg_qps,
      avgErrorRate: stats.perf_avg_error_rate
    }
  }
  if (activeTab.value === 'ui') {
    const success = uiTrend.value.reduce((s, i) => s + i.success, 0)
    const fail = uiTrend.value.reduce((s, i) => s + i.fail, 0)
    return { caseTotal: stats.ui_case_total, suiteTotal: stats.ui_suite_total, successTotal: success, failTotal: fail }
  }
  if (activeTab.value === 'api') {
    const success = apiTrend.value.reduce((s, i) => s + i.success, 0)
    const fail = apiTrend.value.reduce((s, i) => s + i.fail, 0)
    return { caseTotal: stats.api_case_total, suiteTotal: stats.api_suite_total, successTotal: success, failTotal: fail }
  }
  // all
  const success = uiTrend.value.reduce((s, i) => s + i.success, 0) + apiTrend.value.reduce((s, i) => s + i.success, 0)
  const fail = uiTrend.value.reduce((s, i) => s + i.fail, 0) + apiTrend.value.reduce((s, i) => s + i.fail, 0)
  return { caseTotal: stats.total_case, suiteTotal: stats.total_suite, successTotal: success, failTotal: fail }
})

const filteredRecentExecutions = computed(() => {
  if (activeTab.value === 'perf') {
    return recentExecutions.value.filter(r => r.type === '性能')
  }
  if (activeTab.value === 'ui') {
    return recentExecutions.value.filter(r => r.type === 'Web')
  }
  if (activeTab.value === 'api') {
    return recentExecutions.value.filter(r => r.type === '接口')
  }
  return recentExecutions.value
})

const getExecTagType = (type) => {
  const map = { 'Web': 'primary', '接口': 'success', '性能': 'warning' }
  return map[type] || 'info'
}

const getExecStatusType = (status) => {
  const map = {
    '执行完成': 'success',
    'success': 'success',
    '执行中': 'warning',
    'running': 'warning',
    '失败': 'danger',
    'failed': 'danger',
    'stopped': 'info',
    'pending': 'info',
    '未执行': 'info'
  }
  return map[status] || 'info'
}

const openExecutionReport = (row) => {
  if (row?.report_path) {
    router.push(row.report_path)
    return
  }
  if (row?.type === 'Web' && row?.id) {
    router.push({ name: 'taskReport', params: { id: row.id } })
    return
  }
  if (row?.type === '接口' && row?.id) {
    router.push(`/api-module/report/${row.id}?type=suite`)
  }
}

const formatExecStatus = (status) => {
  const map = {
    'success': '成功',
    'failed': '失败',
    'running': '执行中',
    'pending': '等待',
    'stopped': '已停止',
    '执行完成': '成功',
    '执行中': '执行中',
    '等待执行': '等待',
    '失败': '失败'
  }
  return map[status] || status
}

const fetchData = async () => {
  loading.value = true
  try {
    const params = {
      start_date: dateRange.value?.[0],
      end_date: dateRange.value?.[1]
    }
    if (useProjectFilter.value && proStore.projectInfo?.id) {
      params.project_id = proStore.projectInfo.id
    }
    const res = await http.dashboardApi.getDashboard(params)
    const data = res.data || res
    Object.assign(stats, data.stats || {})
    uiTrend.value = data.ui_execution_trend || []
    apiTrend.value = data.api_execution_trend || []
    perfTrend.value = data.perf_execution_trend || []
    topFailedCases.value = data.top_failed_cases || []
    perfTopFailedScenes.value = data.perf_top_failed_scenes || []
    recentExecutions.value = data.recent_executions || []
    caseProportion.value = data.case_proportion || []
    executionProportion.value = data.execution_proportion || []
    pendingCronJobs.value = data.pending_cron_jobs || []
    Object.assign(aiSummary, data.ai_summary || {})
    Object.assign(tokenStats, data.token_stats || {})
    generateTrend.value = data.generate_trend || []
    userActivityTop.value = data.user_activity_top || []
    nextTick(() => {
      initChart()
      initPieCharts()
      initAiTrendChart()
    })
  } catch (err) {
    console.error(err)
    ElMessage.error('获取看板数据失败')
  } finally {
    loading.value = false
  }
}

const handleDateChange = () => {
  fetchData()
}

const initChart = () => {
  if (!trendChartRef.value) return
  if (trendChart) {
    trendChart.dispose()
  }
  trendChart = echarts.init(trendChartRef.value)

  const dates = (uiTrend.value.length ? uiTrend.value.map(i => i.date) : apiTrend.value.length ? apiTrend.value.map(i => i.date) : perfTrend.value.map(i => i.date)) || []

  let series = []
  if (activeTab.value === 'all' || activeTab.value === 'ui') {
    series.push(
      {
        name: 'Web 成功',
        type: 'line',
        smooth: true,
        data: uiTrend.value.map(i => i.success),
        itemStyle: { color: '#5470c6' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(84,112,198,0.4)' },
            { offset: 1, color: 'rgba(84,112,198,0.05)' }
          ])
        }
      },
      {
        name: 'Web 失败',
        type: 'line',
        smooth: true,
        data: uiTrend.value.map(i => i.fail),
        itemStyle: { color: '#ee6666' },
        lineStyle: { type: 'dashed' }
      }
    )
  }
  if (activeTab.value === 'all' || activeTab.value === 'api') {
    series.push(
      {
        name: '接口 成功',
        type: 'line',
        smooth: true,
        data: apiTrend.value.map(i => i.success),
        itemStyle: { color: '#91cc75' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(145,204,117,0.4)' },
            { offset: 1, color: 'rgba(145,204,117,0.05)' }
          ])
        }
      },
      {
        name: '接口 失败',
        type: 'line',
        smooth: true,
        data: apiTrend.value.map(i => i.fail),
        itemStyle: { color: '#fac858' },
        lineStyle: { type: 'dashed' }
      }
    )
  }
  if (activeTab.value === 'all' || activeTab.value === 'perf') {
    series.push(
      {
        name: '性能 成功',
        type: 'line',
        smooth: true,
        data: perfTrend.value.map(i => i.success),
        itemStyle: { color: '#73c0de' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(115,192,222,0.4)' },
            { offset: 1, color: 'rgba(115,192,222,0.05)' }
          ])
        }
      },
      {
        name: '性能 失败',
        type: 'line',
        smooth: true,
        data: perfTrend.value.map(i => i.fail),
        itemStyle: { color: '#fc8452' },
        lineStyle: { type: 'dashed' }
      }
    )
  }

  const option = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#eee',
      textStyle: { color: '#333' }
    },
    legend: {
      data: series.map(s => s.name),
      bottom: 0,
      icon: 'circle'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
      axisLine: { lineStyle: { color: '#ccc' } },
      axisLabel: { color: '#666' }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666' }
    },
    series
  }

  trendChart.setOption(option)
}

const buildPieOption = (title, data) => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, icon: 'circle', textStyle: { fontSize: 11 } },
  series: [{
    type: 'pie',
    radius: ['42%', '68%'],
    center: ['50%', '45%'],
    avoidLabelOverlap: true,
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    label: { show: false },
    data: data.map(i => ({ name: i.name, value: i.value, itemStyle: { color: i.color } }))
  }]
})

const initPieCharts = () => {
  if (casePieRef.value) {
    if (casePieChart) casePieChart.dispose()
    casePieChart = echarts.init(casePieRef.value)
    if (caseProportion.value.length) {
      casePieChart.setOption(buildPieOption('用例资产', caseProportion.value))
    }
  }
  if (execPieRef.value) {
    if (execPieChart) execPieChart.dispose()
    execPieChart = echarts.init(execPieRef.value)
    if (executionProportion.value.length) {
      execPieChart.setOption(buildPieOption('执行结果', executionProportion.value))
    }
  }
}

const initAiTrendChart = () => {
  if (!aiTrendRef.value || !generateTrend.value.length) return
  if (aiTrendChart) aiTrendChart.dispose()
  aiTrendChart = echarts.init(aiTrendRef.value)
  const dates = generateTrend.value.map(i => i.date.slice(5))
  aiTrendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, icon: 'circle', textStyle: { fontSize: 11 } },
    grid: { left: '3%', right: '4%', top: '8%', bottom: '18%', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#ccc' } },
      axisLabel: { color: '#666', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666', fontSize: 11 }
    },
    series: [
      {
        name: '总生成',
        type: 'line',
        smooth: true,
        data: generateTrend.value.map(i => i.total),
        itemStyle: { color: '#409eff' }
      },
      {
        name: '成功',
        type: 'line',
        smooth: true,
        data: generateTrend.value.map(i => i.success),
        itemStyle: { color: '#67c23a' }
      },
      {
        name: '失败',
        type: 'line',
        smooth: true,
        data: generateTrend.value.map(i => i.failed),
        itemStyle: { color: '#f56c6c' },
        lineStyle: { type: 'dashed' }
      }
    ]
  })
}

const onChartResize = () => {
  trendChart && trendChart.resize()
  casePieChart && casePieChart.resize()
  execPieChart && execPieChart.resize()
  aiTrendChart && aiTrendChart.resize()
}

watch([activeTab, useProjectFilter], () => {
  fetchData()
})

onMounted(() => {
  initDateRange()
  fetchData()
  fetchMcpInfo()
  window.addEventListener('resize', onChartResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onChartResize)
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
  if (casePieChart) {
    casePieChart.dispose()
    casePieChart = null
  }
  if (execPieChart) {
    execPieChart.dispose()
    execPieChart = null
  }
  if (aiTrendChart) {
    aiTrendChart.dispose()
    aiTrendChart = null
  }
})
</script>

<style scoped lang="scss">
.dashboard-page {
  padding: 20px;
  background: #f6f8fb;
  height: 100%;
  overflow-y: auto;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #1a2a6c, #b21f1f, #fdbb2d);
  background-size: 200% 200%;
  animation: gradientMove 8s ease infinite;
  padding: 24px 28px;
  border-radius: 16px;
  color: #fff;
  margin-bottom: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
}

@keyframes gradientMove {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 1px;
}
.page-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  opacity: 0.9;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255,255,255,0.15);
  padding: 4px 12px;
  border-radius: 20px;
}
.filter-label {
  font-size: 13px;
  color: #fff;
  opacity: 0.95;
}

.tab-group {
  :deep(.el-radio-button__inner) {
    background: rgba(255,255,255,0.15);
    border-color: rgba(255,255,255,0.25);
    color: #fff;
    font-weight: 500;
  }
  :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
    background: #fff;
    color: #333;
    box-shadow: none;
  }
}

:deep(.el-date-editor) {
  background: rgba(255,255,255,0.9);
  border-radius: 8px;
  border: none;
}

/* 统计卡片 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  position: relative;
  border-radius: 16px;
  padding: 22px 20px;
  color: #fff;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
  display: flex;
  align-items: center;
  gap: 14px;
  transition: transform 0.3s;
}
.stat-card:hover {
  transform: translateY(-4px);
}
.stat-card::after {
  content: '';
  position: absolute;
  top: -40%;
  right: -20%;
  width: 140px;
  height: 140px;
  background: rgba(255,255,255,0.12);
  border-radius: 50%;
}

.gradient-blue {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.gradient-purple {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}
.gradient-green {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}
.gradient-red {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.stat-icon {
  font-size: 32px;
  z-index: 1;
}
.stat-info {
  z-index: 1;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
}
.stat-label {
  font-size: 13px;
  opacity: 0.95;
  margin-top: 2px;
}
.stat-sub {
  position: absolute;
  right: 16px;
  bottom: 12px;
  font-size: 11px;
  opacity: 0.85;
  z-index: 1;
}

/* B1 分析区 */
.analytics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1.2fr;
  gap: 16px;
  margin-bottom: 16px;
}
.chart-panel {
  min-height: 280px;
}
.mini-chart {
  width: 100%;
  height: 220px;
}

.ai-summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: linear-gradient(90deg, #eef4ff 0%, #f6f0ff 100%);
  border: 1px solid #dce6ff;
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 20px;
  cursor: pointer;
  transition: box-shadow 0.2s ease;
}
.ai-summary-bar:hover {
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.12);
}
.ai-summary-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  font-size: 13px;
  color: #606266;
}
.ai-summary-title {
  font-weight: 600;
  color: #303133;
  margin-right: 4px;
}
.ai-summary-item strong {
  color: #409eff;
  font-size: 15px;
  margin-left: 4px;
}
.ai-summary-divider {
  color: #dcdfe6;
}

/* B3 */
.b3-grid {
  margin-bottom: 20px;
}
.token-panel {
  min-height: 280px;
}
.token-stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100% - 36px);
  justify-content: center;
}
.token-stat-main {
  text-align: center;
  padding: 12px 0 4px;
}
.token-value {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
  line-height: 1.2;
}
.token-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}
.token-stat-sub {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.token-sub-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: #f8f9fc;
  border-radius: 8px;
  font-size: 12px;
  color: #909399;
}
.token-sub-item strong {
  font-size: 16px;
  color: #303133;
}
.activity-score {
  color: #409eff;
  font-weight: 700;
}

/* B4 MCP */
.mcp-section {
  margin-bottom: 20px;
}
.mcp-header-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mcp-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mcp-row, .mcp-tools, .mcp-danger {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 13px;
}
.mcp-label {
  width: 88px;
  flex-shrink: 0;
  color: #909399;
  padding-top: 2px;
}
.mcp-code {
  flex: 1;
  background: #f5f7fa;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  word-break: break-all;
}
.mcp-text {
  color: #606266;
  line-height: 1.5;
}
.mcp-tool-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.mcp-danger ul {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.6;
}

/* 图表区 */
.chart-section {
  background: #fff;
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.04);
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #333;
}
.legend-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #666;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot.success { background: #52c41a; }
.dot.fail { background: #ff4d4f; }

.trend-chart {
  width: 100%;
  height: 340px;
}

/* 资源中心 */
.resource-section {
  background: #fff;
  border-radius: 16px;
  padding: 18px 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.04);
}
.resource-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.resource-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid #ebeef5;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #fafbfc;
}
.resource-card:hover {
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.12);
  transform: translateY(-1px);
}
.resource-icon { font-size: 28px; line-height: 1; flex-shrink: 0; }
.resource-body { flex: 1; min-width: 0; }
.resource-title { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 4px; }
.resource-desc { font-size: 12px; color: #909399; line-height: 1.4; }
.resource-arrow { color: #c0c4cc; flex-shrink: 0; }
.resource-card:hover .resource-arrow { color: #409eff; }

/* 底部面板 */
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.panel {
  background: #fff;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.04);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.panel-header h3 {
  margin: 0;
  font-size: 15px;
  color: #333;
}
.panel-sub {
  font-size: 12px;
  color: #999;
}

/* 表格 */
.clickable-table :deep(.el-table__row) {
  cursor: pointer;
}

.fancy-table {
  border-radius: 10px;
  overflow: hidden;
}
.fancy-table :deep(.el-table__header-wrapper th) {
  background: #f8f9fc;
  color: #555;
  font-weight: 600;
}
.fail-count {
  color: #ff4d4f;
  font-weight: 700;
}

/* 性能指标 */
.perf-metric {
  font-size: 11px;
  color: #666;
}
.perf-metric-error {
  font-size: 11px;
  color: #ff4d4f;
}
.pass-rate-ok {
  color: #52c41a;
  font-weight: 600;
}
.pass-rate-warn {
  color: #ff4d4f;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .analytics-grid {
    grid-template-columns: 1fr;
  }
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .resource-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .bottom-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .header-right {
    flex-wrap: wrap;
  }
}
</style>
