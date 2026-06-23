<template>
  <PageCard>
    <template #title>
      <div class="page-title">
        <span>🤖 AI 测试工作台</span>
        <el-button link type="primary" :loading="loading" @click="loadOverview" icon="Refresh">刷新</el-button>
      </div>
    </template>
    <template #main>
      <el-alert
        v-if="!projectId"
        type="warning"
        :closable="false"
        show-icon
        title="请先在顶部导航栏选择项目"
        style="margin-bottom: 16px;"
      />

      <p class="intro">
        集中入口：从需求文档到测试分析、功能用例，再到接口/UI 自动化。各能力在对应业务菜单中执行，此处提供快捷跳转与最近动态。
      </p>

      <!-- 进行中任务 -->
      <el-alert
        v-for="job in runningJobs"
        :key="job.id"
        type="info"
        :closable="false"
        show-icon
        class="job-alert"
      >
        <template #title>
          用例批量生成进行中 · {{ job.requirement_name || `需求 #${job.requirement_id}` }}
        </template>
        <div class="job-alert-body">
          <span>任务 #{{ job.id }} · {{ job.done_batches }}/{{ job.total_batches }} 批</span>
          <el-progress
            :percentage="job.progress_percent"
            :stroke-width="8"
            style="width: 200px; margin: 0 12px;"
          />
          <el-button type="primary" link size="small" @click="openRunningJob(job)">查看进度</el-button>
        </div>
      </el-alert>

      <!-- 统计 -->
      <el-row :gutter="16" class="stat-row">
        <el-col :xs="12" :sm="8" :md="4" v-for="s in statCards" :key="s.key">
          <div class="stat-card" :class="s.class" @click="goStat(s)">
            <div class="stat-value">{{ s.value }}</div>
            <div class="stat-label">{{ s.label }}</div>
          </div>
        </el-col>
      </el-row>

      <!-- B2：转化漏斗 + 待办提醒 -->
      <el-row :gutter="16" class="b2-row">
        <el-col :xs="24" :lg="14">
          <el-card shadow="never" class="panel-card" v-loading="loading">
            <template #header>
              <span class="card-header-title">转化漏斗</span>
            </template>
            <div v-if="funnel.length" class="funnel-wrap">
              <div ref="funnelChartRef" class="funnel-chart"></div>
              <div class="funnel-steps">
                <div
                  v-for="(item, idx) in funnel"
                  :key="item.key"
                  class="funnel-step"
                  :style="{ '--step-color': funnelColors[idx % funnelColors.length] }"
                >
                  <span class="funnel-step-idx">{{ idx + 1 }}</span>
                  <div class="funnel-step-body">
                    <div class="funnel-step-title">{{ item.stage }}</div>
                    <div class="funnel-step-meta">
                      <span class="funnel-step-count">{{ item.count }}</span>
                      <span
                        v-if="item.rate_from_prev != null && item.key !== 'requirement'"
                        class="funnel-step-rate"
                        :class="{ up: item.rate_from_prev > 0, down: item.rate_from_prev < 0 }"
                      >
                        较上步 {{ item.rate_from_prev > 0 ? '+' : '' }}{{ item.rate_from_prev }}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <el-empty v-if="!funnel.length" description="暂无漏斗数据" :image-size="64" />
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="10">
          <el-card shadow="never" class="panel-card" v-loading="loading">
            <template #header>
              <span class="card-header-title">待办提醒</span>
            </template>
            <div v-if="todos.length" class="todo-list">
              <div
                v-for="item in todos"
                :key="item.type"
                class="todo-item"
                :class="`todo-item--${item.level}`"
                @click="goTodo(item)"
              >
                <div class="todo-main">
                  <span class="todo-title">{{ item.title }}</span>
                  <el-tag :type="todoTagType(item.level)" size="small" effect="plain">{{ item.count }}</el-tag>
                </div>
                <div v-if="item.hint" class="todo-hint">{{ item.hint }}</div>
                <el-icon class="todo-arrow"><ArrowRight /></el-icon>
              </div>
            </div>
            <el-empty v-else description="暂无待办，继续保持" :image-size="64" />
          </el-card>
        </el-col>
      </el-row>

      <!-- B3：Token 统计 + 生成趋势 -->
      <el-row :gutter="16" class="token-row" v-if="projectId">
        <el-col :xs="24" :lg="8">
          <el-card shadow="never" class="panel-card" v-loading="loading">
            <template #header>
              <span class="card-header-title">本月 Token（当前项目）</span>
            </template>
            <div class="token-grid">
              <div class="token-item">
                <div class="token-value">{{ formatToken(tokenStats.month_tokens_used) }}</div>
                <div class="token-label">总消耗</div>
              </div>
              <div class="token-item">
                <div class="token-value">{{ tokenStats.month_generate_count ?? 0 }}</div>
                <div class="token-label">生成次数</div>
              </div>
              <div class="token-item">
                <div class="token-value">{{ tokenStats.month_job_count ?? 0 }}</div>
                <div class="token-label">批量任务</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="16">
          <el-card shadow="never" class="panel-card" v-loading="loading">
            <template #header>
              <span class="card-header-title">近 7 日生成趋势（当前项目）</span>
            </template>
            <div v-show="generateTrend.length" ref="trendChartRef" class="trend-chart"></div>
            <el-empty v-if="!generateTrend.length" description="暂无生成记录" :image-size="64" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 推荐流程 -->
      <el-card shadow="never" class="flow-card">
        <template #header>
          <span class="card-header-title">推荐流程</span>
        </template>
        <div class="flow-steps">
          <span class="flow-step clickable" @click="router.push('/ai-testing')">上传需求</span>
          <el-icon><ArrowRight /></el-icon>
          <span class="flow-step clickable" @click="router.push('/ai-testing')">测试分析</span>
          <el-icon><ArrowRight /></el-icon>
          <span class="flow-step">测试点 / 方案</span>
          <el-icon><ArrowRight /></el-icon>
          <span class="flow-step clickable" @click="router.push('/ai-functional-cases')">功能用例库</span>
          <el-icon><ArrowRight /></el-icon>
          <span class="flow-step muted">接口 / UI 自动化（可选）</span>
        </div>
      </el-card>

      <!-- 快捷入口 -->
      <div class="section-title">快捷入口</div>
      <el-row :gutter="16" class="entry-row">
        <el-col
          v-for="card in primaryEntries"
          :key="card.path + card.name"
          :xs="24"
          :sm="12"
          :md="6"
        >
          <div class="entry-card" :class="{ disabled: card.disabled }" @click="go(card)">
            <div class="entry-icon" :style="{ background: card.color }">
              <el-icon :size="26"><component :is="card.icon" /></el-icon>
            </div>
            <div class="entry-body">
              <div class="entry-name">{{ card.name }}</div>
              <div class="entry-desc">{{ card.desc }}</div>
            </div>
            <el-icon class="entry-arrow"><ArrowRight /></el-icon>
          </div>
        </el-col>
      </el-row>

      <div class="section-title">嵌入业务模块</div>
      <el-row :gutter="12" class="entry-row-secondary">
        <el-col v-for="card in secondaryEntries" :key="card.path" :xs="24" :sm="12">
          <el-card shadow="hover" class="secondary-card" @click="go(card)">
            <div class="secondary-inner">
              <el-icon :size="20" class="secondary-icon"><component :is="card.icon" /></el-icon>
              <div>
                <div class="secondary-name">{{ card.name }}</div>
                <div class="secondary-desc">{{ card.desc }}</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <!-- 最近需求 -->
        <el-col :xs="24" :lg="14">
          <el-card shadow="never" class="panel-card" v-loading="loading">
            <template #header>
              <div class="recent-header">
                <span class="card-header-title">最近需求</span>
                <el-button link type="primary" @click="router.push('/ai-testing')">查看全部</el-button>
              </div>
            </template>
            <el-table
              v-if="recentRequirements.length"
              :data="recentRequirements"
              stripe
              size="small"
              @row-click="row => openAnalysis(row)"
              class="clickable-table"
            >
              <el-table-column prop="name" label="需求名称" min-width="140" show-overflow-tooltip />
              <el-table-column prop="test_point_count" label="测试点" width="68" align="center" />
              <el-table-column prop="scheme_count" label="方案" width="56" align="center" />
              <el-table-column prop="case_count" label="用例" width="56" align="center" />
              <el-table-column label="操作" width="130" fixed="right" @click.stop>
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click.stop="openAnalysis(row)">分析</el-button>
                  <el-button link type="success" size="small" @click.stop="openCases(row)">用例</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无需求文档" :image-size="64">
              <el-button type="primary" @click="router.push('/ai-testing')">去上传</el-button>
            </el-empty>
          </el-card>
        </el-col>

        <!-- 最近 AI 生成 -->
        <el-col :xs="24" :lg="10">
          <el-card shadow="never" class="panel-card" v-loading="loading">
            <template #header>
              <span class="card-header-title">最近 AI 生成</span>
            </template>
            <el-table
              v-if="recentRecords.length"
              :data="recentRecords"
              stripe
              size="small"
              max-height="320"
              @row-click="openRecord"
              class="clickable-table"
            >
              <el-table-column prop="generate_type_label" label="类型" width="108" show-overflow-tooltip />
              <el-table-column label="摘要" min-width="100" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.summary || row.requirement_name || '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="72" align="center">
                <template #default="{ row }">
                  <el-tag :type="recordStatusType(row.status)" size="small">
                    {{ row.status_label }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="create_time" label="时间" width="100" show-overflow-tooltip />
            </el-table>
            <el-empty v-else description="暂无生成记录" :image-size="64" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 最近失败 · 快捷分析 -->
      <el-card v-if="recentFailures.length" shadow="never" class="panel-card failures-card" v-loading="loading">
        <template #header>
          <span class="card-header-title">最近失败 · AI 分析</span>
        </template>
        <el-table :data="recentFailures" stripe size="small" max-height="240">
          <el-table-column prop="case_name" label="用例" min-width="140" show-overflow-tooltip />
          <el-table-column label="类型" width="64" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.target_type === 'api' ? 'primary' : 'success'">
                {{ row.target_type === 'api' ? '接口' : 'UI' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error_msg" label="错误摘要" min-width="160" show-overflow-tooltip />
          <el-table-column prop="run_at" label="时间" width="100" show-overflow-tooltip />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="canAiTest && uStore.hasPermission('ai_test:execute')"
                link
                type="warning"
                size="small"
                @click="openFailureAnalyze(row)"
              >AI 分析</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 模型状态 -->
      <el-card shadow="never" class="config-hint-card">
        <template #header>
          <span class="card-header-title">模型配置</span>
        </template>
        <div v-if="configSummary?.default" class="config-lines">
          <div class="config-ok">
            <el-icon color="#67c23a"><CircleCheck /></el-icon>
            <span>
              默认模型：<b>{{ configSummary.default.name }}</b>（{{ configSummary.default.model }}）
            </span>
            <el-button link type="primary" @click="router.push('/ai-config')">管理</el-button>
          </div>
          <div v-if="configSummary.has_vision && configSummary.vision" class="config-ok sub">
            <el-icon color="#e6a23c"><View /></el-icon>
            <span>
              读图模型：<b>{{ configSummary.vision.name }}</b>（{{ configSummary.vision.model }}）
            </span>
          </div>
          <div v-else-if="!configSummary.has_vision" class="config-warn">
            <el-icon color="#e6a23c"><WarningFilled /></el-icon>
            <span>未检测到 Vision 类模型，含图需求建议配置 qwen-vl 等读图模型</span>
          </div>
          <div class="config-meta">已启用 {{ configSummary.enabled_count }} 个配置</div>
        </div>
        <el-alert
          v-else
          type="warning"
          :closable="false"
          show-icon
          title="未配置可用的 LLM，AI 生成将无法使用"
        >
          <el-button type="primary" size="small" @click="router.push('/ai-config')">去配置</el-button>
        </el-alert>
      </el-card>
    </template>
  </PageCard>

  <FailureAnalyzer
    v-model="failureAnalyzeVisible"
    :target-type="failureAnalyzeTarget.type"
    :target-id="failureAnalyzeTarget.id"
  />
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, FunnelChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  ArrowRight,
  CircleCheck,
  WarningFilled,
  View,
  Share,
  Document,
  Setting,
  Link,
  Mouse,
  Upload,
  ChatLineRound
} from '@element-plus/icons-vue'
import PageCard from '@/components/PageCard.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import { aiWorkbenchApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { useCommunityEdition } from '@/composables/useCommunityEdition.js'

echarts.use([BarChart, LineChart, FunnelChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const { isCommunityEdition, loadCommunityEdition } = useCommunityEdition()

const loading = ref(false)
const stats = ref({})
const configSummary = ref(null)
const recentRequirements = ref([])
const recentRecords = ref([])
const recentFailures = ref([])
const runningJobs = ref([])
const funnel = ref([])
const funnelColors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399']
const todos = ref([])
const tokenStats = ref({})
const generateTrend = ref([])
const funnelChartRef = ref(null)
const trendChartRef = ref(null)
let funnelChart = null
let trendChart = null

const failureAnalyzeVisible = ref(false)
const failureAnalyzeTarget = ref({ type: 'api', id: null })

const openFailureAnalyze = (row) => {
  failureAnalyzeTarget.value = { type: row.target_type, id: row.target_id }
  failureAnalyzeVisible.value = true
}

const projectId = computed(() => proStore.projectInfo?.id)

const canAiTest = computed(() => uStore.hasPermission('ai_test:view'))
const canAiConfig = computed(() => uStore.hasPermission('ai_config:view'))
const canApi = computed(() => uStore.hasPermission('api_manage:view') || uStore.hasPermission('api_case:view'))
const canUi = computed(() => uStore.hasPermission('ui_case:view'))

const statCards = computed(() => [
  {
    key: 'req',
    label: '需求文档',
    value: stats.value.requirement_total ?? 0,
    path: '/ai-testing',
    class: ''
  },
  {
    key: 'point',
    label: '测试点',
    value: stats.value.test_point_total ?? 0,
    path: '/ai-testing',
    class: 'stat-card--points'
  },
  {
    key: 'case',
    label: '工作区用例',
    value: stats.value.case_total ?? 0,
    path: '/ai-testing',
    class: 'stat-card--cases'
  },
  {
    key: 'scheme',
    label: '测试方案',
    value: stats.value.scheme_total ?? 0,
    path: '/ai-testing',
    class: 'stat-card--scheme'
  },
  {
    key: 'library',
    label: '功能用例库',
    value: stats.value.functional_case_total ?? 0,
    path: '/ai-functional-cases',
    class: 'stat-card--library'
  },
  {
    key: 'ui',
    label: '已转 UI',
    value: stats.value.ui_automated_count ?? 0,
    path: '/case',
    class: 'stat-card--ui',
    disabled: !canUi.value
  }
])

const primaryEntries = computed(() => [
  {
    name: '上传需求',
    desc: 'PDF / Word → 功能用例',
    path: '/ai-testing',
    icon: Upload,
    color: 'linear-gradient(135deg, #409eff 0%, #337ecc 100%)',
    disabled: !canAiTest.value
  },
  {
    name: '测试分析',
    desc: '测试点 · 方案 · 导图',
    path: '/ai-testing',
    icon: Share,
    color: 'linear-gradient(135deg, #67c23a 0%, #529b2e 100%)',
    disabled: !canAiTest.value
  },
  {
    name: '需求用例',
    desc: '编辑 · 导出禅道',
    path: '/ai-testing',
    icon: Document,
    color: 'linear-gradient(135deg, #e6a23c 0%, #cf9236 100%)',
    disabled: !canAiTest.value
  },
  {
    name: '模型配置',
    desc: 'LLM · Prompt',
    path: '/ai-config',
    icon: Setting,
    color: 'linear-gradient(135deg, #909399 0%, #73767a 100%)',
    disabled: !canAiConfig.value
  }
])

const secondaryEntries = computed(() => {
  const items = [
  {
    name: '接口 AI 生成',
    desc: '接口管理 / 用例 → AI 生成',
    path: '/api-module',
    icon: Link,
    disabled: !canApi.value
  },
  {
    name: 'UI AI / 录制',
    desc: '用例管理 → 新增 → AI',
    path: '/case',
    icon: Mouse,
    disabled: !canUi.value
  },
  {
    name: '功能用例库',
    desc: '入库 · 禅道 · 转 UI',
    path: '/ai-functional-cases',
    icon: Document,
    disabled: !canAiTest.value
  },
  {
    name: '问答准确性评测',
    desc: '标准集 · 被测 API · LLM 打分',
    path: '/ai-qa-eval',
    icon: ChatLineRound,
    disabled: !canAiTest.value
  }
  ]
  if (isCommunityEdition.value) {
    return items.filter((item) => item.path !== '/ai-qa-eval')
  }
  return items
})

const go = (card) => {
  if (card.disabled) return
  router.push(card.path)
}

const goStat = (s) => {
  if (s.disabled) return
  if (!canAiTest.value && s.path !== '/ai-config' && s.path !== '/case') return
  router.push(s.path)
}

const todoTagType = (level) => {
  if (level === 'danger') return 'danger'
  if (level === 'warning') return 'warning'
  return 'info'
}

const goTodo = (item) => {
  if (item.path) {
    router.push({ path: item.path, query: item.query || {} })
  }
}

const formatToken = (n) => {
  const v = Number(n) || 0
  if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`
  return String(v)
}

const initFunnelChart = () => {
  if (!funnelChartRef.value || !funnel.value.length) return
  if (funnelChart) funnelChart.dispose()
  funnelChart = echarts.init(funnelChartRef.value)
  const stageCount = funnel.value.length
  const data = funnel.value.map((i, idx) => ({
    name: i.stage,
    value: stageCount - idx,
    realValue: i.count,
    itemStyle: { color: funnelColors[idx % funnelColors.length] },
  }))
  funnelChart.setOption({
    color: funnelColors,
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const item = funnel.value[p.dataIndex]
        const lines = [`${p.name}`, `数量：${item?.count ?? 0}`]
        if (item?.rate_from_prev != null && item.key !== 'requirement') {
          lines.push(`较上一步：${item.rate_from_prev > 0 ? '+' : ''}${item.rate_from_prev}%`)
        }
        return lines.join('<br/>')
      },
    },
    series: [{
      type: 'funnel',
      left: '8%',
      top: 16,
      bottom: 16,
      width: '84%',
      min: 0,
      max: stageCount,
      sort: 'descending',
      gap: 8,
      label: { show: false },
      labelLine: { show: false },
      itemStyle: {
        borderColor: '#fff',
        borderWidth: 2,
      },
      emphasis: {
        label: { show: true, fontSize: 13, formatter: (p) => {
          const item = funnel.value[p.dataIndex]
          return item ? `${item.stage}\n${item.count}` : p.name
        }},
      },
      data,
    }],
  })
}

const initTrendChart = () => {
  if (!trendChartRef.value || !generateTrend.value.length) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value)
  const dates = generateTrend.value.map(i => i.date?.slice(5) || i.date)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['总生成', '成功', '失败'], bottom: 0 },
    grid: { left: '3%', right: '4%', top: '8%', bottom: '16%', containLabel: true },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '总生成', type: 'line', smooth: true, data: generateTrend.value.map(i => i.total) },
      { name: '成功', type: 'line', smooth: true, data: generateTrend.value.map(i => i.success) },
      { name: '失败', type: 'line', smooth: true, data: generateTrend.value.map(i => i.failed) },
    ]
  })
}

const openAnalysis = (row) => {
  router.push({ name: 'aiTestingWorkspace', params: { reqId: String(row.id) }, query: { tab: 'mindmap' } })
}

const openCases = (row) => {
  router.push({ name: 'aiTestingWorkspace', params: { reqId: String(row.id) }, query: { tab: 'cases' } })
}

const openRunningJob = (job) => {
  router.push({ path: '/ai-requirements', query: { reqId: String(job.requirement_id) } })
}

const recordStatusType = (status) => {
  if (status === 'imported' || status === 'accepted') return 'success'
  if (status === 'rejected') return 'danger'
  return 'info'
}

const openRecord = (row) => {
  const t = row.generate_type || ''
  const reqId = row.requirement_id
  if (t.startsWith('requirement_test') && reqId) {
    if (t === 'requirement_test_scheme') {
      router.push({ path: '/ai-test-analysis', query: { reqId: String(reqId) } })
    } else {
      openAnalysis({ id: reqId })
    }
    return
  }
  if (t === 'requirement_case' && reqId) {
    openCases({ id: reqId })
    return
  }
  if (t === 'api_case') {
    router.push('/api-case')
    return
  }
  if (t === 'ui_case') {
    router.push('/case')
  }
}

const loadOverview = async (silent = false) => {
  if (!projectId.value) {
    stats.value = {}
    configSummary.value = null
    recentRequirements.value = []
    recentRecords.value = []
    recentFailures.value = []
    runningJobs.value = []
    funnel.value = []
    todos.value = []
    tokenStats.value = {}
    generateTrend.value = []
    if (funnelChart) {
      funnelChart.dispose()
      funnelChart = null
    }
    if (trendChart) {
      trendChart.dispose()
      trendChart = null
    }
    return
  }
  if (!silent) loading.value = true
  try {
    const res = await aiWorkbenchApi.getOverview(projectId.value)
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      stats.value = d.stats || {}
      configSummary.value = d.config || null
      recentRequirements.value = d.recent_requirements || []
      recentRecords.value = d.recent_records || []
      recentFailures.value = d.recent_failures || []
      runningJobs.value = d.running_jobs || []
      funnel.value = d.funnel || []
      todos.value = d.todos || []
      tokenStats.value = d.token_stats || {}
      generateTrend.value = d.generate_trend || []
      nextTick(() => {
        initFunnelChart()
        initTrendChart()
      })
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

let pollTimer = null

const startPollIfNeeded = () => {
  if (pollTimer) clearInterval(pollTimer)
  if (!runningJobs.value.length) return
  pollTimer = setInterval(() => {
    if (projectId.value) loadOverview(true)
  }, 5000)
}

watch(projectId, () => {
  loadOverview()
})

watch(runningJobs, () => {
  startPollIfNeeded()
})

const handleFunnelResize = () => {
  if (funnelChart) funnelChart.resize()
  if (trendChart) trendChart.resize()
}

onMounted(() => {
  loadCommunityEdition()
  loadOverview()
  window.addEventListener('resize', handleFunnelResize)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (funnelChart) funnelChart.dispose()
  if (trendChart) trendChart.dispose()
  window.removeEventListener('resize', handleFunnelResize)
})
</script>

<style scoped>
.page-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 18px;
  font-weight: bold;
  width: 100%;
}
.intro {
  color: #606266;
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 16px;
}
.job-alert {
  margin-bottom: 12px;
}
.job-alert-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.stat-row {
  margin-bottom: 16px;
}
.b2-row {
  margin-bottom: 16px;
}
.funnel-wrap {
  display: flex;
  gap: 16px;
  align-items: stretch;
  min-height: 280px;
}
.funnel-chart {
  flex: 0 0 42%;
  min-width: 200px;
  height: 280px;
}
.funnel-steps {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  padding: 4px 0;
}
.funnel-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 8px;
  border-left: 3px solid var(--step-color, #409EFF);
}
.funnel-step-idx {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: var(--step-color, #409EFF);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.funnel-step-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}
.funnel-step-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}
.funnel-step-count {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.funnel-step-rate {
  color: #909399;
}
.funnel-step-rate.up {
  color: #67C23A;
}
.funnel-step-rate.down {
  color: #F56C6C;
}
@media (max-width: 992px) {
  .funnel-wrap {
    flex-direction: column;
  }
  .funnel-chart {
    flex: none;
    width: 100%;
    height: 240px;
  }
}
.token-row {
  margin-bottom: 16px;
}
.token-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.token-item {
  text-align: center;
  padding: 8px 4px;
  background: #f5f7fa;
  border-radius: 8px;
}
.token-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}
.token-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.trend-chart {
  width: 100%;
  height: 220px;
}
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.todo-item {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  cursor: pointer;
  position: relative;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.todo-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 10px;
}
.todo-hint {
  font-size: 12px;
  color: #909399;
  padding-right: 24px;
}
.todo-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
}
.todo-item:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
}
.todo-item--warning {
  background: #fdf6ec;
}
.todo-item--danger {
  background: #fef0f0;
}
.todo-item--info {
  background: #f4f4f5;
}
.todo-title {
  font-size: 14px;
  color: #303133;
}
.todo-arrow {
  color: #c0c4cc;
}
.stat-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.15s;
}
.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}
.stat-card--points {
  background: #f0f9eb;
}
.stat-card--cases {
  background: #fdf6ec;
}
.stat-card--scheme {
  background: #f4f4f5;
}
.stat-card--library {
  background: #ecf5ff;
}
.stat-card--ui {
  background: #fef0f0;
}
.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}
.failures-card {
  margin-bottom: 16px;
}
.flow-card,
.panel-card,
.config-hint-card {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
}
.card-header-title {
  font-weight: 600;
  font-size: 14px;
}
.flow-steps {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #303133;
}
.flow-step {
  padding: 4px 10px;
  background: #ecf5ff;
  border-radius: 4px;
}
.flow-step.clickable {
  cursor: pointer;
}
.flow-step.clickable:hover {
  background: #d9ecff;
}
.flow-step.muted {
  background: #f4f4f5;
  color: #909399;
  cursor: default;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 8px 0 12px;
}
.entry-row {
  margin-bottom: 8px;
}
.entry-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
  background: #fff;
}
.entry-card:hover:not(.disabled) {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.12);
}
.entry-card.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.entry-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.entry-body {
  flex: 1;
  min-width: 0;
}
.entry-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.entry-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.entry-arrow {
  color: #c0c4cc;
  flex-shrink: 0;
}
.entry-row-secondary {
  margin-bottom: 20px;
}
.secondary-card {
  cursor: pointer;
  margin-bottom: 12px;
}
.secondary-card :deep(.el-card__body) {
  padding: 12px 16px;
}
.secondary-inner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.secondary-icon {
  color: var(--el-color-primary);
  margin-top: 2px;
}
.secondary-name {
  font-size: 14px;
  font-weight: 500;
}
.secondary-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.recent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.clickable-table :deep(.el-table__row) {
  cursor: pointer;
}
.config-lines {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.config-ok {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
}
.config-ok.sub {
  padding-left: 4px;
  font-size: 13px;
}
.config-warn {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #e6a23c;
}
.config-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
