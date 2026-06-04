<template>
  <el-dialog
    v-model="visible"
    title="🎬 功能用例 → 录制 UI 自动化"
    width="760px"
    destroy-on-close
    :close-on-click-modal="false"
    append-to-body
    @closed="handleClosed"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px;"
      :title="`功能用例：${functionalCase?.title || '—'}`"
    />

    <FunctionalCaseUiContext v-model="uiContext" mode="record" :project-id="projectId" />

    <el-form label-width="110px" class="record-meta">
      <el-form-item label="执行设备" required>
        <el-select
          v-model="deviceId"
          placeholder="选择在线 Runner 设备"
          style="width: 100%;"
          :loading="loadingDevices"
          filterable
        >
          <el-option
            v-for="d in onlineDevices"
            :key="d.id"
            :label="`${d.name || d.id} (${d.ip || '未知IP'})`"
            :value="d.id"
          />
        </el-select>
        <div class="field-hint">录制由 Runner 在本机弹出浏览器执行，需先启动 runner/main.py</div>
        <el-alert
          v-if="deviceLoadError"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 8px;"
        >
          <template #title>{{ deviceLoadError }}</template>
          <div class="runner-tip">
            在 <code>runner</code> 目录双击 <code>start-local.bat</code> 或 <code>start-online.bat</code> 切换配置后运行 <code>python main.py</code>，
            设备管理页显示「在线」后即可选择。
          </div>
        </el-alert>
      </el-form-item>
      <el-form-item label="悬浮停留时间">
        <el-slider
          v-model="hoverDelayMs"
          :min="500"
          :max="5000"
          :step="500"
          show-stops
          style="max-width: 420px;"
        />
        <div class="field-hint">
          悬浮操作需在元素上方停留 {{ hoverDelayMs / 1000 }} 秒才会被录制（500ms～5s 可调）
        </div>
      </el-form-item>
      <el-form-item label="UI 用例名称">
        <el-input v-model="caseName" maxlength="50" show-word-limit />
      </el-form-item>
      <el-form-item label="用例等级">
        <el-select v-model="caseLevel" style="width: 120px;">
          <el-option label="P0" value="P0" />
          <el-option label="P1" value="P1" />
          <el-option label="P2" value="P2" />
          <el-option label="P3" value="P3" />
        </el-select>
      </el-form-item>
    </el-form>

    <el-alert type="success" :closable="false" show-icon>
      <template #title>
        录制流程：Runner 打开目标页 → 您手动登录并进入业务模块 → 操作功能步骤 → 停止录制 → 导入 UI 用例库
      </template>
    </el-alert>

    <UiCaseRecorder
      ref="recorderRef"
      v-model="recorderVisible"
      :key="recorderKey"
      preset-mode
      skip-config
      apply-label="导入 UI 用例库"
      :initial-url="recorderStartUrl"
      :initial-description="recordDescription"
      :preset-device-id="deviceId"
      :initial-hover-delay-ms="hoverDelayMs"
      @apply="handleRecordApply"
    />

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button link type="primary" @click="loadOnlineDevices">刷新设备</el-button>
      <el-button type="primary" :disabled="!onlineDevices.length" :loading="startingRecord" @click="openRecorder">
        开始录制
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import FunctionalCaseUiContext from '@/views/AI/components/FunctionalCaseUiContext.vue'
import UiCaseRecorder from '@/views/AI/components/UiCaseRecorder.vue'
import { aiFunctionalCaseApi } from '@/api/modules/ai.js'
import { useOnlineDevices } from '@/composables/useOnlineDevices.js'

const props = defineProps({
  modelValue: Boolean,
  functionalCase: { type: Object, default: null },
  projectId: { type: [Number, String], required: true }
})

const emit = defineEmits(['update:modelValue', 'done'])

const defaultUiContext = () => ({
  page_url: ''
})

const visible = ref(false)
const recorderVisible = ref(false)
const recorderRef = ref(null)
const recorderKey = ref(0)
const recorderStartUrl = ref('')
const deviceId = ref('')
const hoverDelayMs = ref(1000)
const startingRecord = ref(false)
const importing = ref(false)
const uiContext = reactive(defaultUiContext())
const caseName = ref('')
const caseLevel = ref('P2')

const { onlineDevices, loadingDevices, deviceLoadError, loadOnlineDevices } = useOnlineDevices()

const priorityToLevel = (p) => ({ 1: 'P0', 2: 'P1', 3: 'P2', 4: 'P3' }[String(p || '2')] || 'P2')

const buildDescription = (fc) => {
  if (!fc) return ''
  const parts = []
  if (fc.title) parts.push(`【用例】${fc.title}`)
  if (fc.precondition) parts.push(`【前置条件】${fc.precondition}`)
  const steps = fc.steps || []
  if (steps.length) {
    parts.push('【测试步骤与预期】')
    steps.forEach((st, i) => {
      const step = (st.step || '').trim()
      const expect = (st.expect || '').trim()
      if (!step && !expect) return
      let line = `${i + 1}. ${step || '（无步骤描述）'}`
      if (expect) line += ` → 预期：${expect}`
      parts.push(line)
    })
  }
  if (uiContext.page_url?.trim()) {
    parts.push(`【目标页面】${uiContext.page_url.trim()}`)
  }
  parts.push('【录制说明】登录与前置导航由人工在浏览器中完成；可在下方测试描述中补充业务背景，供 AI 优化使用。')
  return parts.join('\n\n').slice(0, 2000)
}

const recordDescription = computed(() => buildDescription(props.functionalCase))

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val && props.functionalCase) {
    Object.assign(uiContext, defaultUiContext())
    caseName.value = (props.functionalCase.title || 'UI用例').slice(0, 50)
    caseLevel.value = priorityToLevel(props.functionalCase.priority)
    hoverDelayMs.value = 1000
    deviceId.value = ''
    const list = await loadOnlineDevices()
    if (list.length === 1) deviceId.value = list[0].id
  }
})

watch(visible, (val) => emit('update:modelValue', val))

const validateContext = () => {
  if (!uiContext.page_url?.trim()) {
    ElMessage.warning('请填写目标页面 URL')
    return false
  }
  if (!deviceId.value) {
    ElMessage.warning('请选择在线 Runner 执行设备')
    return false
  }
  return true
}

const openRecorder = async () => {
  if (!props.functionalCase?.id) {
    ElMessage.warning('功能用例无效')
    return
  }
  if (!validateContext()) return
  startingRecord.value = true
  recorderStartUrl.value = uiContext.page_url.trim()
  recorderKey.value += 1
  await nextTick()
  recorderVisible.value = true
  startingRecord.value = false
}

const handleRecordApply = async (steps) => {
  if (!steps?.length) {
    ElMessage.warning('没有可导入的步骤')
    return
  }
  if (!validateContext()) return
  importing.value = true
  try {
    const rid = recorderRef.value?.recordId
    const recordId = typeof rid === 'object' && rid !== null && 'value' in rid ? rid.value : rid
    const res = await aiFunctionalCaseApi.importUi(
      {
        page_url: uiContext.page_url?.trim() || undefined,
        login_strategy: 'none',
        source_method: 'record',
        items: [{
          functional_case_id: props.functionalCase.id,
          steps,
          case_name: caseName.value?.trim() || props.functionalCase.title,
          level: caseLevel.value,
          record_id: recordId
        }]
      },
      props.projectId
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '已导入 UI 用例库')
      visible.value = false
      emit('done', res.data.data)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

const handleClosed = () => {
  recorderVisible.value = false
  Object.assign(uiContext, defaultUiContext())
  deviceId.value = ''
  hoverDelayMs.value = 1000
}
</script>

<style scoped lang="scss">
.record-meta {
  margin-top: 8px;
}
.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
}
.runner-tip {
  font-size: 12px;
  margin-top: 4px;
  line-height: 1.5;
  code {
    background: var(--el-fill-color);
    padding: 0 4px;
    border-radius: 3px;
  }
}
</style>
