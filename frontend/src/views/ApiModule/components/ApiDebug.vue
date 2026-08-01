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
          hint-text="不含工厂标签；请用「数据工厂标签」或「插入工具」。"
        />
        <ToolInsertButton v-if="selectedEnvId" />
        <el-button
          v-if="selectedEnvId"
          type="info"
          link
          size="small"
          @click="tagPickerVisible = true"
        >数据工厂标签</el-button>
      </div>
      <VariablePreviewPanel
        v-if="selectedEnvId"
        :env-id="selectedEnvId"
        :samples="previewSamples"
      />

      <div v-if="!isWsApi" class="worker-selector">
        <el-checkbox v-model="viaWorker" @change="onViaWorkerChange">经执行机发送</el-checkbox>
        <el-select
          v-model="selectedWorkerId"
          placeholder="选择在线空闲执行机"
          size="small"
          clearable
          filterable
          :disabled="!viaWorker"
          style="width: 280px; margin-left: 8px;"
        >
          <el-option
            v-for="w in idleWorkers"
            :key="w.id"
            :label="`${w.name} (#${w.id}) · ${w.host} · 引擎 ${w.engine_version || '?'}`"
            :value="w.id"
          />
        </el-select>
        <el-button
          link
          type="primary"
          size="small"
          style="margin-left: 4px;"
          :loading="workersLoading"
          @click="loadWorkers"
        >刷新</el-button>
        <el-tooltip
          content="平台服务器访问不到被测系统时，勾选后由 BrickCorePerf / Runner 压测执行机代发请求。不勾选则仍由平台本机发送。执行机引擎需 ≥ 1.0.0。"
          placement="top"
        >
          <span class="worker-hint">?</span>
        </el-tooltip>
        <span v-if="viaWorker && !idleWorkers.length" class="worker-warn">
          暂无可用执行机（需在线空闲且引擎 ≥ {{ MIN_API_DEBUG_ENGINE }}）
        </span>
      </div>
      
      <!-- 请求配置 -->
      <div v-if="isWsApi" class="request-panel">
        <div class="panel-header">
          <el-tag type="warning" size="small">WebSocket</el-tag>
          <el-input v-model="request.url" placeholder="ws://host/path 或 /ws/echo" size="small" />
          <el-button type="primary" size="small" @click="sendWsRequest" :loading="loading" icon="Promotion">
            执行
          </el-button>
          <el-button type="success" size="small" plain :loading="savingCase" @click="openSaveAsCase">
            {{ saveCaseButtonLabel }}
          </el-button>
        </div>
        <el-tabs v-model="activeTab" class="debug-tabs">
          <el-tab-pane label="Headers" name="headers">
            <HeaderEditorPanel v-model="request.headers" local-title="连接 Header" :show-description="false" />
          </el-tab-pane>
          <el-tab-pane label="WS 步骤" name="ws-steps">
            <WsStepsEditor v-model="wsSteps" />
          </el-tab-pane>
        </el-tabs>
      </div>
      <div v-else class="request-panel">
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
          <el-button type="success" size="small" plain :loading="savingCase" @click="openSaveAsCase">
            {{ saveCaseButtonLabel }}
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
                      <ApiTestFilePicker
                        v-if="request.body_fields[$index].field_type === 'file'"
                        :model-value="request.body_fields[$index]"
                        @update:model-value="(v) => onFormFieldFileUpdate($index, v)"
                      />
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
  <DataFactoryTagPicker
    v-model="tagPickerVisible"
    :project-id="proStore.projectInfo?.id"
    @insert="onDfTagInsert"
  />

  <el-dialog v-model="saveCaseVisible" title="保存为用例" width="480px" append-to-body destroy-on-close>
    <el-form label-width="80px">
      <el-form-item label="用例名称" required>
        <el-input v-model="saveCaseName" maxlength="100" placeholder="用例名称" />
      </el-form-item>
      <el-alert
        v-if="fromPerfScene"
        type="info"
        :closable="false"
        show-icon
        title="保存成功后将返回压测场景，并把新用例追加到对应链路阶段。"
      />
    </el-form>
    <template #footer>
      <el-button @click="saveCaseVisible = false">取消</el-button>
      <el-button type="primary" :loading="savingCase" @click="submitSaveAsCase">
        {{ saveCaseButtonLabel }}
      </el-button>
    </template>
  </el-dialog>

  <el-dialog
    v-model="extractorWizard.visible"
    title="建议提取变量"
    width="560px"
    append-to-body
    :close-on-click-modal="false"
    @closed="onExtractorWizardClosed"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px;"
      title="根据本次调试响应，建议以下 JSONPath 提取项。勾选后写入用例，可在链路后续步骤用 ${变量名} 引用。"
    />
    <el-table :data="extractorWizard.suggestions" size="small" border max-height="320">
      <el-table-column width="50" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checked" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="变量名" width="120">
        <template #default="{ row }">
          <el-input v-model="row.name" size="small" />
        </template>
      </el-table-column>
      <el-table-column prop="path" label="JSONPath" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.path" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="示例值" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.sample }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="skipExtractorWizard">跳过</el-button>
      <el-button type="primary" :loading="extractorWizard.saving" @click="confirmExtractorWizard">
        写入提取项
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import { httpCaseApi } from '@/api/modules/http'
import { perfWorkerApi } from '@/api/modules/perf'
import { parseWorkerList, filterOnlineWorkers } from '@/views/Perf/perfWorkerUtils'
import EnvVarQuickEdit from '@/components/EnvVarQuickEdit.vue'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DataFactoryTagPicker from './DataFactoryTagPicker.vue'
import { insertVarRef } from '@/utils/varInsert.js'
import VariablePreviewPanel from '@/components/VariablePreviewPanel.vue'
import CopyTextButton from '@/components/CopyTextButton.vue'
import CopyablePre from '@/components/CopyablePre.vue'
import JsonTextarea from '@/components/JsonTextarea.vue'
import HeaderEditorPanel from '@/components/HeaderEditorPanel.vue'
import WsStepsEditor from './WsStepsEditor.vue'
import ApiTestFilePicker from '@/components/ApiTestFilePicker.vue'

const props = defineProps({
  modelValue: Boolean,
  api: Object
})

const emit = defineEmits(['update:modelValue'])

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
const activeTab = ref('params')
const responseTab = ref('body')
const loading = ref(false)
const response = ref(null)
const wsSteps = ref([])
const customBaseUrl = ref('')
const selectedEnvId = ref(null)
const viaWorker = ref(false)
const selectedWorkerId = ref(null)
const workersLoading = ref(false)
const workerList = ref([])
/** 经执行机调试最少引擎版本（与后端门禁一致） */
const MIN_API_DEBUG_ENGINE = '1.0.0'

function parseEngineParts(v) {
  return String(v || '0')
    .split(/[^\d]+/)
    .filter(Boolean)
    .map((n) => Number(n) || 0)
}

function engineAtLeast(version, minimum) {
  const a = parseEngineParts(version)
  const b = parseEngineParts(minimum)
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i += 1) {
    const x = a[i] || 0
    const y = b[i] || 0
    if (x > y) return true
    if (x < y) return false
  }
  return true
}

const idleWorkers = computed(() =>
  filterOnlineWorkers(workerList.value).filter(
    (w) => w.status !== 'busy' && engineAtLeast(w.engine_version, MIN_API_DEBUG_ENGINE)
  )
)
const varEditVisible = ref(false)
const tagPickerVisible = ref(false)
const saveCaseVisible = ref(false)
const saveCaseName = ref('')
const savingCase = ref(false)
const extractorWizard = reactive({
  visible: false,
  saving: false,
  caseId: null,
  suggestions: [],
  pendingRedirect: false
})

const fromPerfScene = computed(() => {
  const v = route.query.from_perf_scene
  return v != null && String(v).length > 0
})
const saveCaseButtonLabel = computed(() =>
  fromPerfScene.value ? '保存并返回压测场景' : '保存为用例'
)

const parseJsonBody = (body) => {
  if (body == null) return null
  if (typeof body === 'object') return body
  if (typeof body !== 'string') return null
  const text = body.trim()
  if (!text || (text[0] !== '{' && text[0] !== '[')) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

const formatSample = (val) => {
  if (val == null) return ''
  if (typeof val === 'object') {
    try {
      const s = JSON.stringify(val)
      return s.length > 80 ? `${s.slice(0, 80)}…` : s
    } catch {
      return String(val)
    }
  }
  const s = String(val)
  return s.length > 80 ? `${s.slice(0, 80)}…` : s
}

const getBySimplePath = (obj, dotted) => {
  const parts = dotted.split('.').filter(Boolean)
  let cur = obj
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = cur[p]
  }
  return cur
}

/** 浅层启发式建议 JSONPath 提取项 */
const suggestExtractorsFromResponse = (body) => {
  const data = parseJsonBody(body)
  if (!data || typeof data !== 'object' || Array.isArray(data)) return []

  const suggestions = []
  const seenPath = new Set()
  const push = (name, path, sample, checked = false) => {
    if (!name || !path || seenPath.has(path)) return
    seenPath.add(path)
    suggestions.push({ name, source: 'json', path, sample: formatSample(sample), checked })
  }

  const preferred = [
    ['token', 'data.token', true],
    ['access_token', 'data.access_token', true],
    ['token', 'token', true],
    ['access_token', 'access_token', true],
    ['id', 'data.id', true],
    ['id', 'id', false],
  ]
  for (const [name, dotted, checked] of preferred) {
    const val = getBySimplePath(data, dotted)
    if (val !== undefined && val !== null && typeof val !== 'object') {
      push(name, `$.${dotted}`, val, checked)
    }
  }

  for (const key of Object.keys(data).slice(0, 15)) {
    const val = data[key]
    if (val !== null && typeof val !== 'object') {
      push(key, `$.${key}`, val, false)
    }
  }

  const nested = data.data
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    for (const key of Object.keys(nested).slice(0, 10)) {
      const val = nested[key]
      if (val !== null && typeof val !== 'object') {
        push(key, `$.data.${key}`, val, false)
      }
    }
  }

  return suggestions
}

const redirectAfterSaveCase = (caseId) => {
  if (!fromPerfScene.value || !caseId) return
  const sceneRef = String(route.query.from_perf_scene)
  const phaseIndex = route.query.phase_index != null ? String(route.query.phase_index) : '0'
  if (sceneRef === 'new') {
    router.push({
      path: '/perf-scene/add',
      query: { append_case_id: String(caseId), phase_index: phaseIndex }
    })
  } else {
    router.push({
      path: `/perf-scene/edit/${sceneRef}`,
      query: { append_case_id: String(caseId), phase_index: phaseIndex }
    })
  }
}

const finishSaveAsCaseFlow = (caseId) => {
  extractorWizard.visible = false
  extractorWizard.caseId = null
  extractorWizard.suggestions = []
  extractorWizard.pendingRedirect = false
  emit('update:modelValue', false)
  redirectAfterSaveCase(caseId)
}

const skipExtractorWizard = () => {
  const caseId = extractorWizard.caseId
  finishSaveAsCaseFlow(caseId)
}

const onExtractorWizardClosed = () => {
  if (extractorWizard.pendingRedirect && extractorWizard.caseId) {
    const caseId = extractorWizard.caseId
    extractorWizard.pendingRedirect = false
    extractorWizard.caseId = null
    emit('update:modelValue', false)
    redirectAfterSaveCase(caseId)
  }
}

const buildCaseUpdatePayload = (detail, extractors) => ({
  name: detail.name,
  catalog_id: detail.catalog_id ?? null,
  priority: detail.priority || 'P2',
  timeout: detail.timeout ?? 30,
  retry_count: detail.retry_count ?? 0,
  tags: Array.isArray(detail.tags) ? detail.tags : [],
  request_headers: detail.request_headers || {},
  request_params: detail.request_params || [],
  request_body: detail.request_body ?? {},
  request_body_type: detail.request_body_type || 'json',
  request_body_fields: detail.request_body_fields || [],
  ws_steps: detail.ws_steps || [],
  assertions: detail.assertions || [],
  assertion_groups: detail.assertion_groups || [],
  extractors,
  depends_on: detail.depends_on || null,
  pre_script: detail.pre_script || null,
  post_script: detail.post_script || null,
  data_set: detail.data_set || [],
  db_assertions: detail.db_assertions || [],
  global_header_policy: detail.global_header_policy || {}
})

const confirmExtractorWizard = async () => {
  const selected = extractorWizard.suggestions
    .filter(s => s.checked && (s.name || '').trim() && (s.path || '').trim())
    .map(s => ({
      name: String(s.name).trim(),
      source: 'json',
      path: String(s.path).trim(),
      description: ''
    }))
  if (!selected.length) {
    ElMessage.warning('请至少勾选一项提取变量，或点击跳过')
    return
  }
  const caseId = extractorWizard.caseId
  if (!caseId) return
  extractorWizard.saving = true
  try {
    const detailRes = await httpCaseApi.getDetail(caseId)
    const detail = detailRes.data?.data ?? detailRes.data ?? detailRes
    await httpCaseApi.update(caseId, buildCaseUpdatePayload(detail, selected))
    ElMessage.success(`已写入 ${selected.length} 个提取项`)
    extractorWizard.pendingRedirect = false
    finishSaveAsCaseFlow(caseId)
  } catch (err) {
    console.error(err)
    ElMessage.error(extractApiErrorMessage(err) || '写入提取项失败')
  } finally {
    extractorWizard.saving = false
  }
}

const openSaveAsCase = () => {
  if (!props.api?.id) {
    ElMessage.warning('缺少接口信息，无法保存用例')
    return
  }
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先选择项目')
    return
  }
  saveCaseName.value = `${props.api.name || '接口'}-调试`
  saveCaseVisible.value = true
}

const submitSaveAsCase = async () => {
  const name = (saveCaseName.value || '').trim()
  if (!name) {
    ElMessage.warning('请填写用例名称')
    return
  }
  if (!props.api?.id) {
    ElMessage.warning('缺少接口信息')
    return
  }
  savingCase.value = true
  try {
    const payload = {
      name,
      api_id: props.api.id,
      project_id: proStore.projectInfo.id,
      catalog_id: props.api.catalog_id ?? null,
      request_headers: headersToCaseDict(request.headers),
      request_params: (request.params || [])
        .filter(p => p?.name)
        .map(p => ({
          name: p.name,
          value: p.value ?? '',
          type: p.type || 'string',
          required: !!p.required
        })),
      request_body: parseBodyForCase(),
      request_body_type: request.body_type || 'json',
      request_body_fields: mapBodyFields(request.body_fields),
      ws_steps: isWsApi.value ? (wsSteps.value || []).map(s => ({ ...s })) : []
    }
    const res = await httpCaseApi.create(payload)
    const data = res.data?.data ?? res.data ?? res
    const caseId = data?.id
    ElMessage.success(caseId ? `用例已保存 #${caseId}` : '用例已保存')
    saveCaseVisible.value = false

    const suggestions = suggestExtractorsFromResponse(response.value?.body)
    if (caseId && suggestions.length) {
      extractorWizard.caseId = caseId
      extractorWizard.suggestions = suggestions
      extractorWizard.pendingRedirect = !!fromPerfScene.value
      extractorWizard.visible = true
      return
    }
    emit('update:modelValue', false)
    redirectAfterSaveCase(caseId)
  } catch (err) {
    console.error(err)
    ElMessage.error(extractApiErrorMessage(err) || '保存用例失败')
  } finally {
    savingCase.value = false
  }
}

async function onDfTagInsert(refStr) {
  const m = String(refStr).match(/^\$\{\{(.+)\}\}$/)
  const name = m ? m[1] : refStr
  const result = await insertVarRef(name)
  if (result?.ok) {
    ElMessage.success(result.mode === 'copy' ? `已复制 ${refStr}，请粘贴` : `已插入 ${refStr}`)
  } else {
    ElMessage.warning('请先将光标放入请求参数输入框')
  }
}

// 当前选中的环境
const selectedEnv = computed(() => {
  if (!selectedEnvId.value) return null
  return proStore.envList.find(e => e.id === selectedEnvId.value)
})

const previewSamples = computed(() => {
  const samples = []
  if (request.url) samples.push(String(request.url))
  wsSteps.value.forEach(s => { if (s.message) samples.push(String(s.message)) })
  return samples
})

const isWsApi = computed(() => (request.protocol || props.api?.protocol) === 'websocket')

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

  const isAbsolute = /^(https?|wss?):\/\//i.test(fullUrl)
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
  protocol: 'http',
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
  request.protocol = val.protocol || 'http'
  request.method = val.method || 'GET'
  request.url = val.path || ''
  request.base_url = val.base_url || ''
  request.headers = val.headers || []
  request.params = val.params || []
  request.body = val.body ?? null
  request.body_fields = mapBodyFields(val.body_fields)
  request.body_type = val.body_type || 'json'
  wsSteps.value = (val.ws_config?.steps || []).map(s => ({ ...s }))
  syncBodyText()
  if (request.body_type === 'form-data') {
    activeTab.value = 'body'
  } else if (request.protocol === 'websocket') {
    activeTab.value = 'ws-steps'
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
  if (visible) {
    loadWorkers()
  }
})

const loadWorkers = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    workerList.value = []
    return
  }
  workersLoading.value = true
  try {
    const res = await perfWorkerApi.getList({ project_id: pid })
    workerList.value = parseWorkerList(res)
    if (
      selectedWorkerId.value &&
      !idleWorkers.value.some((w) => w.id === selectedWorkerId.value)
    ) {
      selectedWorkerId.value = null
    }
  } catch (e) {
    console.error(e)
    workerList.value = []
  } finally {
    workersLoading.value = false
  }
}

const onViaWorkerChange = (checked) => {
  if (checked) {
    loadWorkers()
    if (!selectedWorkerId.value && idleWorkers.value.length === 1) {
      selectedWorkerId.value = idleWorkers.value[0].id
    }
  }
}

// 弹窗关闭后重置
const handleClosed = () => {
  selectedEnvId.value = null
  response.value = null
  customBaseUrl.value = ''
  request.base_url = ''
  request.body_fields = []
  bodyText.value = ''
  viaWorker.value = false
  selectedWorkerId.value = null
}

const headersToCaseDict = (headers) => {
  if (!Array.isArray(headers)) return headers && typeof headers === 'object' ? { ...headers } : {}
  const out = {}
  for (const h of headers) {
    const key = h?.key || h?.name
    if (key) out[key] = h.value ?? ''
  }
  return out
}

const parseBodyForCase = () => {
  if (isWsApi.value) return {}
  if (['form-data', 'binary'].includes(request.body_type)) return {}
  if (request.body_type === 'json') {
    const text = (bodyText.value || '').trim()
    if (!text) return {}
    try {
      return JSON.parse(text)
    } catch {
      return { raw: text }
    }
  }
  return bodyText.value || ''
}

const addParam = () => {
  request.params.push({ name: '', value: '' })
}

const removeParam = (index) => {
  request.params.splice(index, 1)
}

const onFormFieldFileUpdate = (index, patch) => {
  Object.assign(request.body_fields[index], patch)
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

  if (viaWorker.value) {
    if (!selectedWorkerId.value) {
      ElMessage.warning('请选择在线空闲执行机，或取消「经执行机发送」')
      return
    }
    if (!idleWorkers.value.some((w) => w.id === selectedWorkerId.value)) {
      ElMessage.warning('所选执行机已不可用，请刷新后重选')
      return
    }
    if (
      request.body_type === 'form-data' &&
      request.body_fields.some((f) => f.field_type === 'file')
    ) {
      ElMessage.warning('经执行机发送暂不支持带文件的 form-data，请去掉文件字段或取消勾选')
      return
    }
  }

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

    const payload = {
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
    }
    if (viaWorker.value && selectedWorkerId.value) {
      payload.worker_id = selectedWorkerId.value
    }

    const res = await http.apiModuleApi.debugApi(payload)

    if (res.status === 200) {
      response.value = res.data
      responseTab.value = 'body'
      if (res.data?.via_worker) {
        ElMessage.success(`已由执行机 #${res.data.worker_id} 代发`)
      }
    }
  } catch (error) {
    ElMessage.error(extractApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

const sendWsRequest = async () => {
  if (!request.url) {
    ElMessage.warning('请输入 WebSocket URL 或路径')
    return
  }

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
    const res = await http.apiModuleApi.debugWs({
      url: fullUrl,
      headers: request.headers,
      steps: wsSteps.value,
      timeout: 30,
      env_id: selectedEnvId.value || undefined,
      project_id: proStore.projectInfo?.id || undefined,
    })
    if (res.status === 200) {
      const data = res.data
      response.value = {
        status_code: data.success ? 101 : 0,
        headers: {},
        body: data.messages,
        time: data.elapsed_ms || 0,
        size: JSON.stringify(data.messages || []).length,
        ws_error: data.error,
        ws_assertions: data.assertions || [],
        response_body: data.response_body,
      }
      responseTab.value = 'body'
      if (data.error) {
        ElMessage.error(data.error)
      } else if (!data.success) {
        ElMessage.warning('WebSocket 执行完成，但断言未全部通过')
      }
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

.worker-selector {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  padding: 8px 15px;
  background: var(--el-fill-color-blank);
  border: 1px dashed var(--el-border-color);
  border-radius: 4px;
  font-size: 13px;
}

.worker-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 4px;
  border-radius: 50%;
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  cursor: help;
}

.worker-warn {
  color: var(--el-color-warning);
  font-size: 12px;
  margin-left: 4px;
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
