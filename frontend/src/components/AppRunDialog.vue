<template>
  <el-dialog
    :model-value="modelValue"
    title="App 运行配置"
    width="640px"
    destroy-on-close
    class="bc-dialog"
    @close="emit('update:modelValue', false)"
  >
    <div class="bc-dialog-body">
      <section class="bc-dialog-section">
        <div class="bc-dialog-section__title">执行配置</div>
        <el-form label-width="96px" class="bc-dialog-form ui-run-config-form">
      <el-form-item label="运行环境" required>
        <UiRunEnvSelect v-model="form.env_id" />
      </el-form-item>
      <el-form-item label="执行设备" required>
        <template v-if="parallel">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="ui-run-parallel-hint"
            title="并行模式：按权重将套件分到多台 App Runner（一 UDID 一锁，每台仅跑一个套件）。"
          />
          <el-table :data="deviceRows" size="small" class="ui-run-device-table" border table-layout="fixed">
            <el-table-column label="选用" width="52" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.selected" />
              </template>
            </el-table-column>
            <el-table-column label="执行器" min-width="168">
              <template #default="{ row }">
                <div class="ui-run-device-table__name">{{ row.name || row.username }}</div>
                <div class="ui-run-device-table__ip">{{ row.app_udid || row.id }}</div>
              </template>
            </el-table-column>
            <el-table-column label="权重" width="108" align="center">
              <template #default="{ row }">
                <el-input-number v-model="row.weight" :min="1" :max="100" size="small" :disabled="!row.selected" controls-position="right" />
              </template>
            </el-table-column>
          </el-table>
        </template>
        <template v-else>
          <el-select v-model="form.device_id" placeholder="选择支持 App 的在线 Runner" filterable style="width: 100%">
            <el-option
              v-for="d in appDevices"
              :key="d.id"
              :label="`${d.name || d.username} (${d.app_udid || d.id})`"
              :value="d.id"
            />
          </el-select>
          <el-text v-if="!appDevices.length" type="warning" size="small">暂无支持 App 的在线执行器</el-text>
        </template>
      </el-form-item>
      <el-form-item label="设备 UDID">
        <el-input v-model="form.app_udid" placeholder="留空则使用设备登记值" />
      </el-form-item>
      <el-form-item label="应用包名">
        <el-input v-model="form.app_id" placeholder="默认启动包名（可选）" />
      </el-form-item>
      <el-form-item label="隐式等待">
        <el-input-number v-model="form.implicit_wait" :min="1" :max="120" />
      </el-form-item>
      <el-form-item v-if="showHealToggle" label="AI 自愈">
        <div v-if="healOverrideAllowed" class="heal-segments">
          <div
            :class="['ui-run-segment', 'ui-run-segment--grow', { active: form.ai_heal_enabled === true }]"
            @click="form.ai_heal_enabled = true"
          >
            开启
          </div>
          <div
            :class="['ui-run-segment', 'ui-run-segment--grow', { active: form.ai_heal_enabled === false }]"
            @click="form.ai_heal_enabled = false"
          >
            关闭
          </div>
        </div>
        <el-text v-else type="info" size="small">
          本次将按项目默认：{{ healRunOptions?.locator_heal_default_on_execute ? '开启' : '关闭' }}自愈
        </el-text>
        <el-text v-if="healOverrideAllowed" type="info" size="small">步骤失败时自动尝试 AI 修复定位器</el-text>
      </el-form-item>
      <el-form-item label="选项">
        <div class="run-options">
          <el-checkbox v-model="form.no_reset">
            不重置应用
            <el-tooltip content="保持应用当前数据与登录状态，执行前不清除缓存、不强制重装；适合连续调试、免重复登录。取消勾选将在启动前清除应用数据（需用例含「启动应用」步骤）。" placement="top">
              <el-icon class="option-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-checkbox>
          <el-checkbox v-model="form.auto_grant_permissions">
            自动授权
            <el-tooltip content="执行时尽量自动处理 Android 运行时权限弹窗（如存储、相机、麦克风等），减少人工点「允许」。部分系统弹窗仍可能需要手动确认。" placement="top">
              <el-icon class="option-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-checkbox>
          <el-checkbox v-model="form.record_video">
            录制用例视频
            <el-tooltip content="为用例执行过程录制屏幕视频，并附在测试报告中。" placement="top">
              <el-icon class="option-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-checkbox>
        </div>
      </el-form-item>
      <IncludeQuarantineCheckbox v-if="showIncludeQuarantine" v-model="form.include_quarantine" />
        </el-form>
      </section>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">运行</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import UiRunEnvSelect from '@/components/UiRunEnvSelect.vue'
import IncludeQuarantineCheckbox from '@/components/IncludeQuarantineCheckbox.vue'
import { deviceApi } from '@/api'
import { aiConfigApi } from '@/api/modules/ai'
import { UserStore } from '@/stores/module/UserStore'
import { ProjectStore } from '@/stores/module/ProjectStore'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  defaultRecordVideo: { type: Boolean, default: true },
  parallel: { type: Boolean, default: false },
  showIncludeQuarantine: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'submit'])

const uStore = UserStore()
const proStore = ProjectStore()
const devices = ref([])
const deviceRows = ref([])
const healRunOptions = ref(null)

const form = reactive({
  env_id: '',
  device_id: '',
  username: uStore.userInfo?.username || '',
  app_udid: '',
  app_id: '',
  implicit_wait: 10,
  no_reset: true,
  auto_grant_permissions: true,
  record_video: true,
  ai_heal_enabled: true,
  include_quarantine: false,
})

const showHealToggle = computed(() => healRunOptions.value?.locator_heal_enabled === true)

const healOverrideAllowed = computed(() => healRunOptions.value?.locator_heal_allow_run_override === true)

const appDevices = computed(() =>
  (devices.value || []).filter((d) => {
    const types = d.runner_engine_types || ['web']
    return d.status === '在线' && types.includes('app')
  })
)

function syncDeviceRows() {
  deviceRows.value = appDevices.value.map((d) => ({
    ...d,
    selected: true,
    weight: 1,
  }))
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
      form.ai_heal_enabled = healRunOptions.value?.locator_heal_default_on_execute ?? true
    }
  } catch {
    healRunOptions.value = null
  }
}

async function loadDevices() {
  try {
    const res = await deviceApi.getList({ page: 1, size: 200, status: '在线' })
    devices.value = res.data?.data || res.data || []
    syncDeviceRows()
  } catch {
    devices.value = []
    deviceRows.value = []
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    form.username = uStore.userInfo?.username || ''
    form.env_id = ''
    form.device_id = ''
    form.app_udid = ''
    form.app_id = ''
    form.implicit_wait = 10
    form.no_reset = true
    form.auto_grant_permissions = true
    form.record_video = props.defaultRecordVideo
    form.ai_heal_enabled = true
    form.include_quarantine = false
    loadHealRunOptions()
    loadDevices()
  }
)

function submit() {
  if (!form.env_id) {
    ElMessage.warning('请选择运行环境')
    return
  }
  const payload = { ...form }
  if (props.parallel) {
    const selected = deviceRows.value.filter((r) => r.selected)
    if (!selected.length) {
      ElMessage.warning('请至少选择一台 App 执行器')
      return
    }
    payload.devices = selected.map((r) => ({ device_id: r.id, weight: r.weight, concurrency: 1 }))
    payload.device_id = ''
  } else if (!form.device_id) {
    ElMessage.warning('请选择执行设备')
    return
  }
  if (!showHealToggle.value) {
    delete payload.ai_heal_enabled
  } else if (!healOverrideAllowed.value) {
    delete payload.ai_heal_enabled
  }
  if (!props.showIncludeQuarantine) {
    delete payload.include_quarantine
  }
  emit('submit', { ...payload, trigger_source: 'manual' })
}
</script>

<style scoped lang="scss">
@use '@/style/ui-run-config.scss';

.run-options {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.heal-segments {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}

.option-help {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  vertical-align: middle;
  cursor: help;
}
</style>
