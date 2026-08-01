<template>
  <div v-if="hasTrend || hasHist" class="perf-record-charts">
    <div v-if="hasTrend" class="chart-block">
      <div class="chart-title-row">
        <div class="chart-title">{{ trendTitle }}</div>
        <el-button link type="primary" @click="openZoom('trend')">放大</el-button>
      </div>
      <p v-if="trendNote" class="chart-ai-note">{{ trendNote }}</p>
      <div ref="trendRef" class="chart-box" />
      <p class="chart-hint">柱状图为该秒瞬时 QPS；折线为响应时间与错误率。可拖拽/滚轮缩放。</p>
    </div>
    <div v-if="hasHist" class="chart-block">
      <div class="chart-title-row">
        <div class="chart-title">{{ histTitle }}</div>
        <el-button link type="primary" @click="openZoom('hist')">放大</el-button>
      </div>
      <p v-if="distNote" class="chart-ai-note">{{ distNote }}</p>
      <div ref="histRef" class="chart-box hist" />
    </div>

    <el-dialog
      v-model="zoomVisible"
      :title="zoomKind === 'hist' ? histTitle : trendTitle"
      width="92%"
      top="4vh"
      destroy-on-close
      append-to-body
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
  MarkLineComponent,
  DataZoomComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DataZoomComponent,
  CanvasRenderer
])

const props = defineProps({
  timeSeries: { type: Array, default: () => [] },
  rtHistogram: { type: Array, default: () => [] },
  qps: { type: [Number, String], default: null },
  p95: { type: [Number, String], default: null },
  trendNote: { type: String, default: '' },
  distNote: { type: String, default: '' },
  trendTitle: { type: String, default: '性能趋势图' },
  histTitle: { type: String, default: '响应时间分布' }
})

const trendRef = ref(null)
const histRef = ref(null)
const zoomRef = ref(null)
const zoomVisible = ref(false)
const zoomKind = ref('trend')
let trendChart = null
let histChart = null
let zoomChart = null

const normalizeChartTimeSeries = (series) => {
  if (!series?.length) return []
  const points = [...series].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
  const totals = points.map((p) => Number(p.total_req) || 0)
  const looksCumulative =
    points.length > 1 &&
    totals.every((t, i) => i === 0 || t >= totals[i - 1]) &&
    totals[totals.length - 1] > 0
  return points.map((p, i) => {
    const item = { ...p }
    let secReq = Number(item.qps) || 0
    if (looksCumulative) {
      const prev = i > 0 ? totals[i - 1] : 0
      secReq = Math.max(0, totals[i] - prev)
      item.qps = Math.round(secReq * 100) / 100
      item.total_req = secReq
    } else if (secReq <= 0 && item.total_req) {
      secReq = Number(item.total_req)
      item.qps = secReq
    }
    if (item.p95_rt == null) item.p95_rt = item.avg_rt
    return item
  })
}

const normalizedTs = computed(() => normalizeChartTimeSeries(props.timeSeries || []))
const hasTrend = computed(() => normalizedTs.value.length > 0)
const hasHist = computed(() => (props.rtHistogram || []).length > 0)

const disposeCharts = () => {
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
  if (histChart) {
    histChart.dispose()
    histChart = null
  }
}

const disposeZoom = () => {
  if (zoomChart) {
    zoomChart.dispose()
    zoomChart = null
  }
}

const dataZoomOpts = (bottom = 36) => [
  { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
  {
    type: 'slider',
    xAxisIndex: 0,
    height: 18,
    bottom,
    borderColor: '#e2e8f0',
    fillerColor: 'rgba(84,112,198,.15)',
    handleSize: '80%'
  }
]

const buildTrendOption = ({ enlarged = false } = {}) => {
  const ts = normalizedTs.value
  const summaryQps = props.qps
  const summaryP95 = props.p95
  const xData = ts.map((d) => `${d.timestamp || 0}s`)
  const qpsData = ts.map((d) => d.qps)
  const avgRtData = ts.map((d) => (!d.qps || d.qps <= 0 ? null : d.avg_rt ?? null))
  const p95RtData = ts.map((d) => {
    if (!d.qps || d.qps <= 0) return null
    return d.p95_rt != null ? d.p95_rt : d.avg_rt ?? null
  })
  const usersData = ts.map((d) => d.active_users)
  const errorRateData = ts.map((d) => d.error_rate || 0)
  const p95MarkLine =
    summaryP95 != null
      ? {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dotted', color: '#c9a227', opacity: 0.75 },
          label: {
            formatter: `全程 P95: ${summaryP95} ms`,
            position: 'insideEndTop',
            color: '#c9a227'
          },
          data: [{ yAxis: summaryP95 }]
        }
      : undefined

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter(params) {
        if (!params?.length) return ''
        const idx = params[0].dataIndex
        const point = ts[idx] || {}
        const lines = [params[0].axisValue]
        if (!point.qps || point.qps <= 0) {
          lines.push('<span style="color:#909399">该秒无完成请求</span>')
        }
        params.forEach((p) => {
          let val = p.value
          if (val == null || val === '-') {
            lines.push(`${p.marker}${p.seriesName}: —`)
            return
          }
          if (p.seriesName === 'QPS') val = `${val}（该秒瞬时）`
          else if (String(p.seriesName).includes('P95') || String(p.seriesName).includes('RT')) {
            val = `${val} ms`
          } else if (p.seriesName === '错误率') val = `${val}%`
          lines.push(`${p.marker}${p.seriesName}: ${val}`)
        })
        if (summaryQps != null) {
          lines.push(`<span style="color:#909399">全程平均 QPS: ${summaryQps}</span>`)
        }
        if (summaryP95 != null) {
          lines.push(`<span style="color:#909399">全程 P95 RT: ${summaryP95} ms</span>`)
        }
        return lines.join('<br/>')
      }
    },
    legend: { data: ['QPS', '平均RT', 'P95 RT', '错误率', '并发用户数'], bottom: enlarged ? 42 : 28 },
    grid: {
      left: '3%',
      right: '4%',
      bottom: enlarged ? '18%' : '20%',
      top: '10%',
      containLabel: true
    },
    dataZoom: dataZoomOpts(enlarged ? 28 : 8),
    xAxis: { type: 'category', boundaryGap: true, data: xData, name: '时间(秒)' },
    yAxis: [
      { type: 'value', name: '响应时间(ms)', position: 'left' },
      { type: 'value', name: 'QPS', position: 'right' }
    ],
    series: [
      {
        name: 'QPS',
        type: 'bar',
        yAxisIndex: 1,
        data: qpsData,
        itemStyle: { color: '#91cc75', opacity: 0.7 },
        barMaxWidth: 20
      },
      {
        name: '平均RT',
        type: 'line',
        yAxisIndex: 0,
        data: avgRtData,
        connectNulls: true,
        showSymbol: false,
        smooth: true,
        itemStyle: { color: '#5470c6' }
      },
      {
        name: 'P95 RT',
        type: 'line',
        yAxisIndex: 0,
        data: p95RtData,
        connectNulls: true,
        showSymbol: false,
        smooth: true,
        itemStyle: { color: '#fac858' },
        lineStyle: { type: 'dashed' },
        markLine: p95MarkLine
      },
      {
        name: '错误率',
        type: 'line',
        yAxisIndex: 1,
        data: errorRateData,
        showSymbol: false,
        smooth: true,
        connectNulls: true,
        itemStyle: { color: '#e6a23c' }
      },
      {
        name: '并发用户数',
        type: 'line',
        yAxisIndex: 1,
        data: usersData,
        showSymbol: false,
        smooth: true,
        connectNulls: true,
        itemStyle: { color: '#ee6666' },
        lineStyle: { type: 'dotted' }
      }
    ]
  }
}

const buildHistOption = ({ enlarged = false } = {}) => {
  const sorted = [...(props.rtHistogram || [])].sort((a, b) => (a.min || 0) - (b.min || 0))
  return {
    tooltip: { trigger: 'axis' },
    grid: {
      left: '3%',
      right: '4%',
      bottom: enlarged ? '16%' : '18%',
      top: '8%',
      containLabel: true
    },
    dataZoom: dataZoomOpts(enlarged ? 28 : 8),
    xAxis: {
      type: 'category',
      data: sorted.map((b) => b.label || `${b.min}-${b.max}`),
      axisLabel: { rotate: 30 }
    },
    yAxis: { type: 'value', name: '请求数' },
    series: [
      {
        type: 'bar',
        data: sorted.map((b) => b.count || 0),
        itemStyle: { color: '#5470c6' },
        barMaxWidth: 36
      }
    ]
  }
}

const renderTrend = () => {
  if (!trendRef.value || !hasTrend.value) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendRef.value)
  trendChart.setOption(buildTrendOption())
}

const renderHist = () => {
  if (!histRef.value || !hasHist.value) return
  if (histChart) histChart.dispose()
  histChart = echarts.init(histRef.value)
  histChart.setOption(buildHistOption())
}

const renderAll = async () => {
  disposeCharts()
  await nextTick()
  renderTrend()
  renderHist()
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
  zoomChart.setOption(
    zoomKind.value === 'hist' ? buildHistOption({ enlarged: true }) : buildTrendOption({ enlarged: true })
  )
}

const onResize = () => {
  if (trendChart) trendChart.resize()
  if (histChart) histChart.resize()
  if (zoomChart) zoomChart.resize()
}

onMounted(() => {
  renderAll()
  window.addEventListener('resize', onResize)
})
watch(
  () => [props.timeSeries, props.rtHistogram, props.qps, props.p95],
  renderAll,
  { deep: true }
)
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
  disposeZoom()
})
</script>

<style scoped>
.perf-record-charts {
  margin-top: 8px;
}
.chart-block {
  margin-bottom: 16px;
}
.chart-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}
.chart-ai-note {
  font-size: 13px;
  color: #334155;
  background: #f8fafc;
  border-left: 3px solid #3b82f6;
  padding: 8px 12px;
  margin: 0 0 10px;
  line-height: 1.55;
}
.chart-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
}
.chart-box {
  height: 320px;
  width: 100%;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.chart-box.hist {
  height: 300px;
}
.chart-box.zoom {
  height: min(78vh, 720px);
  border: none;
}
</style>
