<template>
  <div v-if="hasAny" class="perf-overlay-charts">
    <div class="overlay-head">
      <h3 class="overlay-title">{{ title }}</h3>
      <p class="overlay-hint">
        多轮曲线按相对秒对齐叠画；可拖拽/滚轮缩放，点「放大」全屏查看。
        流式阶段压测时，秒级点多在请求完成时出现，耗时长的一轮会更晚才有数据。
      </p>
    </div>
    <div v-if="hasTrend" class="chart-block">
      <div class="chart-label-row">
        <div class="chart-label">QPS 对比</div>
        <el-button link type="primary" @click="openZoom('qps')">放大</el-button>
      </div>
      <div ref="qpsRef" class="chart-box" />
    </div>
    <div v-if="hasTrend" class="chart-block">
      <div class="chart-label-row">
        <div class="chart-label">平均响应时间对比</div>
        <el-button link type="primary" @click="openZoom('avg_rt')">放大</el-button>
      </div>
      <div ref="avgRef" class="chart-box" />
    </div>
    <div v-if="hasTrend" class="chart-block">
      <div class="chart-label-row">
        <div class="chart-label">P95 对比</div>
        <el-button link type="primary" @click="openZoom('p95_rt')">放大</el-button>
      </div>
      <div ref="p95Ref" class="chart-box" />
    </div>
    <div v-if="hasHist" class="chart-block">
      <div class="chart-label-row">
        <div class="chart-label">响应时间分布对比</div>
        <el-button link type="primary" @click="openZoom('hist')">放大</el-button>
      </div>
      <div ref="histRef" class="chart-box hist" />
    </div>

    <el-dialog
      v-model="zoomVisible"
      :title="zoomTitle"
      width="92%"
      top="4vh"
      destroy-on-close
      append-to-body
      class="perf-chart-zoom-dialog"
      @opened="renderZoom"
      @closed="disposeZoom"
    >
      <div ref="zoomRef" class="chart-box zoom" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
])

const COLORS = ['#3182ce', '#dd6b20', '#38a169', '#805ad5', '#e53e3e', '#319795']

const props = defineProps({
  records: { type: Array, default: () => [] },
  title: { type: String, default: '统计图对比' },
})

const qpsRef = ref(null)
const avgRef = ref(null)
const p95Ref = ref(null)
const histRef = ref(null)
const zoomRef = ref(null)
const zoomVisible = ref(false)
const zoomKind = ref('qps')
let charts = []
let zoomChart = null

const ZOOM_TITLES = {
  qps: 'QPS 对比',
  avg_rt: '平均响应时间对比',
  p95_rt: 'P95 对比',
  hist: '响应时间分布对比',
}
const zoomTitle = computed(() => ZOOM_TITLES[zoomKind.value] || '图表放大')

const normalizeTs = (series) => {
  if (!series?.length) return []
  return [...series]
    .sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
    .map((p) => {
      const item = { ...p }
      if (item.p95_rt == null) item.p95_rt = item.avg_rt
      return item
    })
}

const seriesMeta = computed(() => {
  const allTs = new Set()
  const bucketOrder = []
  const bucketSeen = new Set()
  const meta = []
  ;(props.records || []).forEach((rec, i) => {
    const ts = normalizeTs(rec?.time_series_data || [])
    const byT = {}
    ts.forEach((p) => {
      const t = Number(p.timestamp) || 0
      byT[t] = p
      allTs.add(t)
    })
    let hist = rec?.rt_histogram || []
    if (!hist?.length && rec?.error_breakdown?.rt_histogram) {
      hist = rec.error_breakdown.rt_histogram
    }
    const histMap = {}
    ;(hist || []).forEach((b) => {
      const lab = String(b?.label || '').trim() || '?'
      histMap[lab] = Number(b?.count) || 0
      if (!bucketSeen.has(lab)) {
        bucketSeen.add(lab)
        bucketOrder.push(lab)
      }
    })
    meta.push({
      label: rec.display_name || rec.scene_name || `#${rec.id}`,
      color: COLORS[i % COLORS.length],
      byT,
      histMap,
    })
  })
  const xTs = [...allTs].sort((a, b) => a - b)
  return { meta, xTs, bucketOrder }
})

const hasTrend = computed(() => seriesMeta.value.xTs.length > 0)
const hasHist = computed(() => seriesMeta.value.bucketOrder.length > 0)
const hasAny = computed(() => (props.records || []).length >= 2 && (hasTrend.value || hasHist.value))

const disposeAll = () => {
  charts.forEach((c) => c.dispose())
  charts = []
}

const disposeZoom = () => {
  if (zoomChart) {
    zoomChart.dispose()
    zoomChart = null
  }
}

const dataZoomOpts = (bottom = 28) => [
  { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
  {
    type: 'slider',
    xAxisIndex: 0,
    height: 18,
    bottom,
    borderColor: '#e2e8f0',
    fillerColor: 'rgba(49,130,206,.15)',
    handleSize: '80%',
  },
]

const lineOption = (field, yName, { enlarged = false } = {}) => {
  const { meta, xTs } = seriesMeta.value
  return {
    color: meta.map((m) => m.color),
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll' },
    grid: {
      left: 52,
      right: 28,
      top: 40,
      bottom: enlarged ? 72 : 56,
      containLabel: false,
    },
    dataZoom: dataZoomOpts(enlarged ? 36 : 28),
    xAxis: {
      type: 'category',
      data: xTs.map((t) => `${t}s`),
      name: '相对秒',
      boundaryGap: false,
    },
    yAxis: { type: 'value', name: yName, scale: true },
    series: meta.map((m) => ({
      name: m.label,
      type: 'line',
      smooth: true,
      showSymbol: false,
      symbol: 'circle',
      symbolSize: 6,
      connectNulls: true,
      sampling: 'lttb',
      lineStyle: { width: 2 },
      emphasis: { focus: 'series' },
      data: xTs.map((t) => {
        const p = m.byT[t]
        if (!p) return null
        if (field === 'qps') {
          const v = p.qps
          return v == null ? null : Number(v)
        }
        // 有完成才标 RT；空闲秒为 null，连线跨过以形成趋势线
        if (Number(p.qps) > 0 || Number(p.total_req) > 0 || Number(p.success) > 0) {
          if (field === 'avg_rt') return p.avg_rt ?? null
          return p.p95_rt ?? p.avg_rt ?? null
        }
        return null
      }),
    })),
  }
}

const histOption = ({ enlarged = false } = {}) => {
  const { meta, bucketOrder } = seriesMeta.value
  return {
    color: meta.map((m) => m.color),
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll' },
    grid: {
      left: 52,
      right: 28,
      top: 40,
      bottom: enlarged ? 80 : 64,
      containLabel: false,
    },
    dataZoom: dataZoomOpts(enlarged ? 40 : 32),
    xAxis: { type: 'category', data: bucketOrder, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', name: '请求数' },
    series: meta.map((m) => ({
      name: m.label,
      type: 'bar',
      barMaxWidth: 28,
      data: bucketOrder.map((lab) => m.histMap[lab] || 0),
    })),
  }
}

const optionFor = (kind, enlarged = false) => {
  if (kind === 'hist') return histOption({ enlarged })
  if (kind === 'avg_rt') return lineOption('avg_rt', 'ms', { enlarged })
  if (kind === 'p95_rt') return lineOption('p95_rt', 'ms', { enlarged })
  return lineOption('qps', 'QPS', { enlarged })
}

const bind = (el, opt) => {
  if (!el || !opt) return null
  const c = echarts.init(el)
  c.setOption(opt)
  charts.push(c)
  return c
}

const render = async () => {
  disposeAll()
  if (!hasAny.value) return
  await nextTick()
  if (hasTrend.value) {
    bind(qpsRef.value, lineOption('qps', 'QPS'))
    bind(avgRef.value, lineOption('avg_rt', 'ms'))
    bind(p95Ref.value, lineOption('p95_rt', 'ms'))
  }
  if (hasHist.value) bind(histRef.value, histOption())
}

const openZoom = (kind) => {
  zoomKind.value = kind
  zoomVisible.value = true
}

const renderZoom = async () => {
  disposeZoom()
  await nextTick()
  if (!zoomRef.value) return
  zoomChart = echarts.init(zoomRef.value)
  zoomChart.setOption(optionFor(zoomKind.value, true))
}

const onResize = () => {
  charts.forEach((c) => c.resize())
  if (zoomChart) zoomChart.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})
watch(() => props.records, render, { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  disposeAll()
  disposeZoom()
})
</script>

<style scoped>
.perf-overlay-charts {
  margin-top: 8px;
}
.overlay-head {
  margin-bottom: 12px;
}
.overlay-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}
.overlay-hint {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}
.chart-block {
  margin-bottom: 16px;
}
.chart-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.chart-label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}
.chart-box {
  height: 300px;
  width: 100%;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.chart-box.hist {
  height: 320px;
}
.chart-box.zoom {
  height: min(78vh, 720px);
  border: none;
}
</style>
