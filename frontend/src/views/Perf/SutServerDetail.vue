<template>
  <PageCard>
    <template #title>
      <div class="title-row">
        <el-button link type="primary" @click="goBack">← 返回</el-button>
        <div style="font-size: 18px; font-weight: bold;">
          {{ detail?.name || '监控详情' }}
          <el-tag
            v-if="detail"
            size="small"
            :type="detail.status === 'online' ? 'success' : 'info'"
            style="margin-left: 8px"
          >
            {{ detail.status === 'online' ? '在线' : '离线' }}
          </el-tag>
          <el-tag
            v-if="detail"
            size="small"
            :type="detail.monitoring_enabled ? 'success' : 'warning'"
            style="margin-left: 6px"
          >
            监控{{ detail.monitoring_enabled ? '开' : '关' }}
          </el-tag>
        </div>
      </div>
    </template>
    <template #main>
      <div class="meta" v-if="detail">
        <span>主机：{{ detail.hostname || '-' }}</span>
        <span>角色：{{ detail.role || '-' }}</span>
        <span>心跳：{{ detail.last_heartbeat_at || '-' }}</span>
        <span v-if="detail.agent_settings">
          采集：{{ detail.agent_settings.interval_sec }}s /
          上报 {{ detail.agent_settings.upload_every_sec }}s /
          缓冲 {{ detail.agent_settings.buffer_hours }}h
        </span>
        <span v-else>采集：本机配置</span>
        <el-button size="small" @click="loadAll" :loading="loading">刷新</el-button>
      </div>

      <div class="filters">
        <div class="filter-row">
          <span class="filter-label">时间</span>
          <el-radio-group v-model="rangePreset" size="small" @change="onPresetChange">
            <el-radio-button value="15m">近 15 分钟</el-radio-button>
            <el-radio-button value="1h">近 1 小时</el-radio-button>
            <el-radio-button value="6h">近 6 小时</el-radio-button>
            <el-radio-button value="24h">近 24 小时</el-radio-button>
            <el-radio-button value="custom">自定义</el-radio-button>
          </el-radio-group>
          <el-date-picker
            v-if="rangePreset === 'custom'"
            v-model="customRange"
            type="datetimerange"
            size="small"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            :clearable="false"
            style="max-width: 380px"
            @change="onCustomRangeChange"
          />
        </div>
        <div class="filter-row">
          <span class="filter-label">曲线</span>
          <el-checkbox-group v-model="metricTypes" size="small" @change="onMetricTypesChange">
            <el-checkbox-button
              v-for="m in METRIC_OPTIONS"
              :key="m.key"
              :value="m.key"
            >{{ m.short }}</el-checkbox-button>
          </el-checkbox-group>
        </div>
        <el-collapse class="metric-help-collapse">
          <el-collapse-item title="指标说明（点击展开）" name="help">
            <ul class="metric-help-list">
              <li v-for="h in METRIC_HELP" :key="h.name">
                <strong>{{ h.name }}</strong>
                <span>{{ h.desc }}</span>
              </li>
              <li>
                <strong>采样点数</strong>
                <span>当前时间窗内平台收到的有效采样个数；间隔约等于采集器配置的采样周期。</span>
              </li>
              <li>
                <strong>平均 / 最大</strong>
                <span>对窗内有效采样点分别求均值与峰值；「最大」适合看尖峰，「平均」看整体水位。</span>
              </li>
            </ul>
          </el-collapse-item>
        </el-collapse>
      </div>

      <div class="summary" v-if="summary">
        <div v-for="card in summaryCards" :key="card.key" class="summary-card">
          <div class="summary-title">{{ card.title }}</div>
          <div class="summary-unit">{{ card.unit }}</div>
          <div class="summary-row">
            <span class="k">平均</span>
            <span class="v">{{ card.avg }}</span>
          </div>
          <div class="summary-row">
            <span class="k">最大</span>
            <span class="v">{{ card.max }}</span>
          </div>
        </div>
        <div class="summary-card summary-card-points">
          <div class="summary-title">采样点数</div>
          <div class="summary-unit">个</div>
          <div class="summary-points">{{ summary.point_count || 0 }}</div>
        </div>
      </div>

      <el-empty
        v-if="!loading && emptySeries"
        description="暂无采样数据。请确认被测监控采集器已启动且监控已开启，或扩大时间范围。"
      />
      <div v-show="!emptySeries" ref="chartRef" class="chart-box" v-loading="loading" />
      <p class="hint">
        当前窗口：{{ rangeHint }}。上方卡片为该窗内汇总；曲线勾选控制图中显示哪些指标。
        平台指标默认保留约 14 天；单次查询最长 24 小时。相对时间窗每 15 秒自动刷新。
      </p>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageCard from '@/components/PageCard.vue'
import { perfSutServerApi } from '@/api/modules/perf'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer])

const METRIC_OPTIONS = [
  { key: 'cpu', short: 'CPU使用率', name: 'CPU使用率(%)', field: 'cpu_pct', y: 0 },
  { key: 'mem', short: '内存占用', name: '内存占用(%)', field: 'mem_pct', y: 0 },
  { key: 'disk', short: '磁盘占用', name: '磁盘占用(%)', field: 'disk_pct', y: 0 },
  { key: 'load', short: '系统负载', name: '1分钟系统负载', field: 'load1', y: 2 },
  { key: 'net_rx', short: '网络下行', name: '网络下行(KB/s)', field: 'net_rx_kbps', y: 1 },
  { key: 'net_tx', short: '网络上行', name: '网络上行(KB/s)', field: 'net_tx_kbps', y: 1 },
  { key: 'disk_r', short: '磁盘读取', name: '磁盘读取(KB/s)', field: 'disk_read_kbps', y: 1 },
  { key: 'disk_w', short: '磁盘写入', name: '磁盘写入(KB/s)', field: 'disk_write_kbps', y: 1 },
]

const METRIC_HELP = [
  {
    name: 'CPU使用率',
    desc: '整机 CPU 忙碌比例（0～100%）。持续偏高说明算力吃紧；卡片「当前 CPU」常为瞬时值，空闲时显示 0% 正常。',
  },
  {
    name: '内存占用',
    desc: '已用内存占物理内存的比例。偏高时注意 OOM 风险；含缓存/缓冲，与「可用内存」口径不同。',
  },
  {
    name: '磁盘占用',
    desc: '系统盘（Linux 根分区 / Windows 系统盘）空间使用比例，不是读写速度。',
  },
  {
    name: '1分钟系统负载（load1）',
    desc: 'Linux 近 1 分钟可运行队列长度，不是百分比。可与 CPU 核数对照：长期明显高于核数，说明排队严重。',
  },
  {
    name: '网络下行 / 上行',
    desc: '相对上一采样的网卡收/发速率（KB/s）。含所有网卡合计；采集器上报自身流量也会算进去。',
  },
  {
    name: '磁盘读取 / 写入',
    desc: '相对上一采样的磁盘读写速率（KB/s），反映 IO 忙闲，与「磁盘占用%」无关。',
  },
]

const SUMMARY_DEFS = [
  { key: 'cpu', title: 'CPU使用率', unit: '%', path: 'cpu_pct' },
  { key: 'mem', title: '内存占用', unit: '%', path: 'mem_pct' },
  { key: 'disk', title: '磁盘占用', unit: '%', path: 'disk_pct' },
  { key: 'load', title: '1分钟系统负载', unit: '无量纲', path: 'load1' },
  { key: 'net_rx', title: '网络下行', unit: 'KB/s', path: 'net_rx_kbps' },
  { key: 'net_tx', title: '网络上行', unit: 'KB/s', path: 'net_tx_kbps' },
  { key: 'disk_r', title: '磁盘读取', unit: 'KB/s', path: 'disk_read_kbps' },
  { key: 'disk_w', title: '磁盘写入', unit: 'KB/s', path: 'disk_write_kbps' },
]

const PRESET_MS = {
  '15m': 15 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '6h': 6 * 60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
}

const route = useRoute()
const router = useRouter()
const serverId = ref(Number(route.params.serverId))
const detail = ref(null)
const summary = ref(null)
const seriesPoints = ref([])
const loading = ref(false)
const chartRef = ref(null)
const rangePreset = ref('1h')
const customRange = ref([])
const metricTypes = ref(['cpu', 'mem', 'disk', 'load', 'net_rx', 'net_tx'])
let chart = null
let timer = null
let loadSeq = 0

const emptySeries = computed(() => !(seriesPoints.value && seriesPoints.value.length))
const isLiveRange = computed(() => rangePreset.value !== 'custom')

const summaryCards = computed(() => {
  const sm = summary.value || {}
  return SUMMARY_DEFS.map((d) => {
    const block = sm[d.path] || {}
    return {
      key: d.key,
      title: d.title,
      unit: d.unit,
      avg: fmt(block.avg),
      max: fmt(block.max),
    }
  })
})

const rangeHint = computed(() => {
  if (rangePreset.value === 'custom' && customRange.value?.length === 2) {
    const [a, b] = customRange.value
    return `${formatDt(a)} ~ ${formatDt(b)}`
  }
  const map = { '15m': '近 15 分钟', '1h': '近 1 小时', '6h': '近 6 小时', '24h': '近 24 小时' }
  return map[rangePreset.value] || '近 1 小时'
})

function formatDt(d) {
  if (!d) return '-'
  const x = d instanceof Date ? d : new Date(d)
  if (Number.isNaN(x.getTime())) return '-'
  const p = (n) => String(n).padStart(2, '0')
  return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())} ${p(x.getHours())}:${p(x.getMinutes())}`
}

function fmt(v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  if (Math.abs(n) >= 1000) return Math.round(n)
  return Math.round(n * 10) / 10
}

function goBack() {
  router.push('/perf-sut-servers')
}

function resolveRangeMs() {
  const to = Date.now()
  if (rangePreset.value === 'custom' && customRange.value?.length === 2) {
    const from = new Date(customRange.value[0]).getTime()
    const end = new Date(customRange.value[1]).getTime()
    if (!Number.isNaN(from) && !Number.isNaN(end) && from <= end) {
      return { from_ms: from, to_ms: end }
    }
  }
  const span = PRESET_MS[rangePreset.value] || PRESET_MS['1h']
  return { from_ms: to - span, to_ms: to }
}

function onPresetChange() {
  if (rangePreset.value === 'custom') {
    if (!customRange.value?.length) {
      const to = new Date()
      const from = new Date(to.getTime() - PRESET_MS['1h'])
      customRange.value = [from, to]
    }
    stopTimer()
  } else {
    ensureTimer()
  }
  loadAll()
}

function onCustomRangeChange() {
  if (rangePreset.value !== 'custom') return
  const { from_ms, to_ms } = resolveRangeMs()
  if (to_ms - from_ms > 24 * 60 * 60 * 1000) {
    ElMessage.warning('查询时间窗不能超过 24 小时')
    return
  }
  loadAll()
}

function onMetricTypesChange(vals) {
  if (!vals?.length) {
    ElMessage.warning('请至少选择一种指标类型')
    metricTypes.value = ['cpu']
  }
  renderChart(seriesPoints.value)
}

function onResize() {
  chart?.resize()
}

function renderChart(series) {
  if (!chartRef.value || !series?.length) {
    if (chart) chart.clear()
    return
  }
  if (!chart) chart = echarts.init(chartRef.value)
  const times = series.map((p) => {
    const d = new Date(Number(p.ts_ms))
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
  })
  const selected = new Set(metricTypes.value || [])
  const active = METRIC_OPTIONS.filter((m) => selected.has(m.key))
  const needPct = active.some((m) => m.y === 0)
  const needNet = active.some((m) => m.y === 1)
  const needLoad = active.some((m) => m.y === 2)
  const yAxis = []
  const yIndexOf = { 0: 0, 1: 0, 2: 0 }
  if (needPct) {
    yIndexOf[0] = yAxis.length
    yAxis.push({ type: 'value', name: '%', min: 0, max: 100 })
  }
  if (needLoad) {
    yIndexOf[2] = yAxis.length
    yAxis.push({
      type: 'value',
      name: 'load',
      min: 0,
      splitLine: { show: !needPct },
    })
  }
  if (needNet) {
    yIndexOf[1] = yAxis.length
    yAxis.push({
      type: 'value',
      name: 'KB/s',
      min: 0,
      splitLine: { show: !needPct && !needLoad },
    })
  }
  const seriesOpt = active.map((m) => ({
    name: m.name,
    type: 'line',
    showSymbol: false,
    data: series.map((p) => p[m.field] ?? null),
    yAxisIndex: yIndexOf[m.y] ?? 0,
  }))
  chart.setOption(
    {
      tooltip: { trigger: 'axis' },
      legend: { data: active.map((m) => m.name) },
      grid: { left: 48, right: needNet || needLoad ? 56 : 24, top: 48, bottom: 48 },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18 }],
      xAxis: { type: 'category', data: times },
      yAxis: yAxis.length ? yAxis : [{ type: 'value' }],
      series: seriesOpt,
    },
    true
  )
}

async function loadAll() {
  const id = serverId.value
  if (!id || Number.isNaN(id)) {
    ElMessage.error('无效的服务器 ID')
    goBack()
    return false
  }
  if (loading.value) return true
  const seq = ++loadSeq
  loading.value = true
  try {
    const range = resolveRangeMs()
    const [dRes, mRes] = await Promise.all([
      perfSutServerApi.getDetail(id),
      perfSutServerApi.getMetrics(id, range),
    ])
    if (seq !== loadSeq) return true
    detail.value = dRes?.data || dRes || null
    const metrics = mRes?.data || mRes || {}
    summary.value = metrics.summary || null
    seriesPoints.value = metrics.series || []
    await nextTick()
    renderChart(seriesPoints.value)
    return true
  } catch (e) {
    if (seq !== loadSeq) return true
    ElMessage.error(e?.response?.data?.detail || e?.data?.detail || '加载失败')
    return true
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function ensureTimer() {
  stopTimer()
  if (!isLiveRange.value) return
  timer = setInterval(() => {
    if (isLiveRange.value) loadAll()
  }, 15000)
}

watch(
  () => route.params.serverId,
  (raw) => {
    serverId.value = Number(raw)
    detail.value = null
    summary.value = null
    seriesPoints.value = []
    loadAll()
  }
)

onMounted(async () => {
  const ok = await loadAll()
  if (ok !== false) ensureTimer()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  stopTimer()
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.filter-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  width: 36px;
  flex-shrink: 0;
}
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.summary-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-blank);
}
.summary-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.3;
}
.summary-unit {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin: 2px 0 8px;
}
.summary-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 13px;
  line-height: 1.55;
}
.summary-row .k {
  color: var(--el-text-color-secondary);
}
.summary-row .v {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
}
.summary-card-points .summary-points {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-top: 4px;
}
.metric-help-collapse {
  border: none;
  --el-collapse-header-height: 36px;
}
.metric-help-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: var(--el-text-color-regular);
  background: transparent;
  border: none;
}
.metric-help-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}
.metric-help-list {
  margin: 0;
  padding: 0 0 4px 18px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.65;
}
.metric-help-list li {
  margin-bottom: 6px;
}
.metric-help-list strong {
  margin-right: 6px;
  color: var(--el-text-color-primary);
}
.chart-box {
  width: 100%;
  height: 360px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
