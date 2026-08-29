<template>
  <el-dialog
    v-model="visible"
    :title="context.title || '确认执行'"
    width="680px"
    destroy-on-close
    append-to-body
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <div v-loading="loading" class="exec-confirm-body">
      <template v-if="context.name">
        <div class="row">
          <span class="label">用例名称</span>
          <span class="value">{{ context.name }}</span>
        </div>
      </template>
      <div class="row">
        <span class="label">起始 URL</span>
        <span class="value mono">{{ context.startUrl || '—' }}</span>
      </div>
      <div class="row block">
        <span class="label">任务描述</span>
        <div class="task-text">{{ context.taskText || '—' }}</div>
      </div>
      <div class="row">
        <span class="label">AI 模型</span>
        <span class="value">{{ context.aiConfigLabel || '默认模型' }}</span>
      </div>
      <div class="row">
        <span class="label">执行选项</span>
        <div class="tag-row">
          <el-tag v-for="t in optionTags" :key="t" size="small" type="info">{{ t }}</el-tag>
        </div>
      </div>
      <div v-if="context.execForm?.env_id" class="row">
        <span class="label">参考环境</span>
        <span class="value">环境 #{{ context.execForm.env_id }}</span>
      </div>

      <el-divider content-position="left">执行设备</el-divider>

      <div v-if="configuredDeviceId" class="device-status-row">
        <span class="label">用例配置</span>
        <span class="value">
          {{ configuredDeviceLabel }}
          <el-tag
            :type="configuredDeviceOnline ? 'success' : 'danger'"
            size="small"
            class="status-tag"
          >
            {{ configuredDeviceOnline ? '在线' : '离线' }}
          </el-tag>
        </span>
      </div>

      <el-alert
        v-if="configuredDeviceId && !configuredDeviceOnline"
        type="warning"
        :closable="false"
        show-icon
        class="device-alert"
        title="配置的执行设备当前不在线，请选择其他在线 Runner 后再执行。"
      />

      <el-form label-width="88px" class="device-form">
        <el-form-item label="本次使用" required>
          <el-select
            v-model="selectedDeviceId"
            placeholder="请选择在线 Runner（Web 自动化）"
            filterable
            style="width: 100%;"
            :loading="loadingDevices"
            :disabled="!onlineDevices.length"
          >
            <el-option
              v-for="device in onlineDevices"
              :key="device.id"
              :label="deviceLabel(device)"
              :value="device.id"
            />
          </el-select>
          <div v-if="deviceLoadError" class="field-hint warn">{{ deviceLoadError }}</div>
          <div v-else-if="!onlineDevices.length && !loadingDevices" class="field-hint warn">
            暂无在线 Runner。请在本机运行执行器客户端并确保设备管理页显示「在线」。
          </div>
          <div v-else class="field-hint">浏览器与 Agent 在 Runner 执行机上运行，平台仅做编排与报告。</div>
        </el-form-item>
        <el-form-item label="浏览器模式">
          <el-radio-group v-model="headless">
            <el-radio :value="true">无头模式（推荐）</el-radio>
            <el-radio :value="false">有头模式（调试）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <el-alert type="info" :closable="false" show-icon title="将派发至 Runner 智能浏览器 Agent，执行过程消耗 Token。" />
    </div>

    <template #footer>
      <el-button @click="cancel">取消</el-button>
      <el-button type="primary" :disabled="!canConfirm" :loading="confirming" @click="confirm">
        开始执行
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useOnlineDevices } from '@/composables/useOnlineDevices.js'
import {
  browserLabDeviceLabel,
  findOnlineDevice,
  formatExecOptionTags,
} from './browserLabExecConfirmHelpers.js'
import { mergeBrowserLabExecForm } from './browserLabExecOptions.js'

const visible = ref(false)
const loading = ref(false)
const confirming = ref(false)
const context = ref({})
const selectedDeviceId = ref(null)
const headless = ref(true)
let pendingResolve = null

const { onlineDevices, loadingDevices, deviceLoadError, loadOnlineDevices } = useOnlineDevices()

const configuredDeviceId = computed(() => context.value.execForm?.device_id || null)
const configuredDeviceOnline = computed(() =>
  Boolean(findOnlineDevice(onlineDevices.value, configuredDeviceId.value))
)
const configuredDeviceLabel = computed(() => {
  const id = configuredDeviceId.value
  if (!id) return '未配置（执行时将选择在线设备）'
  const online = findOnlineDevice(onlineDevices.value, id)
  if (online) return deviceLabel(online)
  return `设备 ${id}（当前离线）`
})
const optionTags = computed(() => formatExecOptionTags(context.value.execForm || {}))
const canConfirm = computed(() => Boolean(selectedDeviceId.value && onlineDevices.value.length))

function deviceLabel(device) {
  return browserLabDeviceLabel(device)
}

async function open(ctx) {
  context.value = {
    title: '确认执行',
    name: '',
    startUrl: '',
    taskText: '',
    aiConfigLabel: '',
    execForm: mergeBrowserLabExecForm(),
    ...ctx,
  }
  const form = context.value.execForm || mergeBrowserLabExecForm()
  headless.value = form.headless !== false
  selectedDeviceId.value = form.device_id || null
  visible.value = true
  loading.value = true
  try {
    await loadOnlineDevices()
    const configured = configuredDeviceId.value
    const onlineMatch = findOnlineDevice(onlineDevices.value, configured)
    if (onlineMatch) {
      selectedDeviceId.value = onlineMatch.id
    } else if (onlineDevices.value.length) {
      selectedDeviceId.value = onlineDevices.value[0].id
    } else {
      selectedDeviceId.value = null
    }
  } finally {
    loading.value = false
  }
  return new Promise((resolve) => {
    pendingResolve = resolve
  })
}

function finish(result) {
  const resolve = pendingResolve
  pendingResolve = null
  visible.value = false
  resolve?.(result ?? null)
}

function cancel() {
  finish(null)
}

function confirm() {
  if (!canConfirm.value) return
  const execForm = {
    ...mergeBrowserLabExecForm(context.value.execForm),
    device_id: selectedDeviceId.value,
    headless: headless.value,
  }
  finish({
    device_id: selectedDeviceId.value,
    execForm,
  })
}

function handleClosed() {
  if (pendingResolve) finish(null)
}

defineExpose({ open })
</script>

<style scoped>
.exec-confirm-body {
  min-height: 120px;
}
.row {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 13px;
  line-height: 1.5;
}
.row.block {
  flex-direction: column;
  gap: 6px;
}
.label {
  flex: 0 0 88px;
  color: var(--el-text-color-secondary);
}
.value {
  flex: 1;
  word-break: break-all;
}
.value.mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
.task-text {
  max-height: 120px;
  overflow-y: auto;
  padding: 8px 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.55;
}
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.device-status-row {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 13px;
}
.status-tag {
  margin-left: 8px;
  vertical-align: middle;
}
.device-alert {
  margin-bottom: 12px;
}
.device-form {
  margin-bottom: 12px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.field-hint.warn {
  color: var(--el-color-warning);
}
</style>
