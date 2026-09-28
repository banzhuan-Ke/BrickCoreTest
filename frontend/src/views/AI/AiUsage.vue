<template>
  <PageCard>
    <template #title>
      <b>📊 模型使用情况</b>
    </template>
    <template #main>
      <div class="usage-summary" v-loading="usageSummaryLoading">
        <el-row :gutter="12">
          <el-col :xs="12" :sm="6">
            <div class="usage-stat-card">
              <div class="stat-label">今日 Tokens</div>
              <div class="stat-value">{{ formatTokenNum(usageSummary.today?.tokens_used) }}</div>
              <div class="stat-sub">调用 {{ usageSummary.today?.calls ?? 0 }} 次</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="usage-stat-card">
              <div class="stat-label">近 {{ usageFilter.days }} 日 Tokens</div>
              <div class="stat-value">{{ formatTokenNum(usageSummary.period?.tokens_used) }}</div>
              <div class="stat-sub">调用 {{ usageSummary.period?.calls ?? 0 }} 次</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="usage-stat-card">
              <div class="stat-label">近 {{ usageFilter.days }} 日失败</div>
              <div class="stat-value danger">{{ usageSummary.period?.failed_calls ?? 0 }}</div>
              <div class="stat-sub">次调用失败</div>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="usage-stat-card">
              <div class="stat-label">成功率</div>
              <div class="stat-value">{{ successRate }}%</div>
              <div class="stat-sub">近 {{ usageFilter.days }} 日统计</div>
            </div>
          </el-col>
        </el-row>
      </div>

      <el-row :gutter="16" class="chart-row" v-loading="chartLoading">
        <el-col :xs="24" :lg="10">
          <el-card shadow="never" class="chart-card">
            <template #header><span class="chart-title">场景 Token 占比</span></template>
            <div v-show="sceneChartData.length" ref="sceneChartRef" class="usage-chart"></div>
            <el-empty v-if="!sceneChartData.length" description="暂无场景数据" :image-size="64" />
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="14">
          <el-card shadow="never" class="chart-card">
            <template #header><span class="chart-title">近 {{ usageFilter.days }} 日调用趋势</span></template>
            <div v-show="trendItems.length" ref="trendChartRef" class="usage-chart"></div>
            <el-empty v-if="!trendItems.length" description="暂无趋势数据" :image-size="64" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" class="chart-row" v-loading="usageSummaryLoading">
        <el-col :xs="24" :lg="14">
          <el-card shadow="never" class="chart-card">
            <template #header>
              <span class="chart-title">按技能拆分（近 {{ usageFilter.days }} 日）</span>
            </template>
            <el-table
              v-if="bySkill.length"
              :data="bySkill"
              size="small"
              stripe
              border
              max-height="260"
            >
              <el-table-column label="技能" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  <span :title="row.skill_code">{{ row.skill_name || row.skill_code }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="call_count" label="调用" width="90" align="right" />
              <el-table-column label="Tokens" width="120" align="right">
                <template #default="{ row }">{{ formatTokenNum(row.tokens_used) }}</template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无技能调用" :image-size="64" />
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="10">
          <el-card shadow="never" class="chart-card">
            <template #header>
              <span class="chart-title">小测多轮分布（近 {{ usageFilter.days }} 日）</span>
            </template>
            <el-table
              v-if="byRounds.length"
              :data="byRounds"
              size="small"
              stripe
              border
              max-height="260"
            >
              <el-table-column prop="label" label="轮次桶" min-width="100" />
              <el-table-column prop="calls" label="回合数" width="100" align="right" />
            </el-table>
            <el-empty
              v-else
              description="暂无回合追踪（含小测对话与技能快捷入口；历史未计入的直跑入口除外）"
              :image-size="64"
            />
          </el-card>
        </el-col>
      </el-row>

      <div class="usage-toolbar">
        <el-select v-model="usageFilter.days" style="width: 120px;" @change="onUsageDaysChange">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="近 90 天" :value="90" />
        </el-select>
        <el-select
          v-model="usageFilter.scene"
          clearable
          placeholder="场景"
          style="width: 180px;"
          @change="loadUsageLogs"
        >
          <el-option v-for="s in usageScenes" :key="s.scene" :label="s.label" :value="s.scene" />
        </el-select>
        <el-input
          v-model="usageFilter.username"
          clearable
          placeholder="用户名"
          style="width: 140px;"
          @clear="loadUsageLogs"
          @keyup.enter="loadUsageLogs"
        />
        <el-select
          v-model="usageFilter.status"
          clearable
          placeholder="状态"
          style="width: 120px;"
          @change="loadUsageLogs"
        >
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button type="primary" icon="Search" @click="loadUsageLogs">查询</el-button>
        <el-button icon="Download" :loading="usageExporting" @click="exportUsageCsv">导出 CSV</el-button>
        <el-button link type="primary" @click="$router.push({ path: '/platform-config', query: { tab: 'ai' } })">平台配置 → AI 模型</el-button>
      </div>

      <el-table :data="usageList" stripe border v-loading="usageLoading" style="width: 100%;">
        <el-table-column prop="create_time" label="时间" width="160" />
        <el-table-column prop="scene_label" label="场景" width="140" show-overflow-tooltip />
        <el-table-column label="用户" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.username_display || row.username || '—' }}</template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.project_name || (row.project_id ? `#${row.project_id}` : '—') }}</template>
        </el-table-column>
        <el-table-column prop="model" label="模型" min-width="140" show-overflow-tooltip />
        <el-table-column label="路径" min-width="170">
          <template #default="{ row }">
            <div class="usage-path" :title="(row.path_tools || []).join('、')">
              <el-tag v-if="row.path_kind && row.path_kind !== 'other'" size="small" :type="pathTagType(row.path_kind)">
                {{ pathKindLabel(row.path_kind) }}
              </el-tag>
              <span v-if="row.path_label" class="usage-path-text">{{ pathShortLabel(row) }}</span>
              <span v-else class="usage-path-empty">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="tokens_used" label="Tokens" width="90" align="right" />
        <el-table-column label="耗时" width="90" align="right">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="输入摘要" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.input_summary }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openUsageDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="usage-pagination">
        <el-pagination
          v-model:current-page="usagePage.page"
          v-model:page-size="usagePage.size"
          :total="usagePage.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadUsageLogs"
          @size-change="loadUsageLogs"
        />
      </div>

      <el-dialog v-model="usageDetailVisible" title="模型使用详情" width="640px" destroy-on-close>
        <el-descriptions v-if="usageDetail" :column="2" border size="small">
          <el-descriptions-item label="时间">{{ usageDetail.create_time }}</el-descriptions-item>
          <el-descriptions-item label="场景">{{ usageDetail.scene_label }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ usageDetail.username_display || usageDetail.username || '—' }}</el-descriptions-item>
          <el-descriptions-item label="项目">{{ usageDetail.project_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ usageDetail.model }}</el-descriptions-item>
          <el-descriptions-item label="供应商">{{ providerMap[usageDetail.provider] || usageDetail.provider }}</el-descriptions-item>
          <el-descriptions-item label="Tokens">{{ usageDetail.tokens_used }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(usageDetail.duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="状态" :span="2">
            <el-tag :type="usageDetail.status === 'success' ? 'success' : 'danger'" size="small">
              {{ usageDetail.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="usageDetail.path_label" label="路径" :span="2">
            {{ pathDetailLabel(usageDetail) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="usageDetail.path_mode" label="小测模式">
            {{ assistModeLabel(usageDetail.path_mode) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="usageDetail.path_skills?.length" label="Skill" :span="2">
            <el-tag v-for="s in usageDetail.path_skills" :key="s" type="warning" size="small" style="margin-right: 4px;">{{ s }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="detailTools(usageDetail).length" label="工具" :span="2">
            <el-tag v-for="t in detailTools(usageDetail)" :key="t" size="small" style="margin-right: 4px;">{{ t }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="输入" :span="2">
            <div class="usage-detail-text">{{ usageDetail.input_summary }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="输出" :span="2">
            <div class="usage-detail-text">{{ usageDetail.output_summary || '—' }}</div>
          </el-descriptions-item>
        </el-descriptions>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { PieChart, LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageCard from '@/components/PageCard.vue'
import { aiConfigApi } from '@/api/modules/ai'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

echarts.use([PieChart, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const proStore = ProjectStore()

const providerMap = {
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  claude: 'Claude',
  custom: '自定义'
}

const usageList = ref([])
const usageScenes = ref([])
const usageLoading = ref(false)
const usageSummaryLoading = ref(false)
const chartLoading = ref(false)
const usageExporting = ref(false)
const usageSummary = ref({
  today: { calls: 0, tokens_used: 0 },
  period: { calls: 0, tokens_used: 0, failed_calls: 0 },
  top_scenes: [],
  by_skill: [],
  by_rounds: []
})
const trendItems = ref([])
const usageFilter = reactive({
  scene: '',
  username: '',
  status: '',
  days: 7
})
const usagePage = reactive({
  page: 1,
  size: 20,
  total: 0
})
const usageDetailVisible = ref(false)
const usageDetail = ref(null)

const sceneChartRef = ref(null)
const trendChartRef = ref(null)
let sceneChart = null
let trendChart = null

const sceneChartData = computed(() => usageSummary.value.top_scenes || [])
const bySkill = computed(() => usageSummary.value.by_skill || [])
const byRounds = computed(() => usageSummary.value.by_rounds || [])

const successRate = computed(() => {
  const calls = Number(usageSummary.value.period?.calls || 0)
  const failed = Number(usageSummary.value.period?.failed_calls || 0)
  if (!calls) return '100.0'
  return (((calls - failed) / calls) * 100).toFixed(1)
})

const ASSIST_MODE_LABELS = {
  lite: '精简',
  standard: '标准'
}

const pathKindLabel = (kind) => {
  if (kind === 'agent') return 'Agent'
  if (kind === 'skill') return 'Skill'
  if (kind === 'confirm') return '确认'
  if (kind === 'tool') return '工具'
  return ''
}

const pathTagType = (kind) => {
  if (kind === 'skill') return 'warning'
  if (kind === 'confirm') return 'success'
  if (kind === 'tool') return 'info'
  return ''
}

const assistModeLabel = (mode) => {
  const key = String(mode || '').trim().toLowerCase()
  return ASSIST_MODE_LABELS[key] || mode || ''
}

const pathShortLabel = (row) => {
  const label = row.path_label || ''
  return label
    .replace(/^小测 Agent(?: · )?/, '')
    .replace(/^Skill · /, '')
    .replace(/^确认执行 · /, '')
    .replace(/^工具 · /, '')
    .replace(/\bstandard\b/gi, '标准')
    .replace(/\blite\b/gi, '精简')
}

const pathDetailLabel = (row) => {
  const label = row?.path_label || ''
  return label
    .replace(/\bstandard\b/gi, '标准')
    .replace(/\blite\b/gi, '精简')
}

const detailTools = (row) => {
  if (row?.path_tools?.length) return row.path_tools
  const extra = row?.extra || {}
  const tools = extra.tools_used || extra.tools || []
  return Array.isArray(tools) ? tools : []
}

const formatDuration = (ms) => {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const formatTokenNum = (n) => {
  const v = Number(n || 0)
  if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`
  return String(v)
}

const initSceneChart = () => {
  if (!sceneChartRef.value || !sceneChartData.value.length) return
  if (sceneChart) sceneChart.dispose()
  sceneChart = echarts.init(sceneChartRef.value)
  sceneChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}<br/>Tokens：${formatTokenNum(p.value)} (${p.percent}%)`
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 0,
      top: 'middle',
      textStyle: { fontSize: 11 }
    },
    series: [{
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['38%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      data: sceneChartData.value.map(s => ({
        name: s.scene_label,
        value: s.tokens_used || 0
      }))
    }]
  })
}

const initTrendChart = () => {
  if (!trendChartRef.value || !trendItems.value.length) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value)
  const dates = trendItems.value.map(i => (i.date || '').slice(5))
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['Tokens', '调用次数', '失败'], bottom: 0 },
    grid: { left: '3%', right: '4%', top: '10%', bottom: '18%', containLabel: true },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
    yAxis: [
      { type: 'value', name: 'Tokens', position: 'left' },
      { type: 'value', name: '次数', position: 'right', minInterval: 1 }
    ],
    series: [
      {
        name: 'Tokens',
        type: 'line',
        smooth: true,
        yAxisIndex: 0,
        areaStyle: { opacity: 0.12 },
        data: trendItems.value.map(i => i.tokens_used)
      },
      {
        name: '调用次数',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 18,
        data: trendItems.value.map(i => i.calls)
      },
      {
        name: '失败',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        lineStyle: { type: 'dashed' },
        data: trendItems.value.map(i => i.failed_calls)
      }
    ]
  })
}

const refreshCharts = async () => {
  await nextTick()
  initSceneChart()
  initTrendChart()
}

const loadUsageSummary = async () => {
  usageSummaryLoading.value = true
  try {
    const res = await aiConfigApi.getUsageSummary({
      project_id: proStore.projectInfo?.id || undefined,
      days: usageFilter.days
    })
    if (res.data?.code === 200) {
      usageSummary.value = res.data.data || usageSummary.value
      await refreshCharts()
    }
  } catch (e) {
    console.error(e)
  } finally {
    usageSummaryLoading.value = false
  }
}

const loadUsageTrend = async () => {
  chartLoading.value = true
  try {
    const res = await aiConfigApi.getUsageTrend({
      project_id: proStore.projectInfo?.id || undefined,
      days: usageFilter.days
    })
    if (res.data?.code === 200) {
      trendItems.value = res.data.data?.items || []
      await refreshCharts()
    }
  } catch (e) {
    console.error(e)
  } finally {
    chartLoading.value = false
  }
}

const onUsageDaysChange = () => {
  usagePage.page = 1
  loadUsageSummary()
  loadUsageTrend()
  loadUsageLogs()
}

const loadUsageLogs = async () => {
  usageLoading.value = true
  try {
    const params = {
      page: usagePage.page,
      size: usagePage.size,
      project_id: proStore.projectInfo?.id || undefined,
      scene: usageFilter.scene || undefined,
      username: usageFilter.username || undefined,
      status: usageFilter.status || undefined,
      days: usageFilter.days
    }
    const res = await aiConfigApi.getUsageLogs(params)
    if (res.data?.code === 200) {
      usageList.value = res.data.data?.list || []
      usagePage.total = res.data.data?.total || 0
      usageScenes.value = res.data.data?.scenes || []
    }
  } catch (e) {
    console.error(e)
  } finally {
    usageLoading.value = false
  }
}

const exportUsageCsv = async () => {
  usageExporting.value = true
  try {
    const res = await aiConfigApi.exportUsageLogs({
      project_id: proStore.projectInfo?.id || undefined,
      scene: usageFilter.scene || undefined,
      username: usageFilter.username || undefined,
      status: usageFilter.status || undefined,
      days: usageFilter.days
    })
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ai_usage_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
    console.error(e)
  } finally {
    usageExporting.value = false
  }
}

const openUsageDetail = (row) => {
  usageDetail.value = row
  usageDetailVisible.value = true
}

const handleResize = () => {
  sceneChart?.resize()
  trendChart?.resize()
}

onMounted(() => {
  loadUsageSummary()
  loadUsageTrend()
  loadUsageLogs()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  sceneChart?.dispose()
  trendChart?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.usage-summary {
  margin-bottom: 16px;
}
.usage-stat-card {
  background: linear-gradient(135deg, #f5f7fa 0%, #eef2f7 100%);
  border-radius: 10px;
  padding: 14px 16px;
  min-height: 92px;
  margin-bottom: 12px;
}
.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}
.stat-value.danger {
  color: #f56c6c;
}
.stat-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.chart-row {
  margin-bottom: 16px;
}
.chart-card {
  margin-bottom: 12px;
}
.chart-title {
  font-weight: 500;
}
.usage-chart {
  width: 100%;
  height: 280px;
}
.usage-path {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.usage-path-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
  font-size: 12px;
}
.usage-path-empty {
  color: #c0c4cc;
}
.usage-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}
.usage-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.usage-detail-text {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  font-size: 13px;
}
</style>
