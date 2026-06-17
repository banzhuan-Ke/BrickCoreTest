<template>
  <div ref="wrapRef" class="mindmap-wrap" :class="{ 'is-fullscreen': isFullscreen }">
    <div class="mindmap-toolbar">
      <el-button size="small" @click="resetZoom" icon="Refresh">重置视图</el-button>
      <el-button size="small" @click="collapseToModules" :disabled="!hasData">收起到模块</el-button>
      <el-button size="small" @click="expandAllNodes" :disabled="!hasData">展开全部</el-button>
      <el-button size="small" type="primary" @click="toggleFullscreen" :icon="isFullscreen ? 'Close' : 'FullScreen'">
        {{ isFullscreen ? '退出全屏' : '全屏预览' }}
      </el-button>
      <el-button size="small" type="primary" @click="exportPng" :disabled="!hasData" icon="Picture">导出 PNG</el-button>
      <el-button size="small" type="success" @click="exportXmind" :disabled="!hasData || !reqId" icon="Download">导出 XMind</el-button>
      <span v-if="total != null && total > 0" class="stat-tag">{{ total }} 条测试点</span>
      <span v-if="!hasData" class="empty-hint">暂无测试点，请先生成</span>
      <span v-else class="zoom-hint">滚轮缩放 · 拖拽平移 · 点击节点展开/折叠</span>
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
  loading: { type: Boolean, default: false },
  total: { type: Number, default: null }
})

const emit = defineEmits(['node-click'])

const wrapRef = ref(null)
const chartRef = ref(null)
const isFullscreen = ref(false)
let chart = null
let expandDepth = 3

const hasData = computed(() => {
  const d = props.treeData
  return d && (d.children?.length > 0 || d.name)
})

function countPoints(node) {
  if (!node) return 0
  let n = node.value?.point_id ? 1 : 0
  for (const c of node.children || []) n += countPoints(c)
  return n
}

function inferExpandDepth(pointCount) {
  if (pointCount <= 20) return 4
  if (pointCount <= 60) return 3
  return 2
}

function truncateLabel(name, maxLen) {
  const text = name || ''
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text
}

function cloneTreeData(data) {
  return JSON.parse(JSON.stringify(data))
}

function applyCollapseDepth(node, depth = 0, maxDepth = expandDepth) {
  if (!node?.children?.length) return
  node.collapsed = depth >= maxDepth
  node.children.forEach(child => applyCollapseDepth(child, depth + 1, maxDepth))
}

function applyExpandAll(node) {
  if (!node?.children?.length) return
  node.collapsed = false
  node.children.forEach(applyExpandAll)
}

function buildOption(data) {
  const pointCount = countPoints(data)
  const manyLeaves = pointCount > 40
  const leafFontSize = manyLeaves ? 10 : 11
  const branchFontSize = manyLeaves ? 12 : 13

  return {
    tooltip: {
      trigger: 'item',
      confine: true,
      extraCssText: 'max-width: 420px; white-space: normal; word-break: break-all;',
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
      top: '1%',
      left: '4%',
      bottom: '1%',
      right: manyLeaves ? '38%' : '24%',
      symbol: 'emptyCircle',
      symbolSize: 7,
      orient: 'LR',
      roam: true,
      expandAndCollapse: true,
      initialTreeDepth: expandDepth,
      label: {
        position: 'left',
        verticalAlign: 'middle',
        align: 'right',
        fontSize: branchFontSize,
        distance: 6,
        formatter: ({ name, data: nodeData }) => {
          const isLeaf = !nodeData?.children?.length
          return truncateLabel(name, isLeaf ? 26 : 36)
        }
      },
      leaves: {
        label: {
          position: 'right',
          verticalAlign: 'middle',
          align: 'left',
          fontSize: leafFontSize,
          color: '#606266',
          lineHeight: manyLeaves ? 14 : 16,
          formatter: ({ name }) => truncateLabel(name, 26)
        }
      },
      lineStyle: { color: '#c0c4cc', width: 1.2, curveness: 0.45 },
      emphasis: { focus: 'descendant', blurScope: 'coordinateSystem' },
      animationDuration: 350,
      animationDurationUpdate: 500
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
  const pointCount = countPoints(props.treeData)
  expandDepth = inferExpandDepth(pointCount)
  const data = cloneTreeData(props.treeData)
  applyCollapseDepth(data, 0, expandDepth)
  chart.setOption(buildOption(data), true)
  chart.resize()
}

function resetZoom() {
  if (!chart || !props.treeData) return
  expandDepth = inferExpandDepth(countPoints(props.treeData))
  renderChart()
}

function collapseToModules() {
  if (!chart || !props.treeData) return
  expandDepth = 2
  renderChart()
}

function expandAllNodes() {
  if (!chart || !props.treeData) return
  expandDepth = 99
  const data = cloneTreeData(props.treeData)
  applyExpandAll(data)
  chart.setOption(buildOption(data), true)
  chart.resize()
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

function onFullscreenKeydown(e) {
  if (e.key === 'Escape' && isFullscreen.value) {
    isFullscreen.value = false
  }
}

watch(isFullscreen, async (v) => {
  document.body.style.overflow = v ? 'hidden' : ''
  if (v) document.addEventListener('keydown', onFullscreenKeydown)
  else document.removeEventListener('keydown', onFullscreenKeydown)
  await nextTick()
  chart?.resize()
})

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
  document.removeEventListener('keydown', onFullscreenKeydown)
  document.body.style.overflow = ''
  chart?.dispose()
  chart = null
})

defineExpose({ exportPng, exportXmind, resetZoom, toggleFullscreen })
</script>

<style scoped>
.mindmap-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 480px;
}
.mindmap-wrap.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 2100;
  background: #fff;
  padding: 16px 20px;
  min-height: 0;
}
.mindmap-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.stat-tag {
  font-size: 12px;
  color: #409eff;
  background: #ecf5ff;
  padding: 2px 8px;
  border-radius: 4px;
}
.empty-hint {
  color: #909399;
  font-size: 13px;
  margin-left: 4px;
}
.zoom-hint {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}
.mindmap-chart {
  flex: 1;
  min-height: 440px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
.is-fullscreen .mindmap-chart {
  min-height: 0;
}
</style>
