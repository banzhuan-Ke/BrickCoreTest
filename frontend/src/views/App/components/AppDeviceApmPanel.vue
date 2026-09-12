<template>
  <div class="app-device-apm">
    <div class="app-device-apm__title">
      设备性能（手机资源）
      <el-tooltip content="随 App 执行采集的本机进程指标，与「被测服务器监控」无关。" placement="top">
        <el-icon class="app-device-apm__help"><QuestionFilled /></el-icon>
      </el-tooltip>
    </div>

    <el-collapse class="metric-help-collapse">
      <el-collapse-item title="指标说明（点击展开）" name="help">
        <ul class="metric-help-list">
          <li v-for="h in METRIC_HELP" :key="h.name">
            <strong>{{ h.name }}</strong>
            <span>{{ h.desc }}</span>
          </li>
        </ul>
      </el-collapse-item>
    </el-collapse>

    <template v-if="hasData">
      <div class="app-device-apm__cards">
        <div v-for="c in cards" :key="c.key" class="app-device-apm__card">
          <div class="app-device-apm__card-label">{{ c.label }}</div>
          <div class="app-device-apm__card-value">{{ c.value }}</div>
          <div v-if="c.hint" class="app-device-apm__card-hint">{{ c.hint }}</div>
        </div>
      </div>

      <div v-if="availableChartMetrics.length" class="chart-metric-bar">
        <span class="chart-metric-bar__label">趋势图指标</span>
        <el-checkbox-group v-model="selectedChartKeys" size="small">
          <el-checkbox-button v-for="m in availableChartMetrics" :key="m.key" :label="m.key">
            {{ m.short }}
          </el-checkbox-button>
        </el-checkbox-group>
      </div>

      <div ref="chartEl" class="app-device-apm__chart" />
      <el-text v-if="unsupportedText" type="warning" size="small">{{ unsupportedText }}</el-text>
      <el-text v-if="emptyHint" type="info" size="small" style="display: block; margin-top: 4px">{{ emptyHint }}</el-text>
    </template>
    <el-empty v-else-if="showEmpty" description="本次未采集设备性能（未开启或执行器未上报）" :image-size="64" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  CanvasRenderer,
])

const DEFAULT_THRESHOLDS = {
  cpu_pct: 80,
  mem_pss_mb: 512,
  fps: 45,
  janky_pct: 10,
  gpu_busy_pct: 90,
}

const METRIC_HELP = [
  { name: 'CPU %（单核 100%）', desc: '进程相对单核占用；多核繁忙时可超过 100。不等于整机 CPU。' },
  { name: 'PSS / RSS', desc: 'PSS 为按比例分摊的物理内存；RSS 为常驻集。单位 MB。' },
  { name: 'Java / Native / Graphics', desc: '来自 dumpsys meminfo 的堆与图形内存拆分；部分 ROM 可能解析不到显示为 —。' },
  { name: 'FPS', desc: '由 gfxinfo 帧差推算的窗口帧率；卡片展示平均 FPS。warmup / 无新帧(0) / degraded 不计入平均。' },
  { name: 'Jank 窗口占比', desc: '采样间隔内 Δ卡顿帧 / Δ总帧 ×100%，不是 dumpsys 累计 Jank%。' },
  { name: 'GPU 忙碌%', desc: '高通 kgsl 窗口差分利用率；非高通机型常 unsupported。' },
  { name: '磁盘剩余', desc: '/data 分区可用空间，偏系统水位，非 App 占用。' },
  { name: '热状态', desc: 'thermalservice 等级（none→shutdown）。' },
  { name: '电量 / 温度', desc: 'dumpsys battery 电量与电池温度。' },
  { name: '网络 RX / TX', desc: '相对监控起点的累计流量（KB）；需勾选「网络」才会采集。' },
  {
    name: '采样空洞',
    desc: '某次采样失败的次数（如 App 进程未起、pid 找不到、核心指标整轮 unavailable）。不是网络丢包。次数高说明那段时间数据不可信。',
  },
]

/** family = 上方「采集指标」勾选项 */
const CHART_METRICS = [
  { key: 'cpu_pct', short: 'CPU%', field: 'cpu_pct', family: 'cpu', yAxisIndex: 0, defaultOn: true },
  { key: 'mem_pss_mb', short: 'PSS', field: 'mem_pss_mb', family: 'memory', yAxisIndex: 1, defaultOn: true },
  { key: 'fps', short: 'FPS', field: 'fps', family: 'fps', yAxisIndex: 0, defaultOn: true },
  { key: 'janky_pct', short: 'Jank%', field: 'janky_pct', family: 'jank', yAxisIndex: 0, defaultOn: true },
  { key: 'battery_pct', short: '电量', field: 'battery_pct', family: 'battery', yAxisIndex: 0, defaultOn: true },
  { key: 'mem_java_heap_mb', short: 'Java堆', field: 'mem_java_heap_mb', family: 'memory', yAxisIndex: 1, defaultOn: false },
  { key: 'mem_native_heap_mb', short: 'Native', field: 'mem_native_heap_mb', family: 'memory', yAxisIndex: 1, defaultOn: false },
  { key: 'mem_graphics_mb', short: 'Graphics', field: 'mem_graphics_mb', family: 'memory', yAxisIndex: 1, defaultOn: false },
  { key: 'gpu_busy_pct', short: 'GPU%', field: 'gpu_busy_pct', family: 'gpu', yAxisIndex: 0, defaultOn: true },
  { key: 'disk_free_mb', short: '磁盘', field: 'disk_free_mb', family: 'disk', yAxisIndex: 1, defaultOn: true },
  { key: 'temp_c', short: '温度', field: 'temp_c', family: 'battery', yAxisIndex: 0, defaultOn: false },
  { key: 'net_rx_kb', short: 'RX', field: 'net_rx_kb', family: 'network', yAxisIndex: 1, defaultOn: true },
  { key: 'net_tx_kb', short: 'TX', field: 'net_tx_kb', family: 'network', yAxisIndex: 1, defaultOn: true },
]

const CARD_DEFS = [
  { key: 'cpu', label: 'CPU 峰值（单核100%）', family: 'cpu', get: (s) => s.cpu_pct_max, unit: '%' },
  { key: 'mem', label: '内存峰值 PSS', family: 'memory', get: (s) => s.mem_pss_mb_max, unit: ' MB' },
  { key: 'java', label: 'Java 堆峰值', family: 'memory', get: (s) => s.mem_java_heap_mb_max, unit: ' MB' },
  { key: 'native', label: 'Native 堆峰值', family: 'memory', get: (s) => s.mem_native_heap_mb_max, unit: ' MB' },
  { key: 'graphics', label: 'Graphics 峰值', family: 'memory', get: (s) => s.mem_graphics_mb_max, unit: ' MB' },
  { key: 'fps', label: 'FPS 平均', family: 'fps', get: (s) => s.fps_avg, unit: '' },
  { key: 'jank', label: 'Jank 窗口占比峰值', family: 'jank', get: (s) => s.janky_pct_max, unit: '%' },
  { key: 'gpu', label: 'GPU 忙碌峰值', family: 'gpu', get: (s) => s.gpu_busy_pct_max, unit: '%' },
  { key: 'disk', label: '磁盘剩余最低', family: 'disk', get: (s) => s.disk_free_mb_min, unit: ' MB' },
  { key: 'thermal', label: '热状态最差', family: 'thermal', get: (s) => s.thermal_status_worst, unit: '', text: true },
  { key: 'bat', label: '电量末值', family: 'battery', get: (s) => s.battery_pct_last, unit: '%' },
  { key: 'temp', label: '温度峰值', family: 'battery', get: (s) => s.temp_c_max, unit: ' ℃' },
  { key: 'net_rx', label: '网络 RX 累计', family: 'network', get: (s) => s.net_rx_kb_delta, unit: ' KB' },
  { key: 'net_tx', label: '网络 TX 累计', family: 'network', get: (s) => s.net_tx_kb_delta, unit: ' KB' },
]

const props = defineProps({
  summary: { type: Object, default: null },
  series: { type: Array, default: () => [] },
  thresholds: { type: Object, default: null },
  showEmpty: { type: Boolean, default: false },
  live: { type: Boolean, default: false },
  /** 上方勾选的采集指标族：cpu/memory/fps/... */
  collectedMetrics: { type: Array, default: () => [] },
})

const chartEl = ref(null)
let chart = null
const selectedChartKeys = ref([])

const collectedSet = computed(() => {
  const list = (props.collectedMetrics || []).map((x) => String(x).toLowerCase()).filter(Boolean)
  return new Set(list)
})

const availableChartMetrics = computed(() => {
  const set = collectedSet.value
  if (set.size) return CHART_METRICS.filter((m) => set.has(m.family))
  // 报告页未传 collectedMetrics：按 series 实际有值的字段展示可选曲线
  const series = props.series || []
  if (!series.length) return CHART_METRICS.filter((m) => m.defaultOn)
  const withData = CHART_METRICS.filter((m) => series.some((p) => p && p[m.field] != null))
  return withData.length ? withData : CHART_METRICS.filter((m) => m.defaultOn)
})

function syncChartSelection() {
  const avail = availableChartMetrics.value
  const availKeys = new Set(avail.map((m) => m.key))
  const preferred = avail.filter((m) => m.defaultOn).map((m) => m.key)
  const keep = (selectedChartKeys.value || []).filter((k) => availKeys.has(k))
  selectedChartKeys.value = keep.length ? keep : preferred.length ? preferred : avail.map((m) => m.key)
}

const resolvedThresholds = computed(() => ({
  ...DEFAULT_THRESHOLDS,
  ...(props.summary?.thresholds || {}),
  ...(props.thresholds || {}),
}))

const hasData = computed(() => {
  const s = props.summary
  const series = props.series || []
  return (s && typeof s === 'object' && Object.keys(s).length > 0) || series.length > 0
})

function fmt(v, unit = '') {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  return `${Number(v).toFixed(1)}${unit}`
}

function metricFamilyCollected(family) {
  const set = collectedSet.value
  if (!set.size) return null
  return set.has(family)
}

function cardHint(family, hasValue) {
  const liveApprox = props.live || props.summary?.live_window_approx
  if (hasValue) {
    if (liveApprox && (family === 'network')) return '本次会话累计（最近窗口）'
    if (liveApprox) return '最近窗口近似'
    return ''
  }
  const on = metricFamilyCollected(family)
  if (on === false) return '未勾选采集'
  if (on === true) return '设备未上报/不可用'
  return ''
}

const cards = computed(() => {
  const s = props.summary || {}
  const set = collectedSet.value
  if (s.scope === 'plan_multi_suite') {
    return [
      {
        key: 'scope',
        label: '计划级说明',
        value: s.note || '多套件计划不合并设备性能曲线，请查看各套件报告',
        hint: s.suite_count_with_apm != null ? `含 APM 套件数：${s.suite_count_with_apm}` : '',
      },
    ]
  }
  // 有勾选时只展示对应卡片；无勾选信息时展示全部（报告页）
  const defs = set.size ? CARD_DEFS.filter((c) => set.has(c.family)) : CARD_DEFS
  const out = defs.map((c) => {
    const raw = c.get(s)
    const hasValue = raw != null && raw !== ''
    return {
      key: c.key,
      label: c.label,
      value: c.text ? raw || '—' : fmt(raw, c.unit),
      hint: cardHint(c.family, hasValue),
    }
  })
  // 采样数始终展示在指标卡片区（有数据时）
  const sampleCount = s.sample_count != null ? s.sample_count : (props.series || []).length || null
  if (sampleCount != null) {
    out.unshift({
      key: 'samples',
      label: '采样数',
      value: String(sampleCount),
      hint: props.live ? '最近窗口近似' : '',
    })
  }
  if (s.duration_sec != null) {
    out.push({ key: 'dur', label: '采集时长', value: fmt(s.duration_sec, ' s'), hint: '' })
  }
  if (s.gap_count != null && Number(s.gap_count) > 0) {
    out.push({
      key: 'gap',
      label: '采样空洞',
      value: String(s.gap_count),
      hint: '进程未起等导致的失败采样次数',
    })
  }
  return out
})

const unsupportedText = computed(() => {
  const list = props.summary?.unsupported_metrics
  if (!Array.isArray(list) || !list.length) return ''
  return `部分指标不可用：${list.join(', ')}`
})

const emptyHint = computed(() => {
  const notes = props.summary?.quality_notes
  if (!notes || typeof notes !== 'object') return ''
  const parts = Object.entries(notes)
    .filter(([k]) => !String(k).endsWith('_basis'))
    .map(([k, v]) => `${k}: ${v}`)
  return parts.length ? `采集备注：${parts.slice(0, 4).join('；')}` : ''
})

function formatTs(ts) {
  const d = new Date(Number(ts) || 0)
  if (!Number(ts)) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function stepMarkPoints(series) {
  const marks = []
  let prev = null
  series.forEach((p, idx) => {
    const sid = (p.step_id || '').toString().trim()
    if (!sid || sid === prev) return
    prev = sid
    if (p.cpu_pct == null || Number.isNaN(Number(p.cpu_pct))) return
    marks.push({
      name: sid,
      coord: [idx, Number(p.cpu_pct)],
      value: sid.length > 12 ? `${sid.slice(0, 12)}…` : sid,
      symbol: 'diamond',
      symbolSize: 8,
      label: {
        show: true,
        formatter: '{c}',
        position: 'top',
        fontSize: 10,
        color: '#64748b',
      },
      itemStyle: { color: '#94a3b8' },
    })
  })
  return marks.slice(0, 40)
}

function buildOption() {
  const series = props.series || []
  const thr = resolvedThresholds.value
  const times = series.map((p) => formatTs(p.ts_ms))
  const stepMarks = stepMarkPoints(series)
  const avail = availableChartMetrics.value
  const keys = (selectedChartKeys.value || []).filter((k) => avail.some((m) => m.key === k))
  const useKeys = keys.length ? keys : avail.filter((m) => m.defaultOn).map((m) => m.key)
  const lines = avail
    .filter((m) => useKeys.includes(m.key))
    .map((m) => {
      const line = {
        name: m.short,
        yAxisIndex: m.yAxisIndex,
        data: series.map((p) => p[m.field]),
      }
      if (m.key === 'cpu_pct' && thr.cpu_pct != null) {
        line.markLine = {
          silent: true,
          data: [{ yAxis: thr.cpu_pct, name: 'CPU 阈值', label: { formatter: 'CPU {c}%' } }],
          lineStyle: { color: '#ef4444', type: 'dashed' },
        }
        if (stepMarks.length) line.markPoint = { data: stepMarks }
      }
      if (m.key === 'mem_pss_mb' && thr.mem_pss_mb != null) {
        line.markLine = {
          silent: true,
          data: [{ yAxis: thr.mem_pss_mb, name: '内存阈值' }],
          lineStyle: { color: '#f59e0b', type: 'dashed' },
        }
      }
      if (m.key === 'fps' && thr.fps != null) {
        line.markLine = {
          silent: true,
          data: [{ yAxis: thr.fps, name: 'FPS 阈值' }],
          lineStyle: { color: '#10b981', type: 'dashed' },
        }
      }
      if (m.key === 'janky_pct' && thr.janky_pct != null) {
        line.markLine = {
          silent: true,
          data: [{ yAxis: thr.janky_pct, name: 'Jank 阈值' }],
          lineStyle: { color: '#8b5cf6', type: 'dashed' },
        }
      }
      if (m.key === 'gpu_busy_pct' && thr.gpu_busy_pct != null) {
        line.markLine = {
          silent: true,
          data: [{ yAxis: thr.gpu_busy_pct, name: 'GPU 阈值', label: { formatter: 'GPU {c}%' } }],
          lineStyle: { color: '#06b6d4', type: 'dashed' },
        }
      }
      return line
    })

  const needLeft = lines.some((l) => l.yAxisIndex === 0)
  const needRight = lines.some((l) => l.yAxisIndex === 1)
  const yAxis = []
  if (needLeft) yAxis.push({ type: 'value', name: '% / fps', scale: true })
  else yAxis.push({ type: 'value', show: false })
  if (needRight) yAxis.push({ type: 'value', name: 'MB / KB', scale: true, splitLine: { show: false } })
  else yAxis.push({ type: 'value', show: false })

  return {
    color: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#84cc16', '#f97316', '#a855f7', '#64748b'],
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        if (!Array.isArray(params) || !params.length) return ''
        const idx = params[0].dataIndex
        const p = series[idx] || {}
        const linesOut = params.map((it) => `${it.marker}${it.seriesName}: ${it.value ?? '—'}`)
        if (p.error) linesOut.push(`error: ${p.error}`)
        const q = p.quality || {}
        const bad = Object.entries(q).filter(([, v]) => v && v !== 'ok').map(([k, v]) => `${k}=${v}`)
        if (bad.length) linesOut.push(`quality: ${bad.join(', ')}`)
        return `${params[0].axisValue}<br/>${linesOut.join('<br/>')}`
      },
    },
    legend: { top: 0, type: 'scroll' },
    grid: { left: 48, right: 56, top: 40, bottom: 28 },
    xAxis: { type: 'category', data: times, boundaryGap: false },
    yAxis,
    animation: !props.live,
    series: lines.map((l) => ({
      name: l.name,
      type: 'line',
      showSymbol: series.length <= 2,
      yAxisIndex: l.yAxisIndex || 0,
      data: l.data,
      connectNulls: false,
      markLine: l.markLine,
      markPoint: l.markPoint,
    })),
  }
}

function renderChart() {
  if (!chartEl.value || !hasData.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption(buildOption(), true)
}

watch(
  () => [...(props.collectedMetrics || [])],
  () => {
    syncChartSelection()
  },
  { immediate: true }
)

watch(
  () => [props.summary, props.series, props.thresholds, selectedChartKeys.value, availableChartMetrics.value],
  async () => {
    await nextTick()
    renderChart()
  },
  { deep: true }
)

onMounted(async () => {
  syncChartSelection()
  await nextTick()
  renderChart()
  window.addEventListener('resize', renderChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', renderChart)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped lang="scss">
.app-device-apm {
  margin: 16px 0 8px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}
.app-device-apm__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  margin-bottom: 8px;
}
.app-device-apm__help {
  color: var(--el-text-color-secondary);
  cursor: help;
}
.metric-help-collapse {
  margin-bottom: 12px;
  --el-collapse-header-height: 36px;
}
.metric-help-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.metric-help-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.metric-help-list strong {
  margin-right: 6px;
  color: var(--el-text-color-primary);
}
.app-device-apm__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.app-device-apm__card {
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
}
.app-device-apm__card-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.app-device-apm__card-value {
  margin-top: 4px;
  font-size: 16px;
  font-weight: 600;
}
.app-device-apm__card-hint {
  margin-top: 2px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.chart-metric-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.chart-metric-bar__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.app-device-apm__chart {
  width: 100%;
  height: 280px;
}
</style>
