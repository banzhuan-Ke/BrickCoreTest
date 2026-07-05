<template>
  <div v-if="hasInfo" class="app-env-summary">
    <el-descriptions :column="3" border size="small" title="执行环境">
      <el-descriptions-item label="引擎">
        <el-tag size="small" type="primary" effect="plain">App 自动化</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="平台">{{ platformLabel }}</el-descriptions-item>
      <el-descriptions-item label="驱动模式">{{ driverModeLabel }}</el-descriptions-item>
      <el-descriptions-item label="设备 UDID">{{ deviceUdid }}</el-descriptions-item>
      <el-descriptions-item label="应用包名">{{ appId }}</el-descriptions-item>
      <el-descriptions-item label="执行人">{{ username || '—' }}</el-descriptions-item>
      <el-descriptions-item label="开始时间">{{ startTime || '—' }}</el-descriptions-item>
      <el-descriptions-item label="隐式等待">{{ implicitWaitText }}</el-descriptions-item>
      <el-descriptions-item label="自动授权">{{ autoGrant ? '是' : '否' }}</el-descriptions-item>
      <el-descriptions-item label="录制视频">{{ recordVideo ? '是' : '否' }}</el-descriptions-item>
      <el-descriptions-item v-if="envName" label="环境">{{ envName }}</el-descriptions-item>
      <el-descriptions-item v-if="projectId" label="项目 ID">{{ projectId }}</el-descriptions-item>
      <el-descriptions-item v-if="environmentId" label="环境 ID">{{ environmentId }}</el-descriptions-item>
      <el-descriptions-item label="触发来源">{{ triggerSourceLabel }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import dateTools from '@/tools/dateTools.js'
import { APP_DRIVER_MODE_OPTIONS } from '@/datas/AppActionGroup.js'

const props = defineProps({
  env: { type: Object, default: () => ({}) },
  deviceId: { type: String, default: '' },
  username: { type: String, default: '' },
  startTime: { type: [String, Date], default: '' },
  driverMode: { type: String, default: '' },
})

const parsedEnv = computed(() => (props.env && typeof props.env === 'object' ? props.env : {}))

const hasInfo = computed(() =>
  Boolean(props.deviceId || parsedEnv.value.device_udid || props.username || parsedEnv.value.platform)
)

const deviceUdid = computed(() => parsedEnv.value.device_udid || props.deviceId || '—')

const platformLabel = computed(() => {
  const p = String(parsedEnv.value.platform || 'android').toLowerCase()
  if (p === 'android') return 'Android'
  if (p === 'ios') return 'iOS'
  return p
})

const driverModeLabel = computed(() => {
  const mode = props.driverMode || parsedEnv.value.driver_mode || ''
  const opt = APP_DRIVER_MODE_OPTIONS.find((o) => o.value === mode)
  return opt ? `${opt.label} (${mode})` : mode || '—'
})

const appId = computed(() => parsedEnv.value.app_id || '—')

const envName = computed(() => parsedEnv.value.env_name || '')

const projectId = computed(() => parsedEnv.value.project_id ?? '')

const environmentId = computed(() => parsedEnv.value.environment_id ?? '')

const TRIGGER_SOURCE_LABELS = {
  manual: '手动',
  cron: '定时任务',
  assistant: '小测',
  mcp: 'MCP',
}

const triggerSourceLabel = computed(() => {
  const code = parsedEnv.value.trigger_source || 'manual'
  return TRIGGER_SOURCE_LABELS[code] || code
})

const implicitWaitText = computed(() => {
  const v = parsedEnv.value.implicit_wait
  return v != null && v !== '' ? `${v}s` : '—'
})

const autoGrant = computed(() => Boolean(parsedEnv.value.auto_grant_permissions))

const recordVideo = computed(() => parsedEnv.value.record_video !== false)

const startTime = computed(() => (props.startTime ? dateTools.rTime(props.startTime) : ''))
</script>

<style scoped lang="scss">
@use '@/styles/app-report.scss';
</style>
