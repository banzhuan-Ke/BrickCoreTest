<template>
  <div class="browser-run-mode">
    <el-form-item label="执行设备" required>
      <el-select
        v-model="form.device_id"
        placeholder="请选择在线 Runner（Web 自动化）"
        filterable
        clearable
        style="width: 100%;"
        :loading="loadingDevices"
        :disabled="!defaults.runner_dispatch_enabled"
      >
        <el-option
          v-for="device in onlineDevices"
          :key="device.id"
          :label="deviceLabel(device)"
          :value="device.id"
        />
      </el-select>
      <div v-if="deviceLoadError" class="field-hint warn">{{ deviceLoadError }}</div>
      <div v-else class="field-hint">{{ runModeHint }}</div>
    </el-form-item>

    <el-form-item label="浏览器模式">
      <el-radio-group v-model="form.headless">
        <el-radio :value="true">无头模式（推荐）</el-radio>
        <el-radio :value="false">有头模式（调试）</el-radio>
      </el-radio-group>
      <div class="field-hint">
        推荐使用<strong>无头模式</strong>，资源占用低、适合服务器与批量任务。
        Runner 装在本机 Windows 且需<strong>直观看到浏览器窗口</strong>时，可临时选有头模式调试。
      </div>
    </el-form-item>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { browserLabApi } from '@/api/modules/ai.js'
import { useOnlineDevices } from '@/composables/useOnlineDevices.js'
import { browserLabDeviceLabel } from '@/views/AI/browserLab/browserLabDeviceLabel.js'

const props = defineProps({
  form: { type: Object, required: true },
})

const defaults = reactive({
  runner_dispatch_enabled: true,
})
const loadingDefaults = ref(false)

const { onlineDevices, loadingDevices, deviceLoadError, loadOnlineDevices } = useOnlineDevices()

const runModeHint = computed(() => {
  if (!defaults.runner_dispatch_enabled) {
    return 'Runner 派发未启用，请联系管理员配置 BROWSER_RUN_DISPATCH_ENABLED=1。'
  }
  return '浏览器与 Agent 在 Runner 执行机上运行，平台仅做编排与报告。'
})

function deviceLabel(device) {
  return browserLabDeviceLabel(device)
}

function ensureFormDefaults() {
  // 产品固定 Runner；后端忽略 local
  props.form.run_mode = 'runner'
  if (props.form.headless == null) {
    props.form.headless = true
  }
}

async function loadDefaults() {
  loadingDefaults.value = true
  try {
    const res = await browserLabApi.getRunDefaults()
    const data = res.data?.data || res.data || {}
    defaults.runner_dispatch_enabled = data.runner_dispatch_enabled !== false
  } catch {
    defaults.runner_dispatch_enabled = true
  } finally {
    props.form.run_mode = 'runner'
    loadingDefaults.value = false
  }
}

onMounted(async () => {
  ensureFormDefaults()
  await loadDefaults()
  await loadOnlineDevices()
})
</script>

<style scoped>
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
