<template>
  <div class="app-report-overview">
    <h3 v-if="title" class="report-title">{{ title }}</h3>
    <div class="stat-grid" v-if="showStats || showStatus">
      <div v-if="showStatus" class="stat-card primary">
        <div class="stat-icon"><el-icon :size="22"><component :is="statusIcon" /></el-icon></div>
        <div class="stat-body">
          <div class="stat-num stat-text">{{ statusText }}</div>
          <div class="stat-label">执行状态</div>
        </div>
      </div>
      <template v-if="showStats">
      <div v-if="passRate != null" class="stat-card pass-rate primary">
        <div class="stat-icon"><el-icon :size="22"><TrendCharts /></el-icon></div>
        <div class="stat-body">
          <div class="stat-num" :style="{ color: passRateColor }">{{ Number(passRate).toFixed(2) }}%</div>
          <div class="stat-label">通过率</div>
        </div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon"><el-icon :size="22"><CircleCheck /></el-icon></div>
        <div class="stat-body">
          <div class="stat-num">{{ success ?? 0 }}</div>
          <div class="stat-label">成功</div>
        </div>
      </div>
      <div class="stat-card fail">
        <div class="stat-icon"><el-icon :size="22"><CircleClose /></el-icon></div>
        <div class="stat-body">
          <div class="stat-num">{{ fail ?? 0 }}</div>
          <div class="stat-label">失败</div>
        </div>
      </div>
      <div class="stat-card warn">
        <div class="stat-icon"><el-icon :size="22"><Warning /></el-icon></div>
        <div class="stat-body">
          <div class="stat-num">{{ error ?? 0 }}</div>
          <div class="stat-label">错误</div>
        </div>
      </div>
      <div class="stat-card info">
        <div class="stat-icon"><el-icon :size="22"><Remove /></el-icon></div>
        <div class="stat-body">
          <div class="stat-num">{{ skip ?? 0 }}</div>
          <div class="stat-label">跳过</div>
        </div>
      </div>
      </template>
    </div>
    <el-descriptions v-if="showMeta" :column="3" border size="small" class="meta-descriptions">
      <el-descriptions-item v-if="caseCount != null" label="用例数">{{ caseCount }}</el-descriptions-item>
      <el-descriptions-item v-if="duration != null" label="耗时">{{ formatDuration(duration) }}</el-descriptions-item>
      <el-descriptions-item v-if="username" label="执行人">{{ username }}</el-descriptions-item>
      <el-descriptions-item v-if="startTime" label="开始时间">{{ formattedStartTime }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CircleCheck, CircleClose, Remove, TrendCharts, Warning, Loading, Clock } from '@element-plus/icons-vue'
import dateTools from '@/tools/dateTools.js'

const props = defineProps({
  title: { type: String, default: '' },
  status: { type: String, default: '' },
  passRate: { type: Number, default: null },
  success: { type: Number, default: 0 },
  fail: { type: Number, default: 0 },
  error: { type: Number, default: 0 },
  skip: { type: Number, default: 0 },
  caseCount: { type: Number, default: null },
  duration: { type: Number, default: null },
  username: { type: String, default: '' },
  startTime: { type: [String, Date], default: '' },
  showStatus: { type: Boolean, default: true },
  showMeta: { type: Boolean, default: true },
  showStats: { type: Boolean, default: true },
})

const formattedStartTime = computed(() => (props.startTime ? dateTools.rTime(props.startTime) : ''))

const statusText = computed(() => {
  const s = String(props.status || '').toLowerCase()
  if (s === 'success' || props.status === '执行完成') return '成功'
  if (s === 'fail' || s === 'failed') return '失败'
  if (s === 'error') return '错误'
  if (s === 'running' || props.status === '执行中') return '运行中'
  return props.status || '—'
})

const statusIcon = computed(() => {
  const s = String(props.status || '').toLowerCase()
  if (s === 'success' || props.status === '执行完成') return CircleCheck
  if (s === 'fail' || s === 'failed' || s === 'error') return CircleClose
  if (s === 'running' || props.status === '执行中') return Loading
  return Clock
})

const passRateColor = computed(() => {
  const rate = Number(props.passRate) || 0
  if (rate >= 90) return 'var(--el-color-success)'
  if (rate >= 70) return 'var(--el-color-warning)'
  return 'var(--el-color-danger)'
})

function formatDuration(duration) {
  if (duration == null || duration === '') return '—'
  const d = Number(duration)
  if (Number.isNaN(d)) return String(duration)
  if (d < 1) return `${(d * 1000).toFixed(0)}ms`
  if (d < 60) return `${d.toFixed(2)}s`
  return `${Math.floor(d / 60)}m ${(d % 60).toFixed(0)}s`
}
</script>

<style scoped lang="scss">
@use '@/styles/app-report.scss';
</style>
