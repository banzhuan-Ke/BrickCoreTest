<template>
  <PageCard>
    <template #title>
      <b>执行可信度</b>
    </template>
    <template #main>
      <el-collapse v-model="helpOpen" class="stab-help">
        <el-collapse-item name="help">
          <template #title>
            <span class="stab-help-title">使用说明</span>
            <span class="stab-help-sub">口径 / 隔离 / 不稳定判定</span>
          </template>
          <ul class="stab-help-list">
            <li>
              <b>近况通过率</b>：最近 {{ recentK }} 次终态成功占比，反映「现在稳不稳」。条数可在项目设置「执行可信度」调整。
            </li>
            <li>
              <b>窗口通过率</b>：项目配置的最近 N 次（当前 N={{ windowN || '—' }}），用于不稳定判定与主排序。
            </li>
            <li>
              <b>历史通过率</b>：最多回溯约 100 次有效样本，用于对比「以前 vs 现在」。
            </li>
            <li>
              <b>首跑通过率</b>：接口可区分重试；Web/App 无 attempt 时显示 —，不会用终态冒充。
            </li>
            <li>
              <b>隔离</b>：打标后计划/套件/定时默认跳过，且不进通过率分母；单条调试仍可跑。
            </li>
            <li>
              <b>不稳定</b>：窗口通过率过低、首跑偏低、重试挽回偏多，或成败切换过多（时好时坏）；阈值在项目设置可调。
            </li>
          </ul>
        </el-collapse-item>
      </el-collapse>

      <div class="stab-overview" v-loading="loading">
        <div class="stab-stat">
          <div class="stab-stat-label">{{ overviewLabel }}用例</div>
          <div class="stab-stat-value">{{ overview.case_count || 0 }}</div>
          <div class="stab-stat-hint">有样本 {{ overview.with_runs || 0 }}</div>
        </div>
        <div class="stab-stat warn">
          <div class="stab-stat-label">不稳定</div>
          <div class="stab-stat-value">{{ overview.unstable || 0 }}</div>
        </div>
        <div class="stab-stat info">
          <div class="stab-stat-label">已隔离</div>
          <div class="stab-stat-value">{{ overview.quarantined || 0 }}</div>
        </div>
        <div class="stab-stat ok">
          <div class="stab-stat-label">平均窗口通过率</div>
          <div class="stab-stat-value">{{ pct(overview.avg_pass_rate) }}</div>
        </div>
        <div class="stab-chart-wrap">
          <div ref="bandChartRef" class="stab-chart"></div>
        </div>
      </div>

      <div class="stab-toolbar">
        <el-radio-group v-model="domain" @change="onDomainChange">
          <el-radio-button value="api">接口</el-radio-button>
          <el-radio-button value="ui">Web UI</el-radio-button>
          <el-radio-button value="app">App</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="keyword"
          clearable
          placeholder="用例名称"
          style="width: 200px"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-checkbox v-model="hasRunsOnly" @change="onFilterChange">仅有样本</el-checkbox>
        <el-checkbox v-model="unstableOnly" @change="onFilterChange">仅不稳定</el-checkbox>
        <el-checkbox v-model="quarantineOnly" @change="onFilterChange">仅已隔离</el-checkbox>
        <el-button type="primary" icon="Search" @click="onSearch">查询</el-button>
      </div>

      <el-table
        :data="items"
        stripe
        v-loading="loading"
        class="stab-table"
        :default-sort="tableSort"
        @sort-change="onSortChange"
      >
        <el-table-column
          prop="case_name"
          label="用例"
          min-width="200"
          show-overflow-tooltip
          sortable="custom"
        />
        <el-table-column label="标记" width="150">
          <template #default="{ row }">
            <CaseStabilityBadges :quarantine="row.quarantine" :unstable="row.unstable" />
          </template>
        </el-table-column>
        <el-table-column
          prop="recent_pass_rate"
          label="近况通过率"
          width="120"
          sortable="custom"
        >
          <template #header>
            <el-tooltip content="最近若干次终态成功占比，看当下趋势" placement="top">
              <span>近况通过率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="rateClass(row.recent_pass_rate)">{{ pct(row.recent_pass_rate) }}</span>
            <span v-if="row.recent_n" class="n-hint">n={{ row.recent_n }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="pass_rate"
          label="窗口通过率"
          width="120"
          sortable="custom"
        >
          <template #header>
            <el-tooltip :content="`最近 N=${windowN || '—'} 次终态成功占比`" placement="top">
              <span>窗口通过率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="rateClass(row.pass_rate)">{{ pct(row.pass_rate) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="overall_pass_rate"
          label="历史通过率"
          width="120"
          sortable="custom"
        >
          <template #header>
            <el-tooltip content="更长回溯窗口内的终态成功占比（最多约 100 次）" placement="top">
              <span>历史通过率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="rateClass(row.overall_pass_rate)">{{ pct(row.overall_pass_rate) }}</span>
            <span v-if="row.overall_n" class="n-hint">n={{ row.overall_n }}</span>
          </template>
        </el-table-column>
        <el-table-column label="首跑通过率" width="110">
          <template #default="{ row }">
            {{ row.first_pass_rate == null ? '—' : pct(row.first_pass_rate) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="retry_salvage_count"
          label="重试挽回"
          width="100"
          sortable="custom"
        />
        <el-table-column prop="n" label="窗口N" width="90" sortable="custom" />
        <el-table-column label="最近失败桶" width="140">
          <template #default="{ row }">{{ row.last_failure_bucket_label || '—' }}</template>
        </el-table-column>
        <el-table-column
          prop="last_run_at"
          label="最近执行"
          width="160"
          sortable="custom"
        />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="canEdit"
              size="small"
              :type="row.quarantine ? 'success' : 'warning'"
              plain
              @click="toggleQuarantine(row)"
            >
              {{ row.quarantine ? '解除隔离' : '隔离' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <template #bottom>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadList"
        @size-change="onSizeChange"
      />
    </template>
  </PageCard>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageCard from '@/components/PageCard.vue'
import CaseStabilityBadges from '@/components/CaseStabilityBadges.vue'
import { stabilityApi } from '@/api/modules/stability.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

echarts.use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer])

const proStore = ProjectStore()
const userStore = UserStore()
const domain = ref('api')
const keyword = ref('')
const unstableOnly = ref(false)
const quarantineOnly = ref(false)
const hasRunsOnly = ref(true)
const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const windowN = ref(0)
const recentK = ref(5)
const overview = ref({
  case_count: 0,
  with_runs: 0,
  unstable: 0,
  quarantined: 0,
  avg_pass_rate: null,
  pass_bands: { high: 0, mid: 0, low: 0, none: 0 },
})
const overviewScope = ref('page')
const helpOpen = ref([])
const sortBy = ref('recent_pass_rate')
const sortOrder = ref('asc')
const bandChartRef = ref(null)
let bandChart = null

const tableSort = computed(() => ({
  prop: sortBy.value || undefined,
  order: sortOrder.value === 'asc' ? 'ascending' : sortOrder.value === 'desc' ? 'descending' : undefined,
}))

const overviewLabel = computed(() => (overviewScope.value === 'filtered' ? '筛选' : '本页'))

const canEdit = computed(() => {
  const map = { api: 'api_case:edit', ui: 'ui_case:edit', app: 'app_case:edit' }
  return userStore.hasPermission(map[domain.value])
})

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(1)}%`
}

function rateClass(v) {
  if (v == null) return ''
  const n = Number(v)
  if (n >= 0.85) return 'rate-high'
  if (n >= 0.5) return 'rate-mid'
  return 'rate-low'
}

function onDomainChange() {
  page.value = 1
  loadList()
}

function onFilterChange() {
  page.value = 1
  loadList()
}

function onSearch() {
  page.value = 1
  loadList()
}

function onSizeChange() {
  page.value = 1
  loadList()
}

function onSortChange({ prop, order }) {
  if (!order || !prop) {
    sortBy.value = ''
    sortOrder.value = 'desc'
  } else {
    sortBy.value = prop
    sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  }
  page.value = 1
  loadList()
}

function renderBandChart() {
  if (!bandChartRef.value) return
  if (!bandChart) {
    bandChart = echarts.init(bandChartRef.value)
  }
  const bands = overview.value.pass_bands || {}
  const data = [
    { name: '≥85%', value: bands.high || 0, itemStyle: { color: '#67c23a' } },
    { name: '50–85%', value: bands.mid || 0, itemStyle: { color: '#e6a23c' } },
    { name: '<50%', value: bands.low || 0, itemStyle: { color: '#f56c6c' } },
    { name: '无样本', value: bands.none || 0, itemStyle: { color: '#c0c4cc' } },
  ].filter((d) => d.value > 0)
  bandChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        label: { show: false },
        data: data.length ? data : [{ name: '暂无', value: 1, itemStyle: { color: '#ebeef5' } }],
      },
    ],
  })
}

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await stabilityApi.listCases({
      project_id: projectId,
      domain: domain.value,
      name: keyword.value.trim() || undefined,
      unstable_only: unstableOnly.value || undefined,
      quarantine_only: quarantineOnly.value || undefined,
      has_runs_only: hasRunsOnly.value || undefined,
      sort_by: sortBy.value || undefined,
      sort_order: sortBy.value ? sortOrder.value : undefined,
      page: page.value,
      size: size.value,
    })
    const body = res.data
    if (body == null || typeof body !== 'object' || Array.isArray(body)) {
      items.value = []
      total.value = 0
      ElMessage.error('执行可信度接口异常：请确认 Nginx 已代理 /stability 到后端')
      return
    }
    const data = body.data && typeof body.data === 'object' ? body.data : body
    items.value = Array.isArray(data.items) ? data.items : []
    total.value = Number(data.total) || 0
    windowN.value = Number(data.n) || 0
    recentK.value = Number(data.recent_k) || 5
    overview.value = data.overview || overview.value
    overviewScope.value = data.overview_scope || 'page'
    await nextTick()
    renderBandChart()
  } catch (e) {
    console.error(e)
    ElMessage.error('加载稳定度失败')
  } finally {
    loading.value = false
  }
}

async function toggleQuarantine(row) {
  const enabled = !row.quarantine
  await ElMessageBox.confirm(
    enabled ? '隔离后计划/定时默认跳过该用例，确认？' : '解除隔离后将重新进入计划执行，确认？',
    '隔离确认',
    { type: 'warning' },
  )
  const res = await stabilityApi.setQuarantine(row.case_id, {
    enabled,
    domain: domain.value,
  })
  if (res.data?.code === 200) {
    ElMessage.success(enabled ? '已隔离' : '已解除隔离')
    await loadList()
  }
}

function onResize() {
  bandChart?.resize()
}

watch(
  () => proStore.projectInfo?.id,
  () => {
    page.value = 1
    loadList()
  },
  { immediate: true },
)

onMounted(() => {
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  bandChart?.dispose()
  bandChart = null
})
</script>

<style scoped>
.stab-help {
  margin-bottom: 12px;
  border: none;
  --el-collapse-header-height: 40px;
}
.stab-help :deep(.el-collapse-item__header) {
  background: linear-gradient(90deg, #f5f9ff 0%, #fafbfc 100%);
  border: 1px solid #e8eef7;
  border-radius: 8px;
  padding: 0 14px;
  font-weight: 500;
}
.stab-help :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}
.stab-help :deep(.el-collapse-item__content) {
  padding: 10px 4px 4px;
}
.stab-help-title {
  margin-right: 10px;
}
.stab-help-sub {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 400;
}
.stab-help-list {
  margin: 0;
  padding-left: 18px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}

.stab-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(100px, 1fr)) minmax(200px, 1.4fr);
  gap: 12px;
  margin-bottom: 14px;
}
.stab-stat {
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.stab-stat.warn {
  border-color: #fde2c0;
  background: #fffaf3;
}
.stab-stat.info {
  border-color: #d9ecff;
  background: #f5faff;
}
.stab-stat.ok {
  border-color: #d7f0c5;
  background: #f7fcf3;
}
.stab-stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.stab-stat-value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 600;
  color: #1f2a37;
  line-height: 1.2;
}
.stab-stat-hint {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.stab-chart-wrap {
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 10px;
  min-height: 120px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.stab-chart {
  width: 100%;
  height: 120px;
}

.stab-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}

.stab-table {
  border-radius: 8px;
  overflow: hidden;
}
.rate-high {
  color: #67c23a;
  font-weight: 600;
}
.rate-mid {
  color: #e6a23c;
  font-weight: 600;
}
.rate-low {
  color: #f56c6c;
  font-weight: 600;
}
.n-hint {
  margin-left: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 1100px) {
  .stab-overview {
    grid-template-columns: repeat(2, 1fr);
  }
  .stab-chart-wrap {
    grid-column: 1 / -1;
  }
}
</style>
