<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="接口调试"
    width="900px"
    destroy-on-close
    class="debug-dialog"
    @closed="handleClosed"
  >
    <div class="debug-container">
      <!-- 环境选择 -->
      <div class="env-selector">
        <span class="env-label">执行环境:</span>
        <el-select v-model="selectedEnvId" placeholder="选择环境（可选）" clearable size="small" style="width: 200px;">
          <el-option
            v-for="env in proStore.envList"
            :key="env.id"
            :label="env.name"
            :value="env.id"
          />
        </el-select>
        <span v-if="selectedEnv?.host" class="env-host">{{ selectedEnv.host }}</span>
        <el-button
          v-if="selectedEnvId"
          type="primary"
          link
          size="small"
          @click="varEditVisible = true"
          icon="Edit"
        >编辑变量</el-button>
        <VarInsertButton
          v-if="selectedEnvId"
          :env-id="selectedEnvId"
          @edit-env-vars="varEditVisible = true"
        />
      </div>
      <VariablePreviewPanel
        v-if="selectedEnvId"
        :env-id="selectedEnvId"
        :samples="previewSamples"
      />
      
      <!-- 请求配置 -->
      <div class="request-panel">
        <div class="panel-header">
          <el-select v-model="request.method" size="small" style="width: 100px;">
            <el-option v-for="m in methods" :key="m" :label="m" :value="m"/>
          </el-select>
          <el-input v-model="request.url" placeholder="请输入请求URL" size="small">
            <template #prepend>
              <el-select v-model="request.base_url" size="small" style="width: 150px;" placeholder="基础URL">
                <el-option label="使用接口配置" value=""/>
                <el-option label="自定义" value="custom"/>
              </el-select>
              <el-input 
                v-if="request.base_url === 'custom'" 
                v-model="customBaseUrl" 
                size="small" 
                placeholder="http://localhost:8080"
                style="width: 180px; margin-left: 10px;"
              />
            </template>
          </el-input>
          <el-button type="primary" size="small" @click="sendRequest" :loading="loading" icon="Promotion">
            发送
          </el-button>
        </div>
        
        <el-tabs v-model="activeTab" class="debug-tabs">
          <el-tab-pane label="Params" name="params">
            <el-table :data="request.params" size="small" border>
              <el-table-column label="参数名" width="180">
                <template #default="{ $index }">
                  <el-input v-model="request.params[$index].name" size="small"/>
                </template>
              </el-table-column>
              <el-table-column label="参数值">
                <template #default="{ $index }">
                  <el-input v-model="request.params[$index].value" size="small"/>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ $index }">
                  <el-button type="danger" link size="small" @click="removeParam($index)" icon="Delete"/>
                </template>
              </el-table-column>
            </el-table>
            <el-button type="primary" link size="small" @click="addParam" icon="Plus" class="add-btn">
              添加参数
            </el-button>
          </el-tab-pane>
          
          <el-tab-pane label="Headers" name="headers">
            <HeaderEditorPanel
              v-model="request.headers"
              local-title="本请求 Header"
              :show-description="false"
            />
          </el-tab-pane>
          
          <el-tab-pane label="Body" name="body" v-if="['POST', 'PUT', 'PATCH'].includes(request.method)">
            <el-radio-group v-model="request.body_type" size="small" class="body-type">
              <el-radio-button label="json">JSON</el-radio-button>
              <el-radio-button label="form-data">Form Data</el-radio-button>
              <el-radio-button label="x-www-form-urlencoded">x-www-form-urlencoded</el-radio-button>
              <el-radio-button label="xml">XML</el-radio-button>
              <el-radio-button label="raw">Raw</el-radio-button>
              <el-radio-button label="binary">Binary</el-radio-button>
            </el-radio-group>
            <template v-if="request.body_type === 'form-data'">
              <div class="section-title compact">
                <span>Form Data 字段</span>
                <el-button type="primary" link size="small" @click="addFormField">添加</el-button>
              </div>
              <el-table :data="request.body_fields" size="small" border>
                <el-table-column label="字段名" width="180">
                  <template #default="{ $index }">
                    <el-input v-model="request.body_fields[$index].name" size="small" placeholder="file" />
                  </template>
                </el-table-column>
                <el-table-column label="类型" width="120">
                  <template #default="{ $index }">
                    <el-select v-model="request.body_fields[$index].field_type" size="small">
                      <el-option label="文本" value="text" />
                      <el-option label="文件" value="file" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="值 / 文件" min-width="260">
                  <template #default="{ $index }">
                    <div class="file-field-cell">
                      <template v-if="request.body_fields[$index].field_type === 'file'">
                        <el-button size="small" @click="triggerFormFilePick($index)">选择并上传文件</el-button>
                        <span v-if="request.body_fields[$index].file_name" class="file-meta-name">{{ request.body_fields[$index].file_name }}</span>
                        <input :ref="(el) => setFormFileInput(el, $index)" class="hidden-file-input" type="file" @change="(e) => handleFormFileChange(e, $index)" />
                      </template>
                      <el-input v-else v-model="request.body_fields[$index].value" size="small" placeholder="文本值" />
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="MIME" width="180">
                  <template #default="{ $index }">
                    <el-input v-model="request.body_fields[$index].mime_type" size="small" placeholder="application/octet-stream" />
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="60">
                  <template #default="{ $index }">
                    <el-button type="danger" link size="small" @click="removeFormField($index)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>
            <JsonTextarea
              v-else
              v-model="bodyText"
              :rows="8"
              input-class="body-editor"
              :placeholder="bodyPlaceholder"
              :json-mode="request.body_type === 'json'"
              show-compact
            />
          </el-tab-pane>
        </el-tabs>
      </div>
      
      <!-- 响应结果 -->
      <div class="response-panel" v-if="response">
        <div class="response-header">
          <div class="response-status">
            <span class="status-code" :class="getStatusClass(response.status_code)">
              {{ response.status_code }}
            </span>
            <span class="response-time">{{ response.time.toFixed(0) }} ms</span>
            <span class="response-size">{{ formatSize(response.size) }}</span>
          </div>
        </div>
        
        <el-tabs v-model="responseTab" class="response-tabs">
          <el-tab-pane label="Body" name="body">
            <CopyablePre :text="responseBodyText" max-height="480px" fill min-height="240px" />
          </el-tab-pane>
          
          <el-tab-pane label="Headers" name="headers">
            <div class="response-tab-toolbar">
              <CopyTextButton :text="response.headers" />
            </div>
            <el-table :data="responseHeaders" size="small" border>
              <el-table-column label="Header名" prop="key" width="250"/>
              <el-table-column label="Header值" prop="value"/>
            </el-table>
          </el-tab-pane>
          
          <el-tab-pane label="Request" name="request">
            <div class="request-info">
              <p class="request-info-line">
                <strong>URL（替换后）:</strong>
                <span class="request-info-value">{{ resolvedRequestDisplay.url }}</span>
                <CopyTextButton :text="resolvedRequestDisplay.url" label="" />
              </p>
              <p v-if="resolvedRequestDisplay.urlOriginal && resolvedRequestDisplay.urlOriginal !== resolvedRequestDisplay.url" class="request-info-line request-info-line--muted">
                <strong>原始 URL:</strong>
                <span class="request-info-value">{{ resolvedRequestDisplay.urlOriginal }}</span>
              </p>
              <p><strong>Method:</strong> {{ resolvedRequestDisplay.method }}</p>
              <div v-if="resolvedRequestDisplay.params && Object.keys(resolvedRequestDisplay.params).length" class="request-info-block">
                <div class="response-tab-toolbar">
                  <strong>Params（替换后）:</strong>
                  <CopyTextButton :text="resolvedRequestDisplay.params" />
                </div>
                <CopyablePre :text="resolvedRequestDisplay.params" max-height="200px" wrap />
              </div>
              <div class="request-info-block">
                <div class="response-tab-toolbar">
                  <strong>Headers（替换后）:</strong>
                  <CopyTextButton :text="resolvedRequestDisplay.headers" />
                </div>
                <CopyablePre :text="resolvedRequestDisplay.headers" max-height="280px" wrap />
              </div>
              <div v-if="hasResolvedRequestBody" class="request-info-block">
                <div class="response-tab-toolbar">
                  <strong>Body（替换后）:</strong>
                  <CopyTextButton :text="resolvedRequestDisplay.body" />
                </div>
                <CopyablePre :text="resolvedRequestDisplay.body" max-height="320px" wrap />
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
      
      <el-empty v-else description="点击发送按钮开始调试" class="response-empty"/>
    </div>
  </el-dialog>

  <EnvVarQuickEdit v-model="varEditVisible" :env-id="selectedEnvId" />
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import EnvVarQuickEdit from './EnvVarQuickEdit.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import VariablePreviewPanel from '@/components/VariablePreviewPanel.vue'
import CopyTextButton from '@/components/CopyTextButton.vue'
import CopyablePre from '@/components/CopyablePre.vue'
import JsonTextarea from '@/components/JsonTextarea.vue'
import HeaderEditorPanel from '@/components/HeaderEditorPanel.vue'

const props = defineProps({
  modelValue: Boolean,
  api: Object
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
const activeTab = ref('params')
const responseTab = ref('body')
const loading = ref(false)
const response = ref(null)
const customBaseUrl = ref('')
const selectedEnvId = ref(null)
const varEditVisible = ref(false)

// 当前选中的环境
const selectedEnv = computed(() => {
  if (!selectedEnvId.value) return null
  return proStore.envList.find(e => e.id === selectedEnvId.value)
})

const previewSamples = computed(() => {
  const samples = []
  if (request.url) samples.push(String(request.url))
  return samples
})

const responseBodyText = computed(() => {
  if (!response.value) return ''
  if (typeof response.value.body === 'object') {
    try {
      return JSON.stringify(response.value.body, null, 2)
    } catch {
      return String(response.value.body)
    }
  }
  return String(response.value.body ?? '')
})

/** 实际发出的请求（优先 request_detail.final，兼容旧 request 字段） */
const resolvedRequestDisplay = computed(() => {
  const data = response.value
  if (!data) {
    return { url: '', urlOriginal: '', method: '', headers: {}, params: {}, body: null }
  }
  const rd = data.request_detail || {}
  const req = data.request || {}
  const headersFinal = rd.headers?.final ?? normalizeHeadersForDisplay(req.headers)
  const paramsFinal = rd.params?.final ?? normalizeParamsForDisplay(req.params)
  return {
    url: rd.url?.final ?? req.url ?? '',
    urlOriginal: rd.url?.original ?? '',
    method: (req.method || request.method || 'GET').toUpperCase(),
    headers: headersFinal,
    params: paramsFinal,
    body: rd.body?.final ?? req.body,
  }
})

const hasResolvedRequestBody = computed(() => {
  const body = resolvedRequestDisplay.value.body
  if (body === null || body === undefined || body === '') return false
  if (typeof body === 'object' && !Array.isArray(body)) return Object.keys(body).length > 0
  return true
})

function normalizeHeadersForDisplay(headers) {
  if (!headers) return {}
  if (Array.isArray(headers)) {
    return headers.reduce((acc, h) => {
      if (h?.key) acc[h.key] = h.value ?? ''
      return acc
    }, {})
  }
  return typeof headers === 'object' ? headers : {}
}

function normalizeParamsForDisplay(params) {
  if (!params) return {}
  if (Array.isArray(params)) {
    return params.reduce((acc, p) => {
      if (p?.name) acc[p.name] = p.value ?? ''
      return acc
    }, {})
  }
  return typeof params === 'object' ? params : {}
}

const VAR_PLACEHOLDER_RE = /\$\{\{[^}]+\}\}|\$\{[^}]+\}/

function extractApiErrorMessage(error) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || d.message || JSON.stringify(d)).join('；')
  }
  if (error?.message) return error.message
  return '请求失败，请稍后重试'
}

function validateBeforeSend(fullUrl) {
  const hasPlaceholder =
    VAR_PLACEHOLDER_RE.test(fullUrl) ||
    request.headers.some((h) => VAR_PLACEHOLDER_RE.test(String(h.value || ''))) ||
    request.params.some((p) => VAR_PLACEHOLDER_RE.test(String(p.value || '')))

  if (hasPlaceholder && !selectedEnvId.value) {
    ElMessage.warning('请求中含有环境变量占位符，请先选择执行环境')
    return false
  }

  const isAbsolute = /^https?:\/\//i.test(fullUrl)
  if (!selectedEnvId.value && !isAbsolute) {
    if (request.base_url === 'custom' && customBaseUrl.value?.trim()) {
      return true
    }
    ElMessage.warning('未选择执行环境且 URL 非绝对地址，请选择环境或填写带 http(s):// 的完整 URL')
    return false
  }
  return true
}

const request = reactive({
  method: 'GET',
  url: '',
  base_url: '',
  headers: [],
  params: [],
  body: null,
  body_fields: [],
  body_type: 'json'
})

const bodyText = ref('')

const isStructuredBodyType = (type) => ['json'].includes(type)

const syncBodyText = () => {
  if (request.body === null || request.body === undefined || request.body === '') {
    bodyText.value = ''
    return
  }
  // 空对象在所有类型下都显示空字符串，避免 [object Object]
  if (typeof request.body === 'object' && !Array.isArray(request.body) && Object.keys(request.body).length === 0) {
    bodyText.value = ''
    return
  }
  if (typeof request.body === 'string') {
    bodyText.value = request.body
    return
  }
  if (isStructuredBodyType(request.body_type)) {
    try {
      bodyText.value = JSON.stringify(request.body, null, 2)
    } catch {
      bodyText.value = String(request.body)
    }
    return
  }
  bodyText.value = String(request.body)
}

const isJsonResponse = computed(() => {
  if (!response.value) return false
  return typeof response.value.body === 'object'
})

const responseHeaders = computed(() => {
  if (!response.value) return []
  return Object.entries(response.value.headers).map(([key, value]) => ({
    key,
    value: Array.isArray(value) ? value.join(', ') : value
  }))
})

const bodyPlaceholder = computed(() => {
  switch (request.body_type) {
    case 'form-data':
      return '请通过“选择并上传文件”添加文件字段'
    case 'x-www-form-urlencoded':
      return '示例：name=张三&age=18'
    case 'xml':
      return '<xml>...</xml>'
    case 'raw':
      return '任意文本内容'
    case 'binary':
      return '请上传单个文件并在后端调试时使用 MinIO 引用'
    default:
      return '{"key": "value"}'
  }
})

const mapBodyFields = (fields) =>
  Array.isArray(fields)
    ? fields.map(f => ({
        name: f.name || '',
        value: f.value || '',
        field_type: f.field_type || 'text',
        file_name: f.file_name || '',
        mime_type: f.mime_type || 'application/octet-stream',
        file_key: f.file_key || '',
        file_bucket: f.file_bucket || '',
        description: f.description || ''
      }))
    : []

const applyApiToRequest = (val) => {
  if (!val) return
  request.method = val.method || 'GET'
  request.url = val.path || ''
  request.base_url = val.base_url || ''
  request.headers = val.headers || []
  request.params = val.params || []
  request.body = val.body ?? null
  request.body_fields = mapBodyFields(val.body_fields)
  request.body_type = val.body_type || 'json'
  syncBodyText()
  if (request.body_type === 'form-data') {
    activeTab.value = 'body'
  }
}

const fetchApiDetail = async (apiId) => {
  try {
    const res = await http.apiModuleApi.getApiDetail(apiId)
    if (res.status === 200 && res.data) {
      applyApiToRequest(res.data)
    }
  } catch {
    ElMessage.error('获取接口详情失败')
  }
}

// 监听 API 变化（先用列表行数据快速填充）
watch(() => props.api, (val) => {
  if (val) applyApiToRequest(val)
  response.value = null
}, { immediate: true })

// 弹窗打开后拉取详情，补全 body_fields 等列表未返回字段
watch(() => [props.modelValue, props.api?.id], ([visible, id]) => {
  if (visible && id) {
    nextTick(() => fetchApiDetail(id))
  }
})

// 弹窗关闭后重置
const handleClosed = () => {
  selectedEnvId.value = null
  response.value = null
  customBaseUrl.value = ''
  request.base_url = ''
  formFileInputs.value = []
  request.body_fields = []
  bodyText.value = ''
}

const addParam = () => {
  request.params.push({ name: '', value: '' })
}

const removeParam = (index) => {
  request.params.splice(index, 1)
}

const formFileInputs = ref([])

const setFormFileInput = (el, index) => {
  if (el) formFileInputs.value[index] = el
}

const addFormField = () => {
  request.body_fields.push({
    name: '',
    value: '',
    field_type: 'text',
    file_name: '',
    mime_type: 'application/octet-stream',
    file_key: '',
    file_bucket: '',
    description: ''
  })
}

const triggerFormFilePick = (index) => {
  const input = formFileInputs.value[index]
  input?.click()
}

const handleFormFileChange = async (event, index) => {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const res = await http.apiModuleApi.uploadBodyFile(file)
    const data = res.data
    request.body_fields[index].file_name = data.file_name
    request.body_fields[index].mime_type = data.mime_type || file.type || 'application/octet-stream'
    request.body_fields[index].file_bucket = data.file_bucket
    request.body_fields[index].file_key = data.file_key
    request.body_fields[index].value = ''
    ElMessage.success('文件上传成功')
  } catch (error) {
    ElMessage.error('文件上传失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    event.target.value = ''
  }
}

const removeFormField = (index) => {
  request.body_fields.splice(index, 1)
}

const getStatusClass = (code) => {
  if (code >= 200 && code < 300) return 'success'
  if (code >= 300 && code < 400) return 'warning'
  return 'error'
}

const formatSize = (size) => {
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(2) + ' KB'
  return (size / 1024 / 1024).toFixed(2) + ' MB'
}

const validateFormDataFields = () => {
  if (request.body_type !== 'form-data') return true
  const invalidField = request.body_fields.find(f => f.field_type === 'file' && !f.file_key)
  if (invalidField) {
    ElMessage.error(`字段 ${invalidField.name || '未命名'} 需要先上传文件`)
    return false
  }
  return true
}

const sendRequest = async () => {
  if (!request.url) {
    ElMessage.warning('请输入请求URL')
    return
  }
  if (!validateFormDataFields()) return

  const baseUrl = request.base_url === 'custom' ? customBaseUrl.value : request.base_url
  let fullUrl = request.url
  if (baseUrl) {
    const cleanBase = baseUrl.replace(/\/$/, '')
    const cleanPath = request.url.replace(/^\//, '')
    fullUrl = cleanBase + '/' + cleanPath
  }
  if (!validateBeforeSend(fullUrl)) return

  loading.value = true
  try {

    let body = request.body
    if (request.body_type === 'form-data') {
      body = null
    } else if (isStructuredBodyType(request.body_type) && typeof bodyText.value === 'string' && bodyText.value.trim()) {
      try {
        body = JSON.parse(bodyText.value)
      } catch {
        ElMessage.error('请求体 JSON 格式错误，请检查')
        return
      }
    } else {
      body = bodyText.value
    }

    request.body = body

    const res = await http.apiModuleApi.debugApi({
      method: request.method,
      url: fullUrl,
      headers: request.headers,
      params: request.params,
      body,
      body_fields: request.body_fields.map(f => ({ ...f })),
      body_type: request.body_type,
      timeout: 30,
      env_id: selectedEnvId.value || undefined,
      project_id: proStore.projectInfo?.id || undefined,
    })

    if (res.status === 200) {
      response.value = res.data
      responseTab.value = 'body'
    }
  } catch (error) {
    ElMessage.error(extractApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.debug-dialog {
  :deep(.el-dialog__body) {
    padding: 10px 20px 20px;
  }
}

.debug-container {
  display: flex;
  flex-direction: column;
  gap: 15px;
  min-height: 400px;
}

.env-selector {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 15px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  
  .env-label {
    font-size: 14px;
    color: var(--el-text-color-regular);
    font-weight: 500;
  }
  
  .env-host {
    font-size: 13px;
    color: var(--el-text-color-secondary);
    margin-left: 10px;
  }
}

.request-panel, .response-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  gap: 10px;
  padding: 15px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.debug-tabs, .response-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 0;
  }
  
  :deep(.el-tabs__content) {
    padding: 15px;
  }
}

.add-btn {
  margin-top: 10px;
}

.body-type {
  margin-bottom: 10px;
}

.body-editor {
  :deep(.el-textarea__inner) {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
  }
}

.file-field-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.file-meta-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hidden-file-input {
  display: none;
}

.response-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.response-header {
  padding: 15px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.response-status {
  display: flex;
  gap: 20px;
  align-items: center;
  
  .status-code {
    font-size: 18px;
    font-weight: bold;
    
    &.success {
      color: var(--el-color-success);
    }
    
    &.warning {
      color: var(--el-color-warning);
    }
    
    &.error {
      color: var(--el-color-danger);
    }
  }
  
  .response-time, .response-size {
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }
}

.response-tab-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.response-body {
  background: var(--el-fill-color-dark);
  padding: 15px;
  border-radius: 4px;
  max-height: 300px;
  overflow: auto;
  
  pre {
    margin: 0;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.request-info {
  padding: 15px;

  p {
    margin: 5px 0;
  }

  .request-info-line {
    display: flex;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 6px;
  }

  .request-info-line--muted {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .request-info-value {
    word-break: break-all;
  }

  .request-info-block {
    margin-top: 12px;
  }

  pre {
    background: var(--el-fill-color-light);
    padding: 10px;
    border-radius: 4px;
    font-size: 12px;
  }
}
</style>
