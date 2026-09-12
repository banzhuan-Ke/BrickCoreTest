<template>
  <div v-if="hasData" class="perf-ladder-charts">
    <div class="ladder-head">
      <h4 class="ladder-sub">趋势图（横轴=并发）</h4>
      <p class="ladder-hint">成功率柱状：≥95% 偏绿，&lt;80% 偏红；折线为各档实测值。</p>
    </div>
    <div class="chart-block">
      <div class="chart-label">请求成功率</div>
      <div ref="okRef" class="chart-box" />
    </div>
    <div class="chart-block">
      <div class="chart-label">平均 / P95 响应时间</div>
      <div ref="rtRef" class="chart-box" />
    </div>
    <div class="chart-block">
      <div class="chart-label">QPS</div>
      <div ref="qpsRef" class="chart-box" />
    </div>
    <div v-if="hasFirst" class="chart-block">
      <div class="chart-label">{{ phaseFirstLabel }}</div>
      <div ref="firstRef" class="chart-box" />
    </div>
    <div v-if="hasTotal" class="chart-block">
      <div class="chart-label">{{ phaseTotalLabel }}</div>
      <div ref="totalRef" class="chart-box" />
    </div>
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
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  ladder: { type: Object, default: null },
})

const okRef = ref(null)
const rtRef = ref(null)
const qpsRef = ref(null)
const firstRef = ref(null)
const totalRef = ref(null)
let charts = []

const series = computed(() => props.ladder?.chart_series || {})
const x = computed(() => series.value.x || [])
const hasData = computed(() => x.value.length >= 2)
const hasFirst = computed(() => (series.value.phase_first_mean || []).some((v) => v != null))
const hasTotal = computed(() => (series.value.phase_total_mean || []).some((v) => v != null))
const phaseFirstLabel = computed(() => props.ladder?.phase_first_label || '首字/首 token')
const phaseTotalLabel = computed(() => props.ladder?.phase_total_label || '整体流式耗时')

const successRates = computed(() => {
  const sr = series.value.success_rate
  if (sr && sr.length) return sr
  return (series.value.error_rate || []).map((v) =>
    Math.round(Math.max(0, Math.min(100, 100 - Number(v || 0))) * 100) / 100
  )
})

function disposeAll() {
  charts.forEach((c) => {
    try {
      c.dispose()
    } catch {
      /* ignore */
    }
  })
  charts = []
}

function initBar(el, data, name) {
  if (!el) return
  const chart = echarts.init(el)
  charts.push(chart)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 28, bottom: 36 },
    xAxis: { type: 'category', name: '并发', data: x.value.map(String) },
    yAxis: { type: 'value', name, min: 0, max: 100 },
    series: [{
      name,
      type: 'bar',
      data,
      barMaxWidth: 36,
      itemStyle: {
        color: (p) => {
          const n = Number(p.value) || 0
          if (n >= 95) return '#38a169'
          if (n < 80) return '#e53e3e'
          return '#dd6b20'
        },
      },
    }],
  })
}

function initLine(el, seriesList, yName) {
  if (!el) return
  const chart = echarts.init(el)
  charts.push(chart)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 56, right: 24, top: 36, bottom: 36 },
    xAxis: { type: 'category', name: '并发', data: x.value.map(String) },
    yAxis: { type: 'value', name: yName || '', min: 0 },
    series: seriesList.map((s) => ({
      name: s.name,
      type: 'line',
      data: s.data,
      smooth: true,
      showSymbol: true,
      symbolSize: 8,
      itemStyle: { color: s.color },
      lineStyle: { width: 2.5, color: s.color },
    })),
  })
}

function render() {
  disposeAll()
  if (!hasData.value) return
  initBar(okRef.value, successRates.value, '成功率(%)')
  initLine(rtRef.value, [
    { name: 'Avg (ms)', data: series.value.avg_rt_ms || [], color: '#3182ce' },
    { name: 'P95 (ms)', data: series.value.p95_rt_ms || [], color: '#dd6b20' },
  ], 'ms')
  initLine(qpsRef.value, [
    { name: 'QPS', data: series.value.qps || [], color: '#805ad5' },
  ], 'QPS')
  if (hasFirst.value) {
    initLine(firstRef.value, [
      { name: phaseFirstLabel.value, data: series.value.phase_first_mean || [], color: '#e53e3e' },
    ], 's')
  }
  if (hasTotal.value) {
    initLine(totalRef.value, [
      { name: phaseTotalLabel.value, data: series.value.phase_total_mean || [], color: '#9b59b6' },
    ], 's')
  }
}

onMounted(() => nextTick(render))
onBeforeUnmount(disposeAll)
watch(() => props.ladder, () => nextTick(render), { deep: true })
</script>

<style scoped>
.perf-ladder-charts { margin-top: 12px; }
.ladder-sub { margin: 0 0 4px; font-size: 14px; color: #334155; }
.ladder-hint { margin: 0 0 12px; font-size: 12px; color: #64748b; }
.chart-block { margin-bottom: 14px; }
.chart-label { font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 6px; }
.chart-box { width: 100%; height: 280px; }
</style>
