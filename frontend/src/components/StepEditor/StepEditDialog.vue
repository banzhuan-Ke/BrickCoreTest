<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑步骤' : '新增步骤'"
    width="700px"
    destroy-on-close
    @closed="handleClose"
  >
    <el-form 
      :model="form" 
      :rules="formRules"
      label-width="100px" 
      ref="formRef"
    >
      <!-- 步骤名称 -->
      <el-form-item label="操作名称" prop="desc">
        <div class="param-input-row">
          <el-input v-model="form.desc" placeholder="请输入操作描述" style="flex: 1" />
          <VarInsertButton :env-id="varInsertEnvId" label="变量" />
          <ToolInsertButton label="工具" />
        </div>
      </el-form-item>

      <el-form-item label="变量参考">
        <div class="step-insert-toolbar">
          <el-select
            v-model="varInsertEnvId"
            placeholder="参考环境"
            size="small"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="e in envList"
              :key="e.id"
              :label="e.name"
              :value="e.id"
            />
          </el-select>
          <VarInsertButton :env-id="varInsertEnvId" label="插入变量" hint-text="跨环境请优先用环境变量同名 key。" />
          <ToolInsertButton label="插入工具" />
          <el-button link type="info" size="small" @click="tagPickerVisible = true">数据工厂标签</el-button>
        </div>
        <p class="step-insert-hint">请先点击要填入的参数输入框，再选择插入项；执行时以运行环境为准。</p>
      </el-form-item>
      
      <!-- 数据库断言（专用表单） -->
      <el-form-item label="库断言" v-if="isDbAssertStep">
        <UiDbAssertStepFields
          :params="form.params"
          :project-id="projectId"
          :env-id="varInsertEnvId"
        />
      </el-form-item>

      <!-- input 文件上传：平台 MinIO 文件选择 -->
      <el-form-item label="测试文件" v-if="isUploadFileStep">
        <UiTestFilePicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>

      <!-- 参数配置 -->
      <el-form-item :label="paramsSectionLabel" v-if="hasParams && !isDbAssertStep">
        <div class="params-container">
          <div 
            class="param-item" 
            v-for="(value, key) in filteredParams" 
            :key="key"
          >
            <div class="param-label">
              {{ getParamLabel(form.method, key, paramLabelMap[key]) }}
              <span v-if="isRequiredParam(key)" class="required-mark">*</span>
            </div>
            
            <!-- 根据参数类型渲染不同输入框 -->
            <template v-if="isLocatorKey(key)">
              <div class="locator-heal-row">
                <LocatorSelector
                  v-model="form.params[key]"
                  :meta="props.step?.meta || {}"
                />
                <el-button
                  type="primary"
                  link
                  :loading="healingLocator"
                  @click="handleHealLocator"
                >AI 自愈</el-button>
              </div>
            </template>
            <template v-else-if="isLongTextKey(key)">
              <div class="param-input-row">
                <el-input
                  v-model="form.params[key]"
                  type="textarea"
                  :rows="2"
                  :placeholder="isRequiredParam(key) ? '必填' : '请输入'"
                  style="flex: 1"
                />
                <VarInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="变量" />
                <ToolInsertButton v-if="canInsertVar(key)" label="工具" />
              </div>
            </template>
            <template v-else-if="isNumber(value)">
              <el-input-number v-model="form.params[key]" style="width: 100%" :controls-position="'right'" />
            </template>
            <template v-else-if="isSelect(key)">
              <el-select v-model="form.params[key]" style="width: 100%">
                <el-option 
                  v-for="opt in getOptions(key)" 
                  :key="opt.value" 
                  :label="opt.label" 
                  :value="opt.value" 
                />
              </el-select>
            </template>
            <template v-else-if="isBoolean(key)">
              <el-switch v-model="form.params[key]" />
            </template>
            <template v-else>
              <div class="param-input-row">
                <el-input
                  v-model="form.params[key]"
                  :placeholder="isRequiredParam(key) ? '必填' : '请输入'"
                  style="flex: 1"
                />
                <VarInsertButton v-if="canInsertVar(key)" :env-id="varInsertEnvId" label="变量" />
                <ToolInsertButton v-if="canInsertVar(key)" label="工具" />
              </div>
            </template>
          </div>
        </div>
      </el-form-item>
      
      <!-- 条件分支配置 -->
      <el-form-item label="分支配置" v-if="isConditionBranch">
        <ConditionEdit v-model:branches="form.branches" />
      </el-form-item>
      
      <!-- 高级配置 -->
      <el-form-item label="高级配置" v-if="!isConditionBranch">
        <div class="advanced-box">
          <div class="advanced-header" @click="showAdvanced = !showAdvanced">
            <span class="advanced-title">超时与重试</span>
            <el-icon class="advanced-arrow" :class="{ 'is-open': showAdvanced }"><ArrowDown /></el-icon>
          </div>
          <div class="advanced-content" v-show="showAdvanced">
            <div class="advanced-row">
              <span class="advanced-label">超时时间</span>
              <el-input-number 
                v-model="form.config.timeout" 
                :min="1000" 
                :step="1000" 
                :controls-position="'right'"
                style="width: 140px"
              />
              <span class="advanced-unit">ms</span>
            </div>
            <div class="advanced-row">
              <span class="advanced-label">失败重试</span>
              <el-switch v-model="form.config.retry" />
            </div>
          </div>
        </div>
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>

  <DataFactoryTagPicker
    v-model="tagPickerVisible"
    :project-id="projectId"
    @insert="onDfTagInsert"
  />

  <el-dialog v-model="healDialogVisible" title="AI 定位器自愈" width="520px" append-to-body destroy-on-close>
    <el-form label-width="120px">
      <el-form-item label="抓取方式">
        <el-radio-group v-model="healMode">
          <el-radio value="replay" :disabled="!canReplay">回放前置步骤</el-radio>
          <el-radio value="url">仅打开 URL</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="healMode === 'replay'" label="回放至第 N 步">
        <el-input-number v-model="healReplayThrough" :min="1" :max="Math.max(1, props.stepIndex)" />
        <div class="heal-hint">将执行用例第 1～{{ healReplayThrough }} 步（不含当前第 {{ props.stepIndex + 1 }} 步），再抓取页面 snapshot</div>
      </el-form-item>
      <el-form-item :label="healMode === 'replay' ? '备用 URL' : '页面 URL'">
        <el-input
          v-model="healPageUrl"
          :placeholder="healMode === 'replay' ? '步骤中无 open_url 时填写' : 'https://example.com/page'"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="healDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="healingLocator" @click="confirmHeal">开始自愈</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, inject } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ConditionEdit from './ConditionEdit.vue'
import LocatorSelector from '@/components/LocatorSelector.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DataFactoryTagPicker from '@/views/ApiModule/components/DataFactoryTagPicker.vue'
import UiDbAssertStepFields from './UiDbAssertStepFields.vue'
import UiTestFilePicker from './UiTestFilePicker.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { insertVarRef } from '@/utils/varInsert.js'
import { getOrderedVisibleParams, getParamLabel, isAssertionMethod } from '@/utils/uiStepMeta.js'
import { aiGenerateApi } from '@/api/modules/ai.js'

const proStore = ProjectStore()
const varInsertEnvId = inject('varInsertEnvId', ref(null))
const envList = computed(() => proStore.envList || [])
const projectId = computed(() => proStore.projectInfo?.id)
const tagPickerVisible = ref(false)

async function onDfTagInsert(refStr) {
  const m = String(refStr).match(/^\$\{\{(.+)\}\}$/)
  const name = m ? m[1] : refStr
  const result = await insertVarRef(name)
  if (result?.ok) {
    const tip =
      result.mode === 'copy'
        ? `已复制 ${refStr}，请粘贴到目标输入框`
        : `已插入 ${refStr}`
    ElMessage.success(tip)
  } else {
    ElMessage.warning('请先将光标放入要填入的输入框')
  }
}

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  step: {
    type: Object,
    default: null
  },
  allSteps: {
    type: Array,
    default: () => []
  },
  stepIndex: {
    type: Number,
    default: -1
  }
})

const emit = defineEmits(['update:visible', 'save', 'cancel'])

const formRef = ref()
const form = ref({
  id: '',
  keyword: '',
  desc: '',
  method: '',
  params: {},
  config: { timeout: 30000, retry: false }
})
const showAdvanced = ref(false)
const healingLocator = ref(false)
const healPageUrl = ref('')
const healDialogVisible = ref(false)
const healMode = ref('replay')
const healReplayThrough = ref(1)

const canReplay = computed(() => props.stepIndex > 0 && (props.allSteps?.length || 0) > 0)

// 是否是编辑模式
const isEdit = computed(() => !!props.step?.id)

// 是否是条件分支步骤
const isConditionBranch = computed(() => {
  return form.value.method === 'condition_branch'
})

const isDbAssertStep = computed(() => form.value.method === 'kw_db_assert')

const isUploadFileStep = computed(() => form.value.method === 'upload_file')

const paramsSectionLabel = computed(() =>
  isAssertionMethod(form.value.method) ? '断言参数' : '配置参数'
)

const uploadFileHiddenKeys = new Set(['file_path', 'file_key', 'file_bucket', 'file_name'])

// 表单校验规则
const formRules = {
  desc: [
    { required: true, message: '请输入操作名称', trigger: 'blur' }
  ]
}

// 过滤后的参数（按 method 元数据控制可见字段与顺序）
const filteredParams = computed(() => {
  const raw = { ...(form.value.params || {}) }
  const keepTimeoutMethods = ['wait_for_time', 'set_default_timeout']
  if (form.value.method === 'upload_file') {
    uploadFileHiddenKeys.forEach((key) => delete raw[key])
  }
  if (!keepTimeoutMethods.includes(form.value.method)) {
    delete raw.timeout
  }
  return getOrderedVisibleParams(form.value.method, raw)
})

// 是否有参数
const hasParams = computed(() => {
  return Object.keys(filteredParams.value).length > 0
})

// 判断参数是否必填
function isRequiredParam(key) {
  const method = form.value.method
  const assertionRequired = {
    kw_assert_page_title: ['title'],
    kw_assert_page_url: ['url'],
    kw_assert_value: ['locator', 'value'],
    kw_assert_element_text: ['locator', 'text'],
    kw_assert_element_text_contains: ['locator', 'text'],
    kw_assert_text_contains: ['text'],
    kw_assert_attribute: ['locator', 'attr_name', 'value'],
    kw_assert_visible: ['locator'],
    kw_assert_hidden: ['locator'],
    kw_assert_not_exist: ['locator'],
    kw_assert_not_visible: ['locator'],
    kw_assert_enabled: ['locator'],
    kw_assert_disabled: ['locator'],
    kw_assert_checked: ['locator'],
    kw_assert_empty: ['locator'],
    kw_assert_editable: ['locator'],
    kw_assert_focused: ['locator'],
  }
  if (assertionRequired[method]) {
    return assertionRequired[method].includes(key)
  }
  const requiredParams = ['selector', 'condition', 'locator', 'var_name', 'attr_name', 'url', 'value', 'text']
  return requiredParams.includes(key)
}

// 参数标签映射（完整的参数映射表）
const paramLabelMap = {
  // 页面操作
  browser_type: '浏览器类型',
  url: '页面url地址',
  wait_until: '等待状态',
  timeout: '超时时间(毫秒)',
  tag: '页面标签名',
  index: '顺序索引',
  title: '网页标题',
  name: '截图名称',
  height: '滚动高度',
  script: 'JS脚本(箭头函数)',
  args: '传给JS的参数',
  
  // 元素操作
  locator: '元素定位表达式',
  selector: '元素定位表达式',
  value: '输入值',
  button: '按键(left/right)',
  count: '点击次数',
  start_selector: '起始元素定位',
  end_selector: '结束元素定位',
  delay: '时长(秒)',
  
  // 鼠标键盘
  x: 'X坐标',
  y: 'Y坐标',
  key: '按键',
  keys: '输入文本',
  button: '鼠标按键',
  
  // iframe操作
  frame: 'iframe定位表达式',
  
  // 断言
  expect_results: '预期结果',
  is_equal: '是否相等',
  attr_name: '属性名称',
  text: '预期文本',
  match_mode: '匹配方式',
  
  // 变量提取
  var_name: '变量名',
  
  // 文件上传
  file_path: '文件绝对路径',
  
  // 强制点击
  force: '强制点击(绕过遮挡)'
}

// 长文本类型的key
const longTextKeys = ['url', 'selector', 'script', 'condition', 'text', 'value', 'path', 'download_path']

// 监听 step 变化
watch(() => props.step, (newStep) => {
  if (newStep) {
    // 确保条件分支有branches字段
    const stepData = { ...newStep }
    if (stepData.method === 'condition_branch' && !stepData.branches) {
      stepData.branches = [
        {
          id: `branch_${Date.now()}`,
          name: '分支1',
          condition: { type: 'element_visible', locator: '', operator: 'is_true' },
          steps: []
        },
        {
          id: `else_branch_${Date.now()}`,
          name: '默认分支',
          condition: { type: 'else' },
          steps: []
        }
      ]
    }
    form.value = {
      ...stepData,
      params: { ...newStep.params },
      config: { timeout: 30000, retry: false, ...newStep.config },
      branches: newStep.branches ? JSON.parse(JSON.stringify(newStep.branches)) : undefined
    }
  }
}, { immediate: true, deep: true })

// 监听 visible 变化
const visible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

// 判断是否为长文本key
function isLongTextKey(key) {
  return longTextKeys.includes(key)
}

// 判断是否为长文本
function isLongText(value) {
  if (typeof value !== 'string') return false
  return value.length > 50 || value.includes('\n')
}

// 判断是否为数字
function isNumber(value) {
  return typeof value === 'number'
}

// 判断是否为下拉选择
function isSelect(key) {
  const selectKeys = ['wait_until', 'browser_type', 'operator', 'key', 'button', 'match_mode']
  return selectKeys.includes(key)
}

// 是否为定位表达式参数（使用 LocatorSelector 组件）
function isLocatorKey(key) {
  return ['locator', 'selector'].includes(key)
}

function canInsertVar(key) {
  return !isLocatorKey(key) && !isNumber(form.value.params?.[key]) && !isBoolean(key) && !isSelect(key)
}

async function handleHealLocator() {
  const locatorKey = Object.keys(form.value.params || {}).find(k => isLocatorKey(k))
  if (!locatorKey) {
    ElMessage.warning('当前步骤无定位器参数')
    return
  }
  const failed = (form.value.params[locatorKey] || '').trim()
  if (!failed) {
    ElMessage.warning('请先填写失败的定位器')
    return
  }
  healReplayThrough.value = Math.max(1, props.stepIndex)
  healMode.value = canReplay.value ? 'replay' : 'url'
  healDialogVisible.value = true
}

async function confirmHeal() {
  const locatorKey = Object.keys(form.value.params || {}).find(k => isLocatorKey(k))
  const failed = (form.value.params[locatorKey] || '').trim()
  const payload = {
    method: form.value.method,
    failed_locator: failed,
    step_desc: form.value.desc
  }

  if (healMode.value === 'replay' && canReplay.value) {
    payload.replay_steps = props.allSteps
    payload.replay_through_index = healReplayThrough.value
    if (healPageUrl.value.trim()) {
      payload.page_url = healPageUrl.value.trim()
    }
  } else {
    if (!healPageUrl.value.trim()) {
      ElMessage.warning('请填写页面 URL')
      return
    }
    payload.page_url = healPageUrl.value.trim()
  }

  healingLocator.value = true
  try {
    const res = await aiGenerateApi.healLocator(payload)
    if (res.data?.code === 200 && res.data.data?.locator) {
      form.value.params[locatorKey] = res.data.data.locator
      ElMessage.success(`已应用新定位器（${res.data.data.confidence || 'medium'}）`)
      healDialogVisible.value = false
    } else {
      ElMessage.error(res.data?.data?.reason || res.data?.message || '自愈失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自愈请求失败')
  } finally {
    healingLocator.value = false
  }
}

// 判断是否为布尔值
function isBoolean(key) {
  const booleanKeys = ['force']
  return booleanKeys.includes(key)
}

// 获取选项
function getOptions(key) {
  const options = {
    wait_until: [
      { label: '页面加载完成', value: 'load' },
      { label: 'DOM就绪', value: 'domcontentloaded' },
      { label: '网络空闲', value: 'networkidle' }
    ],
    browser_type: [
      { label: 'Chrome', value: 'chromium' },
      { label: 'Firefox', value: 'firefox' },
      { label: 'Safari', value: 'webkit' }
    ],
    operator: [
      { label: '等于', value: 'eq' },
      { label: '包含', value: 'contains' },
      { label: '大于', value: 'gt' },
      { label: '小于', value: 'lt' }
    ],
    key: [
      { label: 'Enter', value: 'Enter' },
      { label: 'Tab', value: 'Tab' },
      { label: 'Escape', value: 'Escape' },
      { label: 'Backspace', value: 'Backspace' },
      { label: 'ArrowUp', value: 'ArrowUp' },
      { label: 'ArrowDown', value: 'ArrowDown' },
      { label: 'ArrowLeft', value: 'ArrowLeft' },
      { label: 'ArrowRight', value: 'ArrowRight' }
    ],
    button: [
      { label: '左键', value: 'left' },
      { label: '右键', value: 'right' },
      { label: '中键', value: 'middle' }
    ],
    match_mode: [
      { label: '完全相等', value: 'exact' },
      { label: '包含', value: 'contains' }
    ]
  }
  return options[key] || []
}

// 保存 - 带校验
async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请填写必填项')
    return
  }
  
  // 条件分支不需要校验参数
  if (isDbAssertStep.value) {
    if (!form.value.params?.sql?.trim()) {
      ElMessage.warning('请填写 SQL/Redis 命令')
      return
    }
  } else if (!isConditionBranch.value) {
    if (isUploadFileStep.value) {
      const p = form.value.params || {}
      const hasPlatformFile = !!(p.file_key && p.file_bucket)
      const hasLegacyPath = !!(p.file_path && String(p.file_path).trim())
      if (!hasPlatformFile && !hasLegacyPath) {
        ElMessage.warning('请选择测试文件，或填写 Runner 本地路径')
        return
      }
    }
    // 额外校验必填参数
    for (const key of Object.keys(filteredParams.value)) {
      if (isRequiredParam(key)) {
        const value = form.value.params[key]
        if (!value || (typeof value === 'string' && value.trim() === '')) {
          ElMessage.warning(`请填写${paramLabelMap[key] || key}`)
          return
        }
      }
    }
  }
  
  // 构建保存的步骤数据
  const savedStep = { 
    ...form.value,
    keyword: form.value.keyword,
    method: form.value.method || form.value.keyword
  }
  
  // 条件分支特殊处理
  if (isConditionBranch.value) {
    savedStep.is_container = true
    // 确保branches字段存在
    if (!savedStep.branches || savedStep.branches.length === 0) {
      savedStep.branches = [
        {
          id: `branch_${Date.now()}`,
          name: '分支1',
          condition: { type: 'element_visible', locator: '', operator: 'is_true' },
          steps: []
        },
        {
          id: `else_branch_${Date.now()}`,
          name: '默认分支',
          condition: { type: 'else' },
          steps: []
        }
      ]
    }
  }
  
  emit('save', savedStep)
}

// 取消
function handleCancel() {
  emit('cancel')
}

// 关闭
function handleClose() {
  form.value = {
    id: '',
    keyword: '',
    desc: '',
    method: '',
    params: {},
    config: { timeout: 30000, retry: false }
  }
  showAdvanced.value = false
}
</script>

<style scoped lang="scss">
.params-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}

.param-item {
  width: 100%;
  
  .param-label {
    font-size: 13px;
    color: var(--el-text-color-secondary);
    margin-bottom: 6px;
    
    .required-mark {
      color: var(--el-color-danger);
      margin-left: 4px;
    }
  }
  
  :deep(.el-input__wrapper),
  :deep(.el-textarea__inner) {
    width: 100%;
  }
}

// 高级配置样式 - 新的卡片式设计
.advanced-box {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}

.advanced-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: background 0.2s;
  
  &:hover {
    background: var(--el-fill-color);
  }
}

.advanced-title {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.advanced-arrow {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  transition: transform 0.3s;
  
  &.is-open {
    transform: rotate(180deg);
  }
}

.advanced-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--el-bg-color);
}

.advanced-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.advanced-label {
  width: 80px;
  font-size: 14px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
}

.advanced-unit {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.locator-heal-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  :deep(.locator-selector) {
    flex: 1;
  }
}

.param-input-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.heal-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.step-insert-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  width: 100%;
  overflow-x: auto;
}

.step-insert-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
