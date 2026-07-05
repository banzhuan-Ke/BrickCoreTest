<template>
  <el-dialog
    v-model="visibleProxy"
    :title="`调试至第 ${throughIndex + 1} 步`"
    width="780px"
    destroy-on-close
    @open="onOpen"
    @closed="resetState"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="stepHint"
      style="margin-bottom: 16px;"
    />
    <div class="run-config-container">
      <div class="config-section">
        <div class="section-title"><span>运行环境</span></div>
        <div class="env-cards">
          <div
            v-for="env in proStore.envList"
            :key="env.id"
            :class="['env-card', { active: params.env_id === env.id }]"
            @click="params.env_id = env.id"
          >
            <div class="env-name">{{ env.name }}</div>
            <div class="env-host">{{ env.host }}</div>
          </div>
        </div>
      </div>
      <div class="config-section">
        <div class="section-title"><span>App 执行器</span></div>
        <el-select v-model="params.device_id" placeholder="请选择支持 App 的在线 Runner" style="width: 100%;">
          <el-option
            v-for="device in deviceList"
            :key="device.id"
            :label="`${device.name || device.username} (${device.app_udid || device.id})`"
            :value="device.id"
          />
        </el-select>
      </div>
      <div class="config-section">
        <div class="section-title"><span>设备 UDID</span></div>
        <el-input v-model="params.app_udid" placeholder="留空则使用设备登记值" />
      </div>
      <div class="config-section">
        <div class="section-title"><span>应用包名</span></div>
        <el-input v-model="params.app_id" placeholder="默认启动包名（可选）" />
      </div>
      <div v-if="showHealToggle" class="config-section">
        <div class="section-title"><span>AI 自愈</span></div>
        <div v-if="healOverrideAllowed" class="heal-segments">
          <div
            :class="['heal-segment', { active: params.ai_heal_enabled === true }]"
            @click="params.ai_heal_enabled = true"
          >
            开启
          </div>
          <div
            :class="['heal-segment', { active: params.ai_heal_enabled === false }]"
            @click="params.ai_heal_enabled = false"
          >
            关闭
          </div>
        </div>
        <el-text v-else type="info" size="small">
          本次将按项目默认：{{ healRunOptions?.locator_heal_default_on_execute ? '开启' : '关闭' }}自愈
        </el-text>
      </div>
    </div>

    <div v-if="debugResult" class="debug-result">
      <div class="result-head">
        <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>
        <span class="result-meta">执行记录 #{{ debugResult.id }}</span>
      </div>
      <CaseReportTimeline v-if="debugResult.result_data" :runInfo="debugResult.result_data" profile="app" />
    </div>

    <template #footer>
      <el-button @click="visibleProxy = false">关闭</el-button>
      <el-button type="primary" :loading="running" @click="startDebug">开始调试</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, onBeforeUnmount } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { appExecApi, appRecordApi, deviceApi } from '@/api'
import { aiConfigApi } from '@/api/modules/ai'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import { filterAppRunnerDevices } from '@/utils/runnerDevice'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  caseId: { type: [String, Number], required: true },
  steps: { type: Array, default: () => [] },
  throughIndex: { type: Number, default: 0 },
  driverMode: { type: String, default: 'hybrid' },
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const uStore = UserStore()

const visibleProxy = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const running = ref(false)
const deviceList = ref([])
const debugResult = ref(null)
const pollTimer = ref(null)
const healRunOptions = ref(null)

const showHealToggle = computed(() => healRunOptions.value?.locator_heal_enabled === true)
const healOverrideAllowed = computed(() => healRunOptions.value?.locator_heal_allow_run_override === true)

const params = reactive({
  env_id: '',
  device_id: '',
  app_udid: '',
  app_id: '',
  implicit_wait: 10,
  no_reset: true,
  auto_grant_permissions: true,
  record_video: true,
  ai_heal_enabled: true,
  username: uStore.userInfo?.username || '',
})

const stepHint = computed(() => {
  const step = props.steps[props.throughIndex]
  const label = step?.desc || step?.keyword || `步骤 ${props.throughIndex + 1}`
  return `将执行第 1～${props.throughIndex + 1} 步（含「${label}」），使用当前编辑器步骤（无需先保存）`
})

const statusLabel = computed(() => {
  const s = debugResult.value?.status
  const map = {
    running: '运行中',
    success: '成功',
    fail: '失败',
    failed: '失败',
    error: '错误',
    skip: '跳过',
    no_run: '未运行',
  }
  return map[s] || s || '—'
})

const statusTagType = computed(() => {
  const s = debugResult.value?.status
  if (s === 'success') return 'success'
  if (s === 'running') return 'primary'
  if (s === 'skip') return 'warning'
  return 'danger'
})

const onOpen = async () => {
  params.env_id = proStore.envList?.[0]?.id || ''
  params.device_id = ''
  params.app_udid = ''
  params.app_id = ''
  params.username = uStore.userInfo?.username || ''
  debugResult.value = null
  await Promise.all([loadDevices(), loadHealRunOptions()])
}

async function loadHealRunOptions() {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    healRunOptions.value = null
    return
  }
  try {
    const res = await aiConfigApi.getExecutionSettings(pid)
    if (res.data?.code === 200) {
      healRunOptions.value = res.data.data || null
      params.ai_heal_enabled = healRunOptions.value?.locator_heal_default_on_execute ?? true
    }
  } catch {
    healRunOptions.value = null
  }
}

const loadDevices = async () => {
  try {
    const res = await deviceApi.getList({ page: 1, size: 200, status: '在线' })
    const rows = res.data?.data || res.data || []
    deviceList.value = filterAppRunnerDevices(rows)
    if (!params.device_id && deviceList.value.length) {
      params.device_id = deviceList.value[0].id
    }
  } catch {
    deviceList.value = []
  }
}

const stopPoll = () => {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

const pollExecution = (executionId) => {
  stopPoll()
  pollTimer.value = setInterval(async () => {
    try {
      const res = await appRecordApi.caseDetail(executionId)
      if (res.status !== 200) return
      debugResult.value = res.data?.data ?? res.data
      if (debugResult.value?.status && debugResult.value.status !== 'running') {
        stopPoll()
        running.value = false
      }
    } catch {
      stopPoll()
      running.value = false
    }
  }, 2000)
}

const startDebug = async () => {
  if (!props.steps?.length) {
    ElMessage.warning('请先添加步骤')
    return
  }
  if (!params.env_id) {
    ElMessage.warning('请选择运行环境')
    return
  }
  if (!params.device_id) {
    ElMessage.warning('请选择 App 执行器')
    return
  }

  running.value = true
  debugResult.value = null
  try {
    const payload = {
      ...params,
      steps: props.steps,
      through_index: props.throughIndex,
      driver_mode: props.driverMode || 'hybrid',
      trigger_source: 'manual',
    }
    if (!showHealToggle.value || !healOverrideAllowed.value) {
      delete payload.ai_heal_enabled
    }
    const res = await appExecApi.debugCase(props.caseId, payload)
    if (res.status === 201) {
      const executionId = res.data?.execution_id
      ElNotification.success({
        title: '调试任务已提交',
        message: res.data?.msg || '正在 App Runner 上执行',
        duration: 2000,
      })
      if (executionId) {
        const detail = await appRecordApi.caseDetail(executionId)
        if (detail.status === 200) {
          debugResult.value = detail.data?.data ?? detail.data
        }
        if (debugResult.value?.status === 'running') {
          pollExecution(executionId)
        } else {
          running.value = false
        }
      } else {
        running.value = false
      }
    } else {
      running.value = false
      ElMessage.error(res.data?.detail || '提交调试失败')
    }
  } catch (e) {
    running.value = false
    ElMessage.error(e?.response?.data?.detail || '提交调试失败')
  }
}

const resetState = () => {
  stopPoll()
  running.value = false
  debugResult.value = null
}

onBeforeUnmount(() => {
  stopPoll()
})
</script>

<style scoped lang="scss">
.run-config-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-section {
  .section-title {
    font-weight: 500;
    margin-bottom: 8px;
  }
}

.env-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.env-card {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 8px 12px;
  cursor: pointer;
  min-width: 120px;

  &.active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  .env-name {
    font-weight: 500;
    font-size: 13px;
  }

  .env-host {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.debug-result {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color);

  .result-head {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  .result-meta {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.heal-segments {
  display: flex;
  gap: 8px;
}

.heal-segment {
  flex: 1;
  text-align: center;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;

  &.active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
  }
}
</style>
