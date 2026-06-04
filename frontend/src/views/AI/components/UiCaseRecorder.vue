<template>
  <el-dialog
    v-model="visible"
    title="🎬 AI 录制 UI 测试步骤"
    width="900px"
    destroy-on-close
    :close-on-click-modal="false"
    class="ai-recorder-dialog"
  >
    <!-- ===== 配置态 ===== -->
    <div v-if="state === 'config' && !skipConfig" class="recorder-form">
      <el-alert
        v-if="presetMode"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px;"
      >
        <template #title>
          <div class="preset-summary">
            <div><strong>目标页面：</strong>{{ form.url || initialUrl || '—' }}</div>
            <div><strong>执行设备：</strong>{{ selectedDeviceLabel || '未选择' }}</div>
          </div>
        </template>
      </el-alert>

      <el-form :model="form" label-width="100px">
        <el-form-item v-if="!presetMode" label="目标页面" required>
          <el-input
            v-model="form.url"
            placeholder="例如：https://xxx.com/login（录制起始页面）"
            clearable
          />
        </el-form-item>

        <el-form-item v-if="!presetMode" label="执行设备" required>
          <el-select
            v-model="form.device_id"
            placeholder="选择 Runner 设备"
            style="width: 100%"
            :loading="loadingDevices"
            filterable
          >
            <el-option
              v-for="device in onlineDevices"
              :key="device.id"
              :label="`${device.name || device.id} (${device.ip || '未知IP'})`"
              :value="device.id"
            />
          </el-select>
          <div class="url-hint">请选择设备管理页状态为「在线」的 Runner</div>
          <el-alert
            v-if="deviceLoadError"
            type="warning"
            :closable="false"
            show-icon
            style="margin-top: 8px;"
            :title="deviceLoadError"
          />
        </el-form-item>

        <el-form-item label="悬浮停留时间">
          <el-slider
            v-model="form.hover_delay_ms"
            :min="500"
            :max="5000"
            :step="500"
            show-stops
          />
          <div class="url-hint">
            悬浮操作需在元素上方停留 {{ form.hover_delay_ms / 1000 }} 秒才会被录制（500ms~5s 可调）
          </div>
        </el-form-item>

        <el-form-item>
          <el-alert
            type="info"
            :closable="false"
            show-icon
          >
            <template #title>
              点击"开始录制"后，本地将弹出浏览器窗口。请在浏览器中操作页面，系统会自动记录您的操作。
            </template>
          </el-alert>
        </el-form-item>
      </el-form>

      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="starting" @click="handleStart">
          开始录制
        </el-button>
      </div>
    </div>

    <!-- ===== 录制中 ===== -->
    <div v-if="state === 'recording'" class="recording-state">
      <div class="recording-header">
        <el-icon class="is-loading recording-icon" :size="32"><VideoCamera /></el-icon>
        <div class="recording-info">
          <h4>🔴 正在录制...</h4>
          <p>请在弹出的浏览器窗口中操作页面</p>
          <p class="recording-stats">
            已记录 <strong>{{ actionsCount }}</strong> 个操作
            <span v-if="elapsedTime > 0">，已录制 {{ formatTime(elapsedTime) }}</span>
          </p>
        </div>
      </div>

      <el-divider />

      <div class="recording-actions-preview">
        <h5>实时操作预览</h5>
        <el-timeline v-if="actions.length > 0">
          <el-timeline-item
            v-for="(action, idx) in actions.slice(-10)"
            :key="idx"
            :type="actionTypeColor(action.action_type)"
          >
            <span class="action-tag">{{ actionTypeLabel(action.action_type) }}</span>
            <span class="action-detail">{{ action.selector || action.url || action.value || '' }}</span>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无操作记录，请在浏览器中点击或输入" />
      </div>

      <div class="dialog-footer">
        <el-button type="danger" :loading="stopping" @click="handleStop">
          <el-icon><VideoPause /></el-icon>
          停止录制
        </el-button>
      </div>
    </div>

    <!-- ===== 结果态 ===== -->
    <div v-if="state === 'result'" class="result-state">
      <div class="result-header">
        <el-icon :size="32" color="#67C23A"><CircleCheck /></el-icon>
        <div>
          <h4>录制完成</h4>
          <p>共生成 {{ currentSteps.length }} 个步骤</p>
        </div>
      </div>

      <el-divider />

      <!-- 测试描述（用于 AI 优化上下文） -->
      <div class="description-section">
        <el-form-item label-width="80px">
          <template #label>
            <span class="desc-label">测试描述</span>
            <el-tooltip placement="top-start" :show-after="200">
              <template #content>
                <div class="recorder-desc-tooltip">{{ DESCRIPTION_TOOLTIP }}</div>
              </template>
              <el-icon class="desc-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="description"
            type="textarea"
            :rows="4"
            :placeholder="DESCRIPTION_PLACEHOLDER"
            style="width: 100%"
          />
          <el-collapse v-if="optimizeOptions.append_assertions" class="desc-example-collapse">
            <el-collapse-item title="查看推荐写法与示例（勾选补充断言时建议参考）" name="example">
              <pre class="desc-example">{{ DESCRIPTION_EXAMPLE }}</pre>
              <el-button link type="primary" size="small" @click="fillDescriptionExample">
                填入示例（可再按实际页面改文案）
              </el-button>
            </el-collapse-item>
          </el-collapse>
        </el-form-item>
      </div>

      <!-- AI 优化区域 -->
      <div class="optimize-section optimize-options">
        <el-form-item label="AI 模型" label-width="80px" style="width: 100%; margin-bottom: 8px;">
          <el-select
            v-model="aiConfigId"
            placeholder="默认模型"
            clearable
            style="width: 100%;"
            :loading="loadingConfigs"
          >
            <el-option
              v-for="c in enabledConfigs"
              :key="c.id"
              :label="`${c.name} (${c.model})`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-checkbox v-model="optimizeOptions.append_assertions">补充断言（基于描述中的预期）</el-checkbox>
        <el-checkbox v-model="optimizeOptions.use_page_context" :disabled="!optimizeOptions.append_assertions">
          使用录制页面文本辅助定位
        </el-checkbox>
      </div>
      <div class="optimize-section" v-if="!optimizedSteps.length">
        <el-button type="warning" :loading="optimizing" @click="handleOptimize">
          <el-icon><MagicStick /></el-icon>
          {{ optimizing ? 'AI 优化中...' : 'AI 优化步骤' }}
        </el-button>
        <span class="optimize-hint">精简冗余操作；可选自动追加断言（建议导入前人工确认）</span>
      </div>

      <div class="optimize-section" v-else>
        <el-radio-group v-model="stepVersion" size="small">
          <el-radio-button label="original">原始步骤 ({{ steps.length }} 步)</el-radio-button>
          <el-radio-button label="optimized">
            AI 优化 ({{ optimizedSteps.length }} 步
            <template v-if="lastOptimizeStats.assertions_count">，含 {{ lastOptimizeStats.assertions_count }} 断言</template>)
          </el-radio-button>
        </el-radio-group>
        <el-button type="warning" size="small" :loading="optimizing" @click="handleOptimize" style="margin-left: 12px;">
          重新优化
        </el-button>
      </div>

      <!-- 步骤列表 -->
      <div class="steps-section">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
        >
          <template #title>
            <span style="font-size: 13px">
              定位表达式支持多种语法：CSS（<code>#id</code> <code>.class</code>）、XPath（<code>//div</code>）、<code>get_by_text=文本</code>、<code>get_by_role=button, 名称</code> 等。点击下拉框可切换候选定位器，也可手动输入。
            </span>
          </template>
        </el-alert>
        <h5>
          {{ stepVersion === 'optimized' ? 'AI 优化步骤' : '原始步骤' }}
          <el-button type="primary" size="small" link @click="handleAddStep">
            <el-icon><Plus /></el-icon> 添加步骤
          </el-button>
        </h5>
        <el-table :data="currentSteps" size="small" border class="steps-table">
          <el-table-column type="index" width="40" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="stepTagType(row.method)">{{ row.keyword }}</el-tag>
              <el-tag v-if="row.meta?.ai_inferred_assertion" size="small" type="warning" style="margin-left: 4px;">AI断言</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="描述" min-width="180">
            <template #default="{ row, $index }">
              <el-input v-model="row.desc" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="定位表达式" min-width="200">
            <template #default="{ row }">
              <LocatorSelector
                v-if="row.params && row.params.locator !== undefined"
                v-model="row.params.locator"
                :meta="row.meta || {}"
              />
              <span v-else style="color: #999; font-size: 12px">-</span>
            </template>
          </el-table-column>
          <el-table-column label="其他参数" min-width="160">
            <template #default="{ row, $index }">
              <el-input
                v-model="currentStepParamsJson[$index]"
                size="small"
                type="textarea"
                :rows="2"
                placeholder="不含 locator 的其他参数"
                @blur="handleParamsBlur($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ $index }">
              <el-button type="danger" size="small" link @click="handleDeleteStep($index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleApply">
          <el-icon><Check /></el-icon>
          {{ applyLabel }}
        </el-button>
      </div>
    </div>
  </el-dialog>


</template>

<script setup>
import { ref, reactive, computed, watch, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoCamera, VideoPause, CircleCheck, Plus, Delete, Check, MagicStick, QuestionFilled
} from '@element-plus/icons-vue'

/** 测试描述撰写说明（与 Backend extract_expectations 的「预期：」格式对齐） */
const DESCRIPTION_PLACEHOLDER =
  '操作步骤 + 关键节点写「→ 预期：验证点」；不勾选补充断言时可只写流程'

const DESCRIPTION_TOOLTIP = `【怎么写更好】
1. 操作：账号、点哪里、输入什么（不必写「输入框应可见」）
2. 断言：只在关键结果写「→ 预期：…」，平台按条生成少量 outcome 断言
3. 预期写页面真实文案：菜单名、列表用户名、保存成功提示等
4. 否定用「不存在」「不应出现」→ 会生成 not_exist 断言

【识别格式】
• 登录 demo/demo123 → 查询 zhangsan → 预期：列表包含 zhangsan
• 或分行：1. 登录 → 预期：显示用户管理`

const DESCRIPTION_EXAMPLE = `【操作】
1. 使用 demo / demo123 登录
2. 进入用户管理，搜索框输入 zhangsan 并点击查询
3. 新增用户，姓名「测试」，点击保存

【预期】
1. 登录成功 → 预期：侧栏显示「用户管理」
2. 查询 zhangsan → 预期：列表中存在用户 zhangsan
3. 保存新用户 → 预期：列表中出现用户「测试」`

function fillDescriptionExample() {
  description.value = DESCRIPTION_EXAMPLE
}
import { aiRecordApi } from '@/api/modules/ai'
import { useOnlineDevices } from '@/composables/useOnlineDevices.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import LocatorSelector from '@/components/LocatorSelector.vue'

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const props = defineProps({
  modelValue: Boolean,
  initialUrl: { type: String, default: '' },
  initialDescription: { type: String, default: '' },
  presetDeviceId: { type: [String, Number], default: '' },
  presetMode: { type: Boolean, default: false },
  skipConfig: { type: Boolean, default: false },
  initialHoverDelayMs: { type: Number, default: 1000 },
  applyLabel: { type: String, default: '应用到用例' },
})

const emit = defineEmits(['update:modelValue', 'apply'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// ===== 状态 =====
const state = ref('config') // config / recording / result
const starting = ref(false)
const stopping = ref(false)

// ===== 表单 =====
const form = reactive({
  url: '',
  device_id: '',
  use_ai_optimize: false,
  hover_delay_ms: 1000,
})

// 测试描述（移到结果态，用于 AI 优化上下文）
const description = ref('')

// 在线设备列表
const { onlineDevices, loadingDevices, deviceLoadError, loadOnlineDevices } = useOnlineDevices()

const selectedDeviceLabel = computed(() => {
  const id = form.device_id
  if (!id) return ''
  const d = onlineDevices.value.find(item => String(item.id) === String(id))
  return d ? `${d.name || d.id} (${d.ip || '未知IP'})` : String(id)
})

const applyPresetValues = () => {
  if (props.initialUrl) form.url = props.initialUrl
  if (props.presetDeviceId) form.device_id = props.presetDeviceId
  if (props.initialHoverDelayMs) form.hover_delay_ms = props.initialHoverDelayMs
}

// ===== 录制数据 =====
const recordId = ref(null)
const actions = ref([])
const actionsCount = ref(0)
const elapsedTime = ref(0)
const steps = ref([])
const optimizedSteps = ref([])
const stepVersion = ref('original')
const optimizing = ref(false)
const optimizeOptions = reactive({
  append_assertions: true,
  use_page_context: true,
})
const lastOptimizeStats = reactive({
  trimmed_count: 0,
  assertions_count: 0,
})
const stepParamsJson = ref([])
const optimizedStepParamsJson = ref([])

// ===== 轮询 =====
let pollTimer = null
let elapsedTimer = null
let startTime = 0

// ===== 方法 =====

const handleStart = async () => {
  if (!form.url.trim()) {
    ElMessage.warning('请输入目标页面地址')
    if (props.skipConfig) visible.value = false
    return
  }
  if (!form.device_id) {
    ElMessage.warning('请选择执行设备')
    if (props.skipConfig) visible.value = false
    return
  }
  starting.value = true
  try {
    const res = await aiRecordApi.start({
      url: form.url,
      device_id: form.device_id,
      use_ai_optimize: form.use_ai_optimize,
      hover_delay_ms: form.hover_delay_ms,
    })
    // axios response: res.status = HTTP 状态码, res.data = StandardResponse
    if (res.status === 200 && res.data?.code === 200) {
      recordId.value = res.data.data.record_id
      state.value = 'recording'
      startTime = Date.now()
      actions.value = []
      actionsCount.value = 0
      elapsedTime.value = 0
      startPolling()
      startElapsedTimer()
      ElMessage.success('录制已启动，请在浏览器中操作页面')
    } else {
      ElMessage.error(res.data?.message || '启动录制失败')
      if (props.skipConfig) {
        visible.value = false
      }
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动录制失败')
    if (props.skipConfig) {
      visible.value = false
    }
  } finally {
    starting.value = false
  }
}

const handleStop = async () => {
  stopping.value = true
  stopPolling()
  stopElapsedTimer()
  try {
    await aiRecordApi.stop(recordId.value)
    ElMessage.info('停止指令已发送，等待结果...')
    // 再轮询几次等待结果
    await waitForResult()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '停止录制失败')
  } finally {
    stopping.value = false
  }
}

const waitForResult = async () => {
  // 最多等待 30 秒
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 1000))
    try {
      const res = await aiRecordApi.getStatus(recordId.value)
      if (res.status === 200 && res.data?.code === 200) {
        const data = res.data.data
        actions.value = data.raw_actions || []
        actionsCount.value = data.actions_count
        if (data.status === 'completed') {
          steps.value = data.steps || []
          optimizedSteps.value = data.optimized_steps || []
          syncStepParamsJson()
          state.value = 'result'
          return
        }
        if (data.status === 'failed') {
          ElMessage.error(data.error || '录制失败')
          state.value = 'config'
          return
        }
      }
    } catch (e) {
      console.error('等待结果失败:', e)
    }
  }
  ElMessage.warning('等待结果超时，请稍后手动查询')
  state.value = 'config'
}

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!recordId.value) return
    try {
      const res = await aiRecordApi.getStatus(recordId.value)
      if (res.status === 200 && res.data?.code === 200) {
        const data = res.data.data
        actions.value = data.raw_actions || []
        actionsCount.value = data.actions_count
        // 如果 Runner 已经自动完成
        if (data.status === 'completed' && state.value === 'recording') {
          steps.value = data.steps || []
          optimizedSteps.value = data.optimized_steps || []
          syncStepParamsJson()
          stopPolling()
          stopElapsedTimer()
          state.value = 'result'
          ElMessage.success('录制完成')
        }
        if (data.status === 'failed' && state.value === 'recording') {
          stopPolling()
          stopElapsedTimer()
          ElMessage.error(data.error || '录制失败')
          state.value = 'config'
        }
      }
    } catch (e) {
      console.error('轮询状态失败:', e)
    }
  }, 1000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startElapsedTimer = () => {
  stopElapsedTimer()
  elapsedTimer = setInterval(() => {
    elapsedTime.value = Math.floor((Date.now() - startTime) / 1000)
  }, 1000)
}

const stopElapsedTimer = () => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

const currentSteps = computed(() => stepVersion.value === 'optimized' ? optimizedSteps.value : steps.value)
const currentStepParamsJson = computed(() => stepVersion.value === 'optimized' ? optimizedStepParamsJson.value : stepParamsJson.value)

const syncStepParamsJson = () => {
  // 参数 JSON 中排除 locator（locator 已单独用 LocatorSelector 展示和编辑）
  stepParamsJson.value = steps.value.map(s => {
    const { locator, ...rest } = s.params || {}
    return JSON.stringify(rest, null, 2)
  })
  optimizedStepParamsJson.value = optimizedSteps.value.map(s => {
    const { locator, ...rest } = s.params || {}
    return JSON.stringify(rest, null, 2)
  })
}

const handleParamsBlur = (index) => {
  try {
    const paramsJson = stepVersion.value === 'optimized' ? optimizedStepParamsJson.value : stepParamsJson.value
    const targetSteps = stepVersion.value === 'optimized' ? optimizedSteps.value : steps.value
    const parsed = JSON.parse(paramsJson[index])
    // 保留 locator（由 LocatorSelector 单独管理）
    const existingLocator = targetSteps[index].params?.locator
    targetSteps[index].params = { ...parsed, ...(existingLocator !== undefined ? { locator: existingLocator } : {}) }
  } catch (e) {
    ElMessage.warning(`第 ${index + 1} 步参数 JSON 格式错误`)
  }
}

const handleDeleteStep = (index) => {
  if (stepVersion.value === 'optimized') {
    optimizedSteps.value.splice(index, 1)
    optimizedStepParamsJson.value.splice(index, 1)
  } else {
    steps.value.splice(index, 1)
    stepParamsJson.value.splice(index, 1)
  }
}

const handleAddStep = () => {
  steps.value.push({
    id: `step_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
    keyword: '点击元素',
    desc: '点击某个元素',
    method: 'click_ele',
    params: { locator: '', index: 1, force: false, timeout: 20000 },
    children: [],
    meta: {},
  })
  // stepParamsJson 排除 locator（由 LocatorSelector 单独管理）
  stepParamsJson.value.push(JSON.stringify({ index: 1, force: false, timeout: 20000 }, null, 2))
}

const handleOptimize = async () => {
  if (!recordId.value) {
    ElMessage.warning('录制会话不存在')
    return
  }
  optimizing.value = true
  try {
    const res = await aiRecordApi.optimize(recordId.value, {
      description: description.value,
      ai_config_id: aiConfigId.value || undefined,
      append_assertions: optimizeOptions.append_assertions,
      use_page_context: optimizeOptions.use_page_context,
    })
    if (res.status === 200 && res.data?.code === 200) {
      const d = res.data.data || {}
      optimizedSteps.value = d.optimized_steps || []
      lastOptimizeStats.trimmed_count = d.trimmed_count || 0
      lastOptimizeStats.assertions_count = d.assertions_count || 0
      optimizedStepParamsJson.value = optimizedSteps.value.map(s => {
        const { locator, ...rest } = s.params || {}
        return JSON.stringify(rest, null, 2)
      })
      stepVersion.value = 'optimized'
      const msg = lastOptimizeStats.assertions_count
        ? `优化完成：精简 ${lastOptimizeStats.trimmed_count} 步 + 断言 ${lastOptimizeStats.assertions_count} 条`
        : 'AI 优化完成'
      ElMessage.success(msg)
    } else {
      ElMessage.error(res.data?.message || 'AI 优化失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'AI 优化失败')
  } finally {
    optimizing.value = false
  }
}

const handleApply = () => {
  const targetSteps = stepVersion.value === 'optimized' ? optimizedSteps.value : steps.value
  if (targetSteps.length === 0) {
    ElMessage.warning('没有可应用的步骤')
    return
  }
  emit('apply', JSON.parse(JSON.stringify(targetSteps)))
  visible.value = false
  resetState()
}

const resetState = () => {
  state.value = 'config'
  form.url = props.initialUrl || ''
  form.device_id = props.presetDeviceId || ''
  description.value = props.initialDescription || ''
  recordId.value = null
  actions.value = []
  actionsCount.value = 0
  elapsedTime.value = 0
  steps.value = []
  stepParamsJson.value = []
  optimizedSteps.value = []
  optimizedStepParamsJson.value = []
  stepVersion.value = 'original'
  stopPolling()
  stopElapsedTimer()
}

const formatTime = (seconds) => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}分${s}秒`
}

const actionTypeColor = (type) => {
  const map = { click: 'primary', fill: 'success', navigate: 'warning', wait: 'info' }
  return map[type] || ''
}

const actionTypeLabel = (type) => {
  const map = {
    click: '点击', fill: '输入', navigate: '导航', wait: '等待',
    dblclick: '双击', select: '选择', hover: '悬停'
  }
  return map[type] || type
}

const stepTagType = (method) => {
  const map = {
    click_ele: 'primary', fill_value: 'success', open_url: 'warning',
    wait_for_time: 'info', double_click_ele: 'danger', hover: ''
  }
  if (String(method || '').startsWith('kw_assert_')) return 'success'
  return map[method] || ''
}

watch(() => props.modelValue, async (val) => {
  if (val) {
    resetState()
    applyPresetValues()
    await loadConfigs()
    if (!props.skipConfig) {
      const list = await loadOnlineDevices()
      if (!form.device_id && list.length === 1) {
        form.device_id = list[0].id
      }
    }
    applyPresetValues()
    if (props.skipConfig && props.presetMode) {
      await nextTick()
      handleStart()
    }
  }
})

watch(() => props.initialUrl, (url) => {
  if (url) form.url = url
})

watch(() => props.presetDeviceId, (id) => {
  if (id) form.device_id = id
})

defineExpose({ recordId })

onUnmounted(() => {
  stopPolling()
  stopElapsedTimer()
})
</script>

<style scoped lang="scss">
.ai-recorder-dialog {
  :deep(.el-dialog__body) {
    max-height: 70vh;
    overflow-y: auto;
    padding-top: 10px;
  }
}

.recorder-form {
  padding: 10px 0;
}
.preset-summary {
  font-size: 13px;
  line-height: 1.6;
}

.recording-state {
  padding: 10px 0;

  .recording-header {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 10px;
    background: #fdf6ec;
    border-radius: 8px;
    border: 1px solid #f0c78a;

    .recording-icon {
      color: #f56c6c;
    }

    .recording-info {
      h4 {
        margin: 0 0 5px;
        color: #e6a23c;
      }
      p {
        margin: 0;
        color: #666;
        font-size: 14px;
      }
      .recording-stats {
        margin-top: 5px;
        font-size: 13px;
        strong {
          color: #f56c6c;
          font-size: 16px;
        }
      }
    }
  }

  .recording-actions-preview {
    max-height: 300px;
    overflow-y: auto;
    padding: 10px;
    background: #f5f7fa;
    border-radius: 6px;

    h5 {
      margin: 0 0 10px;
      color: #333;
    }

    .action-tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      background: #409eff;
      color: #fff;
      font-size: 12px;
      margin-right: 8px;
    }
    .action-detail {
      color: #666;
      font-size: 13px;
      word-break: break-all;
    }
  }
}

.result-state {
  padding: 10px 0;

  .result-header {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 10px;
    background: #f0f9eb;
    border-radius: 8px;
    border: 1px solid #b3e19d;

    h4 {
      margin: 0 0 5px;
      color: #67c23a;
    }
    p {
      margin: 0;
      color: #666;
      font-size: 14px;
    }
  }

  .description-section {
    margin-bottom: 12px;

    :deep(.el-form-item) {
      margin-bottom: 0;
    }
    :deep(.el-form-item__label) {
      color: #606266;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }

    .desc-label {
      line-height: 1;
    }

    .desc-help-icon {
      color: #909399;
      cursor: help;
      font-size: 14px;
    }

    .desc-example-collapse {
      margin-top: 8px;
      border: none;

      :deep(.el-collapse-item__header) {
        height: 32px;
        line-height: 32px;
        font-size: 12px;
        color: #409eff;
        border: none;
        background: transparent;
      }
      :deep(.el-collapse-item__wrap) {
        border: none;
      }
      :deep(.el-collapse-item__content) {
        padding-bottom: 4px;
      }
    }

    .recorder-desc-tooltip {
      max-width: 360px;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    .desc-example {
      margin: 0 0 8px;
      padding: 10px 12px;
      background: #f5f7fa;
      border-radius: 4px;
      font-size: 12px;
      line-height: 1.55;
      color: #606266;
      white-space: pre-wrap;
      word-break: break-word;
    }
  }

  .optimize-section {
    margin-bottom: 15px;
    padding: 12px;
    background: #fdf6ec;
    border-radius: 6px;
    border: 1px solid #f0c78a;
    display: flex;
    align-items: center;
    gap: 12px;

    &.optimize-options {
      flex-wrap: wrap;
      align-items: flex-start;
    }

    .optimize-hint {
      color: #e6a23c;
      font-size: 13px;
    }
  }

  .steps-section {
    margin-top: 15px;

    h5 {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 0 0 10px;
    }
  }

}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px solid #e4e7ed;
}

.steps-table {
  :deep(.el-textarea__inner) {
    font-family: 'Consolas', monospace;
    font-size: 12px;
  }
}
</style>
