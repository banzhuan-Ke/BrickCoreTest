<template>
  <div class="mindmap-wrap">
    <div class="mindmap-toolbar">
      <el-button size="small" @click="resetZoom" icon="Refresh">重置视图</el-button>
      <el-button size="small" type="primary" @click="exportPng" :disabled="!hasData" icon="Picture">导出 PNG</el-button>
      <el-button size="small" type="success" @click="exportXmind" :disabled="!hasData || !reqId" icon="Download">导出 XMind</el-button>
      <span v-if="!hasData" class="empty-hint">暂无测试点，请先生成</span>
    </div>
    <div ref="chartRef" class="mindmap-chart" v-loading="loading"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { aiTestAnalysisApi } from '@/api/modules/ai'

const props = defineProps({
  treeData: { type: Object, default: null },
  reqId: { type: Number, default: null },
  projectId: { type: Number, default: null },
  exportParams: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits(['node-click'])

const chartRef = ref(null)
let chart = null

const hasData = computed(() => {
  const d = props.treeData
  return d && (d.children?.length > 0 || d.name)
})

function buildOption(data) {
  return {
    tooltip: {
      trigger: 'item',
      formatter(params) {
        const v = params.data?.value || {}
        if (v.point_id) {
          const lines = [
            `<b>${v.title || params.name}</b>`,
            v.test_type ? `类型：${v.test_type}` : '',
            v.priority ? `优先级：${v.priority}` : '',
            v.status ? `状态：${v.status}` : '',
            v.description ? `说明：${v.description}` : ''
          ].filter(Boolean)
          return lines.join('<br/>')
        }
        return params.name
      }
    },
    series: [{
      type: 'tree',
      data: [data],
      top: '2%',
      left: '8%',
      bottom: '2%',
      right: '22%',
      symbol: 'emptyCircle',
      symbolSize: 8,
      orient: 'LR',
      expandAndCollapse: true,
      initialTreeDepth: 4,
      label: {
        position: 'left',
        verticalAlign: 'middle',
        align: 'right',
        fontSize: 12,
        distance: 8
      },
      leaves: {
        label: {
          position: 'right',
          verticalAlign: 'middle',
          align: 'left',
          color: '#303133'
        }
      },
      lineStyle: { color: '#c0c4cc', width: 1.5, curveness: 0.5 },
      emphasis: { focus: 'descendant' },
      animationDuration: 450,
      animationDurationUpdate: 650
    }]
  }
}

function renderChart() {
  if (!chartRef.value || !props.treeData) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params) => {
      const v = params.data?.value
      if (v?.point_id) emit('node-click', v)
    })
  }
  chart.setOption(buildOption(JSON.parse(JSON.stringify(props.treeData))), true)
  chart.resize()
}

function resetZoom() {
  if (!chart || !props.treeData) return
  chart.setOption(buildOption(JSON.parse(JSON.stringify(props.treeData))), true)
}

function exportPng() {
  if (!chart) {
    ElMessage.warning('暂无导图可导出')
    return
  }
  const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
  const a = document.createElement('a')
  a.href = url
  a.download = `test_points_mindmap_${props.reqId || 'export'}.png`
  a.click()
  ElMessage.success('PNG 已下载')
}

async function exportXmind() {
  if (!props.reqId || !props.projectId) return
  try {
    const blob = await aiTestAnalysisApi.exportXmindBlob(props.reqId, props.projectId, props.exportParams || {})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `test_points_${props.reqId}.xmind`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('XMind 已下载')
  } catch (e) {
    ElMessage.error(e?.message || 'XMind 导出失败')
  }
}

function handleResize() {
  chart?.resize()
}

watch(() => props.treeData, async () => {
  await nextTick()
  renderChart()
}, { deep: true })

onMounted(() => {
  window.addEventListener('resize', handleResize)
  nextTick(() => renderChart())
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})

defineExpose({ exportPng, exportXmind, resetZoom })
</script>

<style scoped>
.mindmap-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 420px;
}
.mindmap-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.empty-hint {
  color: #909399;
  font-size: 13px;
  margin-left: 8px;
}
.mindmap-chart {
  flex: 1;
  min-height: 400px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
</style>
