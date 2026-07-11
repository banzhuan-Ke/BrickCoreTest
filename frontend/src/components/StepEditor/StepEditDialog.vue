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
          <el-input v-model="form.desc" placeholder="简短名称，如：点击登录" style="flex: 1" />
          <VarInsertButton :env-id="varInsertEnvId" label="变量" />
          <ToolInsertButton label="工具" />
        </div>
      </el-form-item>

      <el-form-item label="业务意图" prop="intent">
        <el-input
          v-model="form.intent"
          type="textarea"
          :rows="2"
          placeholder="可选。描述本步要完成的操作目标，供 AI 自愈参考。例：点击左侧导航栏的「基础设置」菜单项"
        />
        <p class="step-intent-hint">未填写时自愈使用「操作名称」。填写更具体的意图可提高自愈准确率。</p>
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

      <AppH5UsageGuide
        v-if="showAppH5StepGuide"
        scope="step"
        :driver-mode="driverMode"
        :step-method="form.method"
        :has-h5-locator="appFormHasH5Locator"
        :has-image-locator="appFormHasImageLocator"
        :title="appStepGuideTitle"
      />
      
      <!-- 数据库断言（专用表单） -->
      <el-form-item label="库断言" v-if="isDbAssertStep">
        <UiDbAssertStepFields
          :params="form.params"
          :project-id="projectId"
          :env-id="varInsertEnvId"
        />
      </el-form-item>

      <!-- input 文件上传：平台 MinIO 文件/文件夹选择 -->
      <el-form-item label="上传模式" v-if="isUploadFileStep">
        <el-radio-group v-model="uploadMode">
          <el-radio value="single">单文件</el-radio>
          <el-radio value="multiple">多文件</el-radio>
          <el-radio value="folder">文件夹</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="测试文件" v-if="isUploadFileStep && uploadMode === 'single'">
        <UiTestFilePicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>
      <el-form-item label="测试文件" v-if="isUploadFileStep && uploadMode === 'multiple'">
        <UiTestMultiFilePicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>
      <el-form-item label="测试文件夹" v-if="isUploadFileStep && uploadMode === 'folder'">
        <UiTestFolderPicker v-model="form.params" :env-id="varInsertEnvId" />
      </el-form-item>

      <el-form-item label="识别图" v-if="isWebVisionStep">
        <div class="web-vision-template">
          <el-upload
            :show-file-list="false"
            accept="image/png,image/jpeg,image/webp"
            :http-request="handleWebVisionTemplateUpload"
            :disabled="stepTemplateUploading"
          >
            <el-button type="primary" plain size="small" :loading="stepTemplateUploading">上传模板图</el-button>
          </el-upload>
          <el-input
            v-model="form.params.template"
            placeholder="MinIO 对象键，如 app-elements/1/xxx.png"
            class="web-vision-template-input"
          />
          <div class="web-vision-threshold">
            <span>相似度阈值</span>
            <el-slider v-model="form.params.threshold" :min="0.1" :max="0.99" :step="0.01" style="width: 200px" />
          </div>
          <el-image
            v-if="webVisionPreviewSrc"
            :src="webVisionPreviewSrc"
            fit="contain"
            class="step-template-preview"
            :preview-src-list="[webVisionPreviewSrc]"
          />
          <el-text type="info" size="small">固定 viewport 下匹配页面截图；Canvas/纯图标场景兜底，优先 DOM 定位。</el-text>
        </div>
      </el-form-item>

      <!-- 参数配置 -->
      <el-form-item :label="paramsSectionLabel" v-if="hasParams && !isDbAssertStep">
        <div class="params-container">
          <el-alert
            v-if="isDragDropStep"
            type="info"
            :closable="false"
            show-icon
            class="drag-position-hint"
          >
            <template #title>拖拽落点坐标</template>
            <p>坐标相对元素<strong>左上角</strong>，单位像素；X/Y 需成对填写才生效，留空则落在元素中心。</p>
            <p class="drag-position-example">
              例：把「拖拽目录2」插到「拖拽目录1」前面 →
              起始=<code>目录2</code>，结束=<code>目录1</code>，目标 X=<code>20</code>，目标 Y=<code>5</code>
            </p>
          </el-alert>
          <el-alert
            v-if="isElementOrderStep"
            type="info"
            :closable="false"
            show-icon
            class="drag-position-hint"
          >
            <template #title>元素顺序断言</template>
            <p>按 <strong>DOM 文档顺序</strong>判断两个元素谁先谁后，适用于列表、表格行、树节点同级排序等场景。</p>
            <p class="drag-position-example">
              例：拖拽后断言「目录2」在「目录1」前面 →
              靠前元素=<code>#treebox nz-tree-node-title[title="拖拽目录2"]</code>，
              参照元素=<code>…[title="拖拽目录1"]</code>，
              期望顺序=<code>前面</code>
            </p>
            <p class="drag-position-example">
              断言「1 在 2 后面」可设期望顺序为「后面」，或交换两个定位表达式并保持「前面」。
            </p>
          </el-alert>
          <div 
            class="param-item" 
            v-for="(value, key) in filteredParams" 
            :key="key"
          >
            <div class="param-label">
              <span>{{ resolveParamLabel(key) }}</span>
              <span v-if="isRequiredParam(key)" class="required-mark">*</span>
              <el-tooltip
                v-if="resolveParamTooltip(key)"
                placement="top"
                :show-after="200"
                popper-class="param-tip-popper"
              >
                <template #content>
                  <div class="param-tip-content">{{ resolveParamTooltip(key) }}</div>
                </template>
                <el-icon class="param-tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            
            <!-- 根据参数类型渲染不同输入框 -->
            <template v-if="isAppObjectLocator(key)">
              <div v-if="form.params[key].by === 'image'" class="app-image-locator">
                <div class="app-locator-row">
                  <el-select v-model="form.params[key].by" placeholder="定位方式" style="width: 140px" @change="onAppLocatorByChange(key)">
                    <el-option v-for="opt in appLocatorByOptions(key)" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                  <el-upload
                    :show-file-list="false"
                    accept="image/png,image/jpeg,image/webp"
                    :http-request="(req) => handleStepTemplateUpload(req, key)"
                    :disabled="stepTemplateUploading"
                  >
                    <el-button type="primary" plain size="small" :loading="stepTemplateUploading">上传识别图</el-button>
                  </el-upload>
                </div>
                <div v-if="form.params[key].value" class="step-template-path">{{ form.params[key].value }}</div>
                <el-text type="info" size="small">图像识别定位暂不支持 AI 自愈</el-text>
                <el-image
                  v-if="stepTemplatePreviewSrc(key)"
                  :src="stepTemplatePreviewSrc(key)"
                  fit="contain"
                  class="step-template-preview"
                  :preview-src-list="[stepTemplatePreviewSrc(key)]"
                />
                <div class="app-image-fields">
                  <span class="field-label">相似度阈值</span>
                  <el-slider
                    v-model="form.params[key].threshold"
                    :min="0.5"
                    :max="1"
                    :step="0.05"
                    :disabled="false"
                    style="flex: 1"
                  />
                  <span class="field-label">RGB</span>
                  <el-switch v-model="form.params[key].rgb" />
                </div>
                <div class="app-image-fields">
                  <span class="field-label">中心偏移</span>
                  <el-input
                    :model-value="formatLocatorPair(form.params[key].record_pos)"
                    placeholder="相对屏幕中心，如 0.12,-0.05"
                    :disabled="false"
                    style="flex: 1"
                    @update:model-value="(v) => setLocatorPair(form.params[key], 'record_pos', v)"
                  />
                  <span class="field-label">录制分辨率</span>
                  <el-input
                    :model-value="formatLocatorPair(form.params[key].resolution)"
                    placeholder="宽,高，如 1080,2400"
                    :disabled="false"
                    style="flex: 1"
                    @update:model-value="(v) => setLocatorPair(form.params[key], 'resolution', v)"
                  />
                </div>
              </div>
              <div v-else class="app-locator-row">
                <el-select
                  v-model="form.params[key].context"
                  placeholder="定位环境"
                  style="width: 130px"
                  @change="onAppLocatorContextChange(key)"
                >
                  <el-option label="原生 App" :value="APP_LOCATOR_CONTEXT_NATIVE" />
                  <el-option label="WebView / H5" value="webview" />
                </el-select>
                <el-select v-model="form.params[key].by" placeholder="定位方式" style="width: 140px" @change="onAppLocatorByChange(key)">
                  <el-option v-for="opt in appLocatorByOptions(key)" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <el-input v-model="form.params[key].value" placeholder="定位值" style="flex: 1" @input="onAppLocatorFieldEdited" />
                <el-input-number v-model="form.params[key].index" :min="1" :max="99" controls-position="right" style="width: 100px" @change="onAppLocatorFieldEdited" />
                <el-button type="primary" link :loading="healingLocator" @click="handleHealLocator">AI 自愈</el-button>
              </div>
            </template>
            <template v-else-if="isAppLocatorRefKey(key)">
              <div class="locator-ref-row">
                <el-select
                  v-model="form.params[key]"
                  filterable
                  clearable
                  placeholder="选择元素库引用（同步到上方定位，可再编辑）"
                  style="flex: 1"
                  @change="onLocatorRefChange"
                >
                  <el-option v-for="opt in appElementOptions" :key="opt.name" :label="opt.name" :value="opt.name">
                    <span>{{ opt.name }}</span>
                    <span style="color: #909399; margin-left: 8px">{{ formatElementLocator(opt.locator) }}</span>
                  </el-option>
                </el-select>
                <el-button type="primary" link @click="openAppInspector">元素探查</el-button>
              </div>
            </template>
            <template v-else-if="isLocatorKey(key)">
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
        <ConditionEdit v-model:branches="form.branches" :module="module" />
      </el-form-item>
      
      <!-- 高级配置（App 步骤使用 params 内超时，不展示此项） -->
      <el-form-item label="高级配置" v-if="!isConditionBranch && !isAppStep">
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
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ConditionEdit from './ConditionEdit.vue'
import LocatorSelector from '@/components/LocatorSelector.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DataFactoryTagPicker from '@/views/ApiModule/components/DataFactoryTagPicker.vue'
import UiDbAssertStepFields from './UiDbAssertStepFields.vue'
import UiTestFilePicker from './UiTestFilePicker.vue'
import UiTestMultiFilePicker from './UiTestMultiFilePicker.vue'
import UiTestFolderPicker from './UiTestFolderPicker.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { insertVarRef } from '@/utils/varInsert.js'
import { getOrderedVisibleParams, getParamLabel, getParamTooltip, isDragDropMethod, isElementOrderMethod, isAssertionMethod } from '@/utils/uiStepMeta.js'
import { getAppOrderedVisibleParams, getAppParamLabel, getAppParamTooltip, isAppMethod, isAppRequiredParam, getAppSelectOptions, validateAppStepParams, validateAppBranchConditions, getAppLocatorByOptions, isWebviewLocator, isImageLocator, isAppLocatorFilled, APP_LOCATOR_CONTEXT_NATIVE, applyDefaultAppIdToStepParams, getProjectDefaultAppId, prepareAppLocatorForEdit, serializeAppLocatorForSave, normalizeAppLocator } from '@/utils/appStepMeta.js'
import { presignTemplateKeys, resolveTemplatePreviewUrl } from '@/utils/appTemplatePresign.js'
import AppH5UsageGuide from '@/components/App/AppH5UsageGuide.vue'
import { appElementApi } from '@/api/modules/app.js'
import { aiGenerateApi } from '@/api/modules/ai.js'

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const varInsertEnvId = inject('varInsertEnvId', ref(null))
const saveAppInspectorDraft = inject('saveAppInspectorDraft', null)
const envList = computed(() => proStore.envList || [])
const projectId = computed(() => proStore.projectInfo?.id)
const tagPickerVisible = ref(false)
const appElementOptions = ref([])
const stepTemplateUploading = ref(false)
const stepTemplatePreviewMap = ref({})

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
  },
  stepPath: {
    type: Array,
    default: () => [],
  },
  module: {
    type: String,
    default: 'web'
  },
  driverMode: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:visible', 'save', 'cancel'])

const formRef = ref()
const form = ref({
  id: '',
  keyword: '',
  desc: '',
  intent: '',
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

const effectiveStepPath = computed(() => {
  if (Array.isArray(props.stepPath) && props.stepPath.length) return props.stepPath
  if (props.stepIndex >= 0) return [props.stepIndex]
  return []
})

// 是否是编辑模式
const isEdit = computed(() => !!props.step?.id)

// 是否是 App 步骤（仅按编辑器 module 区分；Web/App 存在同名 method 如 extract_text、open_url）
const isAppStep = computed(() => props.module === 'app')

const H5_CONTEXT_METHODS = new Set(['switch_webview', 'switch_chrome', 'switch_native', 'open_url'])

const appFormHasH5Locator = computed(() => isWebviewLocator(form.value.params?.locator))
const appFormHasImageLocator = computed(() => isImageLocator(form.value.params?.locator))

const appStepGuideTitle = computed(() => {
  if (appFormHasImageLocator.value) return '本步骤图像识别说明'
  if (appFormHasH5Locator.value || H5_CONTEXT_METHODS.has(form.value.method)) return '本步骤 H5 / WebView 说明'
  return 'App 步骤说明'
})

const showAppH5StepGuide = computed(() => {
  if (!isAppStep.value) return false
  const method = form.value.method
  if (H5_CONTEXT_METHODS.has(method)) return true
  if (appFormHasH5Locator.value) return true
  if (appFormHasImageLocator.value) return true
  if (['hybrid_web', 'mobile_chrome'].includes(props.driverMode) && form.value.params?.locator) {
    return true
  }
  return false
})

const isConditionBranch = computed(() => {
  return form.value.method === 'condition_branch'
})

const isDbAssertStep = computed(() => form.value.method === 'kw_db_assert')

const isUploadFileStep = computed(() => form.value.method === 'upload_file')

const WEB_VISION_METHODS = new Set(['click_by_image', 'wait_for_image', 'kw_assert_image', 'kw_assert_image_not_exists'])
const isWebVisionStep = computed(
  () => !isAppStep.value && WEB_VISION_METHODS.has(form.value.method),
)

const webVisionHiddenKeys = new Set(['template', 'threshold'])

const uploadMode = computed({
  get: () => (form.value.params?.upload_mode || 'single'),
  set: (val) => {
    if (!form.value.params) form.value.params = {}
    form.value.params.upload_mode = val
  },
})

const isDragDropStep = computed(() => isDragDropMethod(form.value.method))

const isElementOrderStep = computed(() => isElementOrderMethod(form.value.method))

const paramsSectionLabel = computed(() =>
  isAssertionMethod(form.value.method) ? '断言参数' : '配置参数'
)

const uploadFileHiddenKeys = new Set([
  'file_path', 'file_key', 'file_bucket', 'file_name', 'upload_as_name', 'file_items',
  'upload_mode', 'folder_key', 'folder_bucket', 'folder_name',
])

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
  if (isWebVisionStep.value) {
    webVisionHiddenKeys.forEach((key) => delete raw[key])
  }
  if (!keepTimeoutMethods.includes(form.value.method) && !isAppStep.value) {
    delete raw.timeout
  }
  if (isAppStep.value) {
    return getAppOrderedVisibleParams(form.value.method, raw)
  }
  return getOrderedVisibleParams(form.value.method, raw)
})

// 是否有参数
const hasParams = computed(() => {
  return Object.keys(filteredParams.value).length > 0
})

function resolveParamLabel(key) {
  if (isAppStep.value) {
    return getAppParamLabel(form.value.method, key, paramLabelMap[key])
  }
  return getParamLabel(form.value.method, key, paramLabelMap[key])
}

function resolveParamTooltip(key) {
  if (isAppStep.value) {
    return getAppParamTooltip(form.value.method, key)
  }
  return getParamTooltip(form.value.method, key)
}

// 判断参数是否必填
function isRequiredParam(key) {
  const method = form.value.method
  if (isAppStep.value) {
    return isAppRequiredParam(method, key)
  }
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
    kw_assert_element_order: ['first_locator', 'second_locator'],
  }
  if (assertionRequired[method]) {
    return assertionRequired[method].includes(key)
  }
  if (WEB_VISION_METHODS.has(method)) {
    return key === 'template'
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
  first_locator: '靠前元素定位',
  second_locator: '靠后参照元素定位',
  first_index: '靠前元素索引',
  second_index: '参照元素索引',
  order: '期望顺序',
  source_position_x: '起始落点X(像素)',
  source_position_y: '起始落点Y(像素)',
  target_position_x: '目标落点X(像素)',
  target_position_y: '目标落点Y(像素)',
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

function repairWebStepParams(params) {
  if (!params || typeof params !== 'object') return params || {}
  const next = { ...params }
  for (const key of ['locator', 'selector', 'first_locator', 'second_locator']) {
    const v = next[key]
    if (v && typeof v === 'object' && v.by !== undefined) {
      next[key] = v.value != null ? String(v.value) : ''
    }
  }
  if (next.locator_ref != null) {
    delete next.locator_ref
  }
  return next
}

// 监听 step 变化
watch(() => props.step, (newStep) => {
  if (newStep) {
    // 确保条件分支有branches字段
    const stepData = { ...newStep }
    if (stepData.method === 'condition_branch' && !stepData.branches) {
      const defaultCond = props.module === 'app'
        ? { type: 'element_exist', locator: { by: 'resource_id', value: '', index: 1 }, operator: 'is_true' }
        : { type: 'element_visible', locator: '', operator: 'is_true' }
      stepData.branches = [
        {
          id: `branch_${Date.now()}`,
          name: '分支1',
          condition: defaultCond,
          steps: [],
        },
        {
          id: `else_branch_${Date.now()}`,
          name: '默认分支',
          condition: { type: 'else' },
          steps: [],
        },
      ]
    }
    const baseParams = props.module === 'app'
      ? { ...newStep.params }
      : repairWebStepParams(newStep.params)
    form.value = {
      ...stepData,
      params: baseParams,
      config: { timeout: 30000, retry: false, ...newStep.config },
      branches: newStep.branches ? JSON.parse(JSON.stringify(newStep.branches)) : undefined
    }
    if (isAppStep.value && isAppMethod(form.value.method)) {
      form.value.params = applyDefaultAppIdToStepParams(
        form.value.method,
        form.value.params || {},
        proStore.projectInfo,
        props.allSteps || []
      )
      if (form.value.params?.locator) {
        form.value.params.locator = prepareAppLocatorForEdit(form.value.params.locator)
      }
    }
  }
}, { immediate: true, deep: true })

watch(() => props.visible, (open) => {
  if (open && !varInsertEnvId.value && proStore.envList.length) {
    varInsertEnvId.value = proStore.envList[0].id
  }
  if (open && isAppStep.value) {
    loadAppElementOptions().then(() => {
      if (form.value.params?.locator_ref) {
        syncLocatorFromElementRef(form.value.params.locator_ref)
      }
    })
    const loc = form.value.params?.locator
    if (isImageLocator(loc) && loc?.value) {
      hydrateStepTemplatePreview(loc.value)
    }
    if (isAppMethod(form.value.method)) {
      form.value.params = applyDefaultAppIdToStepParams(
        form.value.method,
        form.value.params || {},
        proStore.projectInfo,
        props.allSteps || []
      )
    }
  }
})

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
  if (isAppStep.value) {
    return ['direction', 'key'].includes(key)
  }
  const selectKeys = ['wait_until', 'browser_type', 'operator', 'key', 'button', 'match_mode', 'order']
  return selectKeys.includes(key)
}

// 是否为定位表达式参数（使用 LocatorSelector 组件）
function isAppLocatorRefKey(key) {
  return isAppStep.value && key === 'locator_ref'
}

function formatElementLocator(locator) {
  if (!locator || typeof locator !== 'object') return ''
  return `${locator.by || ''}=${locator.value || ''}`
}

async function loadAppElementOptions() {
  if (!isAppStep.value || !proStore.projectInfo?.id) {
    appElementOptions.value = []
    return
  }
  try {
    const res = await appElementApi.options({ project_id: proStore.projectInfo.id })
    appElementOptions.value = res.data?.data || res.data || []
  } catch {
    appElementOptions.value = []
  }
}

function appLocatorByOptions(key) {
  return getAppLocatorByOptions(form.value.params?.[key])
}

function onAppLocatorContextChange(key) {
  const loc = form.value.params?.[key]
  if (!loc) return
  if (loc.context === 'webview' && !['css', 'xpath', 'text', 'id'].includes(loc.by)) {
    loc.by = 'css'
  }
  if (loc.context === APP_LOCATOR_CONTEXT_NATIVE && ['css', 'id'].includes(loc.by)) {
    loc.by = 'resource_id'
  }
  onAppLocatorFieldEdited()
}

function onAppLocatorByChange(key) {
  const loc = form.value.params?.[key]
  if (!loc) return
  if (loc.by === 'image') {
    loc.value = loc.value || ''
    loc.threshold = loc.threshold ?? 0.8
    loc.rgb = loc.rgb ?? false
    delete loc.index
    delete loc.context
    hydrateStepTemplatePreview(loc.value)
  } else {
    delete loc.threshold
    delete loc.rgb
    delete loc.record_pos
    delete loc.resolution
    if (String(loc.value || '').startsWith('app-elements/')) {
      loc.value = ''
    }
    if (!loc.context) {
      loc.context = APP_LOCATOR_CONTEXT_NATIVE
    }
    if (loc.by === 'resource_id' && !loc.index) {
      loc.index = 1
    }
  }
  onAppLocatorFieldEdited()
}

function onAppLocatorFieldEdited() {
  if (form.value.params?.locator_ref) {
    form.value.params.locator_ref = ''
  }
}

function syncLocatorFromElementRef(refName) {
  const loc = form.value.params?.locator
  if (!loc || !refName) return
  const found = appElementOptions.value.find((opt) => opt.name === refName)
  if (!found?.locator) return
  const synced = prepareAppLocatorForEdit(JSON.parse(JSON.stringify(found.locator)))
  Object.assign(loc, synced)
  if (isImageLocator(synced) && synced.value) {
    hydrateStepTemplatePreview(synced.value)
  }
}

function onLocatorRefChange(val) {
  if (!val) return
  syncLocatorFromElementRef(val)
}

function formatLocatorPair(value) {
  if (value == null || value === '') return ''
  if (Array.isArray(value) && value.length >= 2) return `${value[0]},${value[1]}`
  if (typeof value === 'object' && value.x != null && value.y != null) return `${value.x},${value.y}`
  return String(value)
}

function setLocatorPair(loc, field, text) {
  if (!loc) return
  const parts = String(text || '').split(',').map((s) => s.trim()).filter(Boolean)
  if (parts.length >= 2) {
    const a = Number(parts[0])
    const b = Number(parts[1])
    if (!Number.isNaN(a) && !Number.isNaN(b)) loc[field] = [a, b]
  } else {
    delete loc[field]
  }
}

async function hydrateStepTemplatePreview(objectKey) {
  if (!objectKey || String(objectKey).startsWith('http')) return
  const urlMap = await presignTemplateKeys([objectKey], projectId.value)
  stepTemplatePreviewMap.value = { ...stepTemplatePreviewMap.value, ...urlMap }
}

function stepTemplatePreviewSrc(key) {
  const value = form.value.params?.[key]?.value
  return resolveTemplatePreviewUrl(value, stepTemplatePreviewMap.value)
}

async function handleStepTemplateUpload(options, key) {
  const file = options.file
  if (!file || !projectId.value) return
  stepTemplateUploading.value = true
  try {
    const res = await appElementApi.uploadTemplate(projectId.value, file)
    const data = res.data?.data || res.data
    const objectKey = data?.object_key || ''
    const accessUrl = data?.access_url || ''
    if (!objectKey) {
      ElMessage.error('上传失败')
      return
    }
    const loc = form.value.params?.[key]
    if (loc) {
      loc.by = 'image'
      loc.value = objectKey
      loc.threshold = loc.threshold ?? 0.8
      loc.rgb = loc.rgb ?? false
    }
    if (accessUrl) {
      stepTemplatePreviewMap.value = { ...stepTemplatePreviewMap.value, [objectKey]: accessUrl }
    }
    ElMessage.success('识别图已上传')
  } catch (e) {
    ElMessage.error('识别图上传失败')
  } finally {
    stepTemplateUploading.value = false
  }
}

const webVisionPreviewSrc = computed(() => {
  const key = form.value.params?.template
  return resolveTemplatePreviewUrl(key, stepTemplatePreviewMap.value)
})

async function handleWebVisionTemplateUpload(options) {
  const file = options.file
  if (!file || !projectId.value) return
  stepTemplateUploading.value = true
  try {
    const res = await appElementApi.uploadTemplate(projectId.value, file)
    const data = res.data?.data || res.data
    const objectKey = data?.object_key || ''
    const accessUrl = data?.access_url || ''
    if (!objectKey) {
      ElMessage.error('上传失败')
      return
    }
    if (!form.value.params) form.value.params = {}
    form.value.params.template = objectKey
    form.value.params.threshold = form.value.params.threshold ?? 0.8
    if (accessUrl) {
      stepTemplatePreviewMap.value = { ...stepTemplatePreviewMap.value, [objectKey]: accessUrl }
    } else {
      await hydrateStepTemplatePreview(objectKey)
    }
    ElMessage.success('模板图已上传')
  } catch (e) {
    ElMessage.error('模板图上传失败')
  } finally {
    stepTemplateUploading.value = false
  }
}

import { setAppInspectorContext, setAppInspectorCaseDraft } from '@/utils/appInspectorContext.js'

function openAppInspector() {
  if (!isAppStep.value) {
    router.push({ name: 'appInspector' })
    return
  }
  if (typeof saveAppInspectorDraft === 'function') {
    saveAppInspectorDraft()
  }
  setAppInspectorContext({
    returnPath: route.fullPath,
    returnName: route.name,
    stepPath: effectiveStepPath.value,
    stepIndex: effectiveStepPath.value[effectiveStepPath.value.length - 1],
    driverMode: props.driverMode || 'hybrid',
    caseId: route.params.id || null,
    projectId: proStore.projectInfo?.id || null,
  })
  router.push({ name: 'appInspector', query: { from: 'step_edit' } })
}

function isAppObjectLocator(key) {
  if (!isAppStep.value) return false
  const val = form.value.params?.[key]
  return key === 'locator' && val && typeof val === 'object' && val.by !== undefined
}

function isLocatorKey(key) {
  if (isAppObjectLocator(key)) return false
  return ['locator', 'selector', 'first_locator', 'second_locator'].includes(key)
}

function canInsertVar(key) {
  return !isLocatorKey(key) && !isNumber(form.value.params?.[key]) && !isBoolean(key) && !isSelect(key)
}

async function handleHealLocator() {
  if (isAppStep.value) {
    return handleAppHealLocator()
  }
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

async function handleAppHealLocator() {
  const locator = form.value.params?.locator
  if (!locator || !isAppLocatorFilled(locator)) {
    ElMessage.warning('请先填写定位器')
    return
  }
  if (isImageLocator(locator)) {
    ElMessage.warning('图像识别定位暂不支持 AI 自愈')
    return
  }
  healingLocator.value = true
  try {
    const res = await aiGenerateApi.healAppLocator({
      method: form.value.method,
      failed_locator: serializeAppLocatorForSave(locator),
      step_desc: form.value.desc,
      step_intent: form.value.intent || undefined,
    })
    if (res.data?.code === 200 && res.data.data?.locator) {
      form.value.params.locator = prepareAppLocatorForEdit(res.data.data.locator)
      ElMessage.success(`已应用新定位器（${res.data.data.confidence || 'medium'}）`)
    } else {
      ElMessage.error(res.data?.data?.reason || res.data?.message || '自愈失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自愈请求失败')
  } finally {
    healingLocator.value = false
  }
}

async function confirmHeal() {
  const locatorKey = Object.keys(form.value.params || {}).find(k => isLocatorKey(k))
  const failed = (form.value.params[locatorKey] || '').trim()
  const payload = {
    method: form.value.method,
    failed_locator: failed,
    step_desc: form.value.desc,
    step_intent: form.value.intent || undefined,
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
  if (isAppStep.value) {
    return getAppSelectOptions(key)
  }
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
    ],
    order: [
      { label: '前面（第一个在第二个之前）', value: 'before' },
      { label: '后面（第一个在第二个之后）', value: 'after' }
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
      const mode = (p.upload_mode || 'single').toLowerCase()
      if (mode === 'folder') {
        const hasPlatformFolder = !!(p.folder_key && p.folder_bucket)
        const hasLegacyPath = !!(p.file_path && String(p.file_path).trim())
        if (!hasPlatformFolder && !hasLegacyPath) {
          ElMessage.warning('请选择测试文件夹，或填写 Runner 本地路径')
          return
        }
      } else if (mode === 'multiple') {
        const items = Array.isArray(p.file_items) ? p.file_items : []
        const hasItems = items.some((it) => it?.file_key && it?.file_bucket)
        if (!hasItems) {
          ElMessage.warning('请至少选择一个测试文件')
          return
        }
      } else {
        const hasPlatformFile = !!(p.file_key && p.file_bucket)
        const hasLegacyPath = !!(p.file_path && String(p.file_path).trim())
        if (!hasPlatformFile && !hasLegacyPath) {
          ElMessage.warning('请选择测试文件，或填写 Runner 本地路径')
          return
        }
      }
    }
    // App / Web 步骤参数校验
    if (isAppStep.value) {
      const appErr = validateAppStepParams(form.value.method, form.value.params)
      if (appErr) {
        ElMessage.warning(appErr)
        return
      }
    } else {
      for (const key of Object.keys(filteredParams.value)) {
        if (isRequiredParam(key)) {
          const value = form.value.params[key]
          if (!value || (typeof value === 'string' && value.trim() === '')) {
            ElMessage.warning(`请填写${resolveParamLabel(key)}`)
            return
          }
        }
      }
    }
  }

  if (isConditionBranch.value && isAppStep.value) {
    const branchErr = validateAppBranchConditions(form.value.branches)
    if (branchErr) {
      ElMessage.warning(branchErr)
      return
    }
  }
  
  // 构建保存的步骤数据
  const savedStep = { 
    ...form.value,
    keyword: form.value.keyword,
    method: form.value.method || form.value.keyword,
    params: { ...(form.value.params || {}) },
  }
  const intent = (savedStep.intent || '').trim()
  if (intent) {
    savedStep.intent = intent
  } else {
    delete savedStep.intent
  }
  if (isAppStep.value) {
    if (savedStep.params?.locator) {
      savedStep.params.locator = serializeAppLocatorForSave(savedStep.params.locator)
    }
    if (!savedStep.params?.locator_ref) {
      delete savedStep.params.locator_ref
    }
  }
  
  // 条件分支特殊处理
  if (isConditionBranch.value) {
    savedStep.is_container = true
    // 确保branches字段存在
    if (!savedStep.branches || savedStep.branches.length === 0) {
      const defaultCond = isAppStep.value
        ? { type: 'element_exist', locator: { by: 'resource_id', value: '', index: 1 }, operator: 'is_true' }
        : { type: 'element_visible', locator: '', operator: 'is_true' }
      savedStep.branches = [
        {
          id: `branch_${Date.now()}`,
          name: '分支1',
          condition: defaultCond,
          steps: [],
        },
        {
          id: `else_branch_${Date.now()}`,
          name: '默认分支',
          condition: { type: 'else' },
          steps: [],
        },
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
    intent: '',
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

.drag-position-hint {
  margin-bottom: 4px;

  p {
    margin: 0 0 6px;
    font-size: 13px;
    line-height: 1.55;
    color: var(--el-text-color-regular);
  }

  .drag-position-example {
    margin-bottom: 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);

    code {
      padding: 0 4px;
      border-radius: 3px;
      background: var(--el-fill-color);
      font-size: 12px;
    }
  }
}

.param-item {
  width: 100%;
  
  .param-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: var(--el-text-color-secondary);
    margin-bottom: 6px;
    
    .required-mark {
      color: var(--el-color-danger);
    }

    .param-tip-icon {
      font-size: 14px;
      color: var(--el-color-primary);
      cursor: help;
      vertical-align: middle;
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

.app-locator-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.app-image-locator {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.app-image-fields {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-image-fields .field-label {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.step-template-path {
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}

.web-vision-template {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.web-vision-template-input {
  max-width: 520px;
}
.web-vision-threshold {
  display: flex;
  align-items: center;
  gap: 12px;
}
.step-template-preview {
  width: 72px;
  height: 72px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}

.locator-ref-row {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
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

.step-intent-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
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

<style lang="scss">
.param-tip-popper {
  max-width: 360px;

  .param-tip-content {
    font-size: 13px;
    line-height: 1.55;
    white-space: pre-line;
  }
}
</style>
