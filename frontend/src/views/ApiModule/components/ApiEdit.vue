<template>
  <div class="api-edit-wrapper">
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    :title="isEdit ? '编辑接口' : '新建接口'"
    width="800px"
    destroy-on-close
    @closed="handleClosed"
  >
    <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="接口名称" prop="name">
            <el-input v-model="form.name" placeholder="请输入接口名称"/>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="所属目录">
            <el-tree-select
              v-model="form.catalog_id"
              :data="catalogTree"
              :props="{ label: 'name', value: 'id', children: 'children' }"
              clearable
              placeholder="请选择目录"
            />
          </el-form-item>
        </el-col>
      </el-row>
      
      <el-row :gutter="20">
        <el-col :span="8">
          <el-form-item label="协议类型">
            <el-select v-model="form.protocol" placeholder="请选择协议" style="width: 100%;">
              <el-option label="HTTP" value="http" />
              <el-option label="WebSocket" value="websocket" />
              <el-option label="GraphQL" value="graphql" />
              <el-option label="gRPC" value="grpc" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6" v-if="form.protocol === 'http'">
          <el-form-item label="请求方法" prop="method">
            <el-select v-model="form.method" placeholder="Method">
              <el-option label="GET" value="GET"/>
              <el-option label="POST" value="POST"/>
              <el-option label="PUT" value="PUT"/>
              <el-option label="DELETE" value="DELETE"/>
              <el-option label="PATCH" value="PATCH"/>
              <el-option label="HEAD" value="HEAD"/>
              <el-option label="OPTIONS" value="OPTIONS"/>
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="form.protocol === 'websocket' || form.protocol === 'graphql' || form.protocol === 'grpc' ? 16 : 10">
          <el-form-item label="接口路径" prop="path">
            <el-input v-model="form.path" :placeholder="pathPlaceholder"/>
          </el-form-item>
        </el-col>
      </el-row>
      
      <el-form-item label="基础URL">
        <el-input v-model="form.base_url" placeholder="留空则执行/测试时使用所选环境的 Base_url" clearable />
        <div class="field-hint">留空时按「参考环境」或测试弹窗所选环境的 Base_url 拼接路径；填写则优先使用接口级地址</div>
      </el-form-item>
      
      <el-form-item label="接口描述">
        <el-input v-model="form.description" type="textarea" rows="2" placeholder="接口功能描述"/>
      </el-form-item>

      <div class="var-toolbar">
        <div class="var-toolbar-actions">
          <el-select
            v-model="refEnvId"
            placeholder="参考环境"
            clearable
            size="small"
            style="width: 160px"
          >
            <el-option
              v-for="env in proStore.envList"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
          <VarInsertButton
            :env-id="refEnvId"
            :show-env-edit="false"
            hint-text="含项目/环境/Token 授权/内置/用例变量；授权变量在调试与执行时自动注入。工厂标签与工具请用旁侧按钮。"
          />
          <ToolInsertButton :env-id="refEnvId" />
          <el-button type="info" link size="small" @click="tagPickerVisible = true">数据工厂标签</el-button>
        </div>
        <span class="var-toolbar-hint">先点击下方输入框再插入；参考环境仅预览变量列表，<strong>执行</strong>时以运行环境为准</span>
      </div>
      
      <!-- 请求参数 -->
      <div class="section-title">
        <span>查询参数 (Params)</span>
        <el-button type="primary" link size="small" @click="addParam" icon="Plus">添加</el-button>
      </div>
      <el-table :data="form.params" size="small" border class="param-table">
        <el-table-column label="参数名" width="150">
          <template #default="{ $index }">
            <el-input v-model="form.params[$index].name" size="small" placeholder="name"/>
          </template>
        </el-table-column>
        <el-table-column label="参数值" width="150">
          <template #default="{ $index }">
            <el-input v-model="form.params[$index].value" size="small" placeholder="value"/>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ $index }">
            <el-select v-model="form.params[$index].type" size="small">
              <el-option label="string" value="string"/>
              <el-option label="integer" value="integer"/>
              <el-option label="boolean" value="boolean"/>
              <el-option label="array" value="array"/>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="必填" width="80">
          <template #default="{ $index }">
            <el-checkbox v-model="form.params[$index].required"/>
          </template>
        </el-table-column>
        <el-table-column label="描述">
          <template #default="{ $index }">
            <el-input v-model="form.params[$index].description" size="small" placeholder="参数描述"/>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeParam($index)" icon="Delete"/>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 请求头 -->
      <HeaderEditorPanel
        v-model="form.headers"
        local-title="本接口 Header"
      />

      <template v-if="form.protocol === 'websocket'">
        <div class="section-title"><span>默认 WS 步骤（用例可覆盖）</span></div>
        <WsStepsEditor v-model="form.ws_config.steps" />
      </template>

      <template v-if="form.protocol === 'graphql'">
        <div class="section-title"><span>GraphQL 请求体（query / variables）</span></div>
        <JsonTextarea
          v-model="bodyText"
          :rows="10"
          placeholder='{"query":"query { ... }","variables":{}}'
          json-mode
          show-compact
        />
        <div class="field-hint">执行时以 POST JSON 发送到 GraphQL 端点；用例 request_body 可覆盖。</div>
      </template>

      <template v-if="form.protocol === 'grpc'">
        <div class="section-title"><span>gRPC 配置</span></div>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="full_method">
              <el-input v-model="form.grpc_config.full_method" placeholder="/helloworld.Greeter/SayHello" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="TLS">
              <el-switch v-model="form.grpc_config.use_tls" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="service">
              <el-input v-model="form.grpc_config.service" placeholder="helloworld.Greeter（可选）" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="method">
              <el-input v-model="form.grpc_config.method" placeholder="SayHello（可选）" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="section-title"><span>默认请求 JSON（用例可覆盖）</span></div>
        <JsonTextarea
          v-model="bodyText"
          :rows="8"
          placeholder='{"name":"world"}'
          json-mode
          show-compact
        />
        <div class="field-hint">需目标 gRPC 服务开启 Server Reflection；基础 URL 填 host:port。</div>
      </template>
      
      <!-- 请求体 -->
      <template v-if="form.protocol === 'http' && ['POST', 'PUT', 'PATCH'].includes(form.method)">
        <div class="section-title">
          <span>请求体 (Body)</span>
          <el-radio-group v-model="form.body_type" size="small">
            <el-radio-button label="json">JSON</el-radio-button>
            <el-radio-button label="form-data">Form Data</el-radio-button>
            <el-radio-button label="x-www-form-urlencoded">x-www-form-urlencoded</el-radio-button>
            <el-radio-button label="xml">XML</el-radio-button>
            <el-radio-button label="raw">Raw</el-radio-button>
          </el-radio-group>
        </div>
        <el-form-item v-if="form.body_type !== 'form-data'">
          <JsonTextarea
            v-model="bodyText"
            :rows="8"
            :placeholder="bodyPlaceholder"
            :json-mode="form.body_type === 'json'"
            show-compact
          />
        </el-form-item>
        <div v-else class="form-data-editor">
          <div class="section-title compact">
            <span>Form Data 字段</span>
            <el-button type="primary" link size="small" @click="addFormField">添加</el-button>
          </div>
          <el-table :data="form.body_fields" size="small" border>
            <el-table-column label="字段名" width="180">
              <template #default="{ $index }">
                <el-input v-model="form.body_fields[$index].name" size="small" placeholder="file" />
              </template>
            </el-table-column>
            <el-table-column label="类型" width="120">
              <template #default="{ $index }">
                <el-select v-model="form.body_fields[$index].field_type" size="small">
                  <el-option label="文本" value="text" />
                  <el-option label="文件" value="file" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="值 / 文件" min-width="260">
              <template #default="{ $index }">
                <div class="file-field-cell">
                  <ApiTestFilePicker
                    v-if="form.body_fields[$index].field_type === 'file'"
                    :model-value="form.body_fields[$index]"
                    @update:model-value="(v) => onFormFieldFileUpdate($index, v)"
                  />
                  <el-input v-else v-model="form.body_fields[$index].value" size="small" placeholder="文本值" />
                </div>
              </template>
            </el-table-column>
            <el-table-column label="MIME" width="180">
              <template #default="{ $index }">
                <el-input v-model="form.body_fields[$index].mime_type" size="small" placeholder="application/octet-stream" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeFormField($index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

      </template>

      <!-- 响应结构 -->
      <el-collapse v-model="responseCollapse" class="response-collapse">
        <el-collapse-item title="响应结构定义（可选，用于 AI 生成精准断言）" name="response">
          <el-form-item class="response-field-item" label-width="110px">
            <template #label>
              <span class="response-field-label">响应 Schema</span>
              <el-tooltip content="OpenAPI 格式的响应结构定义，用于描述返回字段的类型、是否必填等元数据。AI 会基于此生成字段类型校验断言。" placement="top">
                <el-icon class="label-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <div class="response-field-toolbar">
              <el-button type="primary" link size="small" @click="showSchemaGenDialog" icon="MagicStick">一键生成</el-button>
            </div>
            <JsonTextarea
              v-model="responseSchemaText"
              :rows="5"
              placeholder='{"type": "object", "properties": {"code": {"type": "integer"}, "data": {"type": "object", "properties": {"list": {"type": "array"}}}}}'
            />
            <div class="field-hint">填写 OpenAPI 格式的 schema 定义（如字段类型、必填性）。通常从 Swagger/Apifox 导入时自动填充</div>
          </el-form-item>
          <el-form-item class="response-field-item" label-width="110px">
            <template #label>
              <span class="response-field-label">响应示例</span>
              <el-tooltip content="支持标准 JSON，或 SSE 等多行文本（如 event:message + data:{...}）。AI 会参考此示例生成断言。可通过【测试接口】一键保存。" placement="top">
                <el-icon class="label-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <JsonTextarea
              v-model="responseExampleText"
              :rows="4"
              :placeholder="responseExamplePlaceholder"
            />
            <div class="field-hint">支持 JSON 或 SSE（event:/data:）等原始响应文本；非 JSON 将原样保存。Schema 一键生成会尝试从 data: 行解析 JSON</div>
          </el-form-item>
        </el-collapse-item>
      </el-collapse>
    </el-form>
    
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="warning" @click="showTestDialog" :loading="testing">测试</el-button>
      <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
  
  <!-- 测试环境选择弹窗 -->
  <el-dialog v-model="testDialogVisible" title="测试接口" width="560px" append-to-body destroy-on-close>
    <el-form :model="testForm" label-width="100px">
      <el-form-item label="执行环境">
        <el-select v-model="testForm.env_id" placeholder="选择环境（基础URL 为空时必填）" clearable style="width: 100%">
          <el-option
            v-for="env in proStore.envList"
            :key="env.id"
            :label="env.name"
            :value="env.id"
          />
        </el-select>
        <div v-if="selectedEnv?.host" class="env-host">{{ selectedEnv.host }}</div>
      </el-form-item>
      <el-form-item v-if="form.protocol !== 'websocket' && form.protocol !== 'grpc'" label="执行机">
        <ViaWorkerSelect v-model="testForm.worker_id" :env-id="testForm.env_id" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="testDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleTest" :loading="testing">开始测试</el-button>
    </template>
  </el-dialog>
  
  <!-- 生成 Schema 弹窗 -->
  <el-dialog v-model="schemaGenVisible" title="根据响应示例生成 JSON Schema" width="600px" append-to-body destroy-on-close>
    <el-form label-width="0">
      <el-form-item>
        <div style="margin-bottom: 8px; color: var(--el-text-color-secondary); font-size: 13px;">
          粘贴 JSON 响应示例，系统会自动推断每个字段的类型并生成 Schema。
          <span v-if="form.response_schema?.example" style="color: var(--el-color-primary); cursor: pointer;" @click="useExistingExample">（或点击使用已填写的响应示例）</span>
        </div>
        <JsonTextarea
          v-model="schemaGenForm.input"
          :rows="12"
          placeholder='{"code": 0, "data": {"list": [{"id": 1, "name": "xxx"}]}, "message": "success"}'
        />
        <div style="text-align: right; color: #999; font-size: 12px; margin-top: 4px;">
          已输入 {{ schemaGenForm.input.length }} 字符
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="schemaGenVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmGenerateSchema">生成</el-button>
    </template>
  </el-dialog>
  
  <!-- 测试结果弹窗 -->
  <el-dialog v-model="testResultVisible" title="测试结果" width="800px" append-to-body class="test-result-dialog" destroy-on-close>
    <div v-if="testResult" class="test-result">
      <div class="result-header">
        <el-tag :type="getStatusType(testResult.status_code)" size="large">
          {{ testResult.status_code }}
        </el-tag>
        <span v-if="testResult.time" class="response-time">{{ testResult.time.toFixed(2) }} ms</span>
      </div>
      
      <el-tabs v-model="testActiveTab">
        <!-- 请求详情 -->
        <el-tab-pane label="请求详情" name="request">
          <div v-if="testResult.request_detail" class="detail-section">
            <div class="detail-block">
              <div class="detail-title">请求 URL</div>
              <div class="detail-content">
                <div class="compare-row">
                  <span class="label">原始:</span>
                  <code class="original">{{ testResult.request_detail.url.original }}</code>
                </div>
                <div class="compare-row">
                  <span class="label">最终:</span>
                  <code class="final">{{ testResult.request_detail.url.final }}</code>
                </div>
              </div>
            </div>
            <div class="detail-block" v-if="Object.keys(testResult.request_detail.headers.final).length > 0">
              <div class="detail-title">Headers</div>
              <div class="detail-content">
                <pre>{{ JSON.stringify(testResult.request_detail.headers.final, null, 2) }}</pre>
              </div>
            </div>
          </div>
        </el-tab-pane>
        
        <!-- 变量替换 -->
        <el-tab-pane label="变量替换" name="variables">
          <div v-if="testResult.request_detail" class="detail-section">
            <div class="detail-block" v-if="Object.keys(testResult.request_detail.variables_used || {}).length > 0">
              <div class="detail-title">环境变量</div>
              <div class="detail-content">
                <el-descriptions border size="small" :column="2">
                  <el-descriptions-item 
                    v-for="(value, key) in testResult.request_detail.variables_used" 
                    :key="key"
                    :label="key"
                  >{{ value }}</el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
            <div class="detail-block">
              <div class="detail-title">替换详情</div>
              <div class="detail-content">
                <el-empty v-if="!testResult.request_detail.replacements?.length" description="没有变量替换"/>
                <el-table v-else :data="testResult.request_detail.replacements" size="small" border>
                  <el-table-column label="变量名" prop="key" width="120"/>
                  <el-table-column label="原始值" prop="original" width="150">
                    <template #default="{ row }">
                      <code class="original">{{ row.original }}</code>
                    </template>
                  </el-table-column>
                  <el-table-column label="替换后" prop="replaced" width="150">
                    <template #default="{ row }">
                      <code class="final">{{ row.replaced }}</code>
                    </template>
                  </el-table-column>
                  <el-table-column label="位置" prop="path" width="100"/>
                </el-table>
              </div>
            </div>
          </div>
        </el-tab-pane>
        
        <!-- 响应详情 -->
        <el-tab-pane label="响应详情" name="response">
          <div v-if="testResult.response_detail" class="detail-section">
            <div class="detail-block">
              <div class="detail-title">响应信息</div>
              <el-descriptions border size="small">
                <el-descriptions-item label="状态码">{{ testResult.response_detail.status_code ?? '-' }}</el-descriptions-item>
                <el-descriptions-item label="接口耗时">
                  {{ testResult.response_detail.http_time != null ? `${Number(testResult.response_detail.http_time).toFixed(2)} ms` : '-' }}
                </el-descriptions-item>
              </el-descriptions>
            </div>
            <div
              class="detail-block"
              v-if="testResult.response_detail.headers && Object.keys(testResult.response_detail.headers || {}).length"
            >
              <div class="detail-title">响应 Headers</div>
              <div class="detail-content">
                <pre>{{ typeof testResult.response_detail.headers === 'object' ? JSON.stringify(testResult.response_detail.headers, null, 2) : testResult.response_detail.headers }}</pre>
              </div>
            </div>
            <div class="detail-block">
              <div class="detail-title" style="display: flex; justify-content: space-between; align-items: center;">
                <span>响应 Body</span>
                <el-button type="primary" size="small" @click="saveResponseAsExample" icon="DocumentChecked">保存为响应示例</el-button>
              </div>
              <div class="detail-content">
                <pre>{{ typeof testResult.response_detail.body === 'object' ? JSON.stringify(testResult.response_detail.body, null, 2) : testResult.response_detail.body }}</pre>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
    <template #footer>
      <el-button @click="testResultVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <DataFactoryTagPicker
    v-model="tagPickerVisible"
    :project-id="proStore.projectInfo?.id"
    @insert="onDfTagInsert"
  />
</div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'

import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DataFactoryTagPicker from './DataFactoryTagPicker.vue'
import { insertVarRef } from '@/utils/varInsert.js'
import JsonTextarea from '@/components/JsonTextarea.vue'
import HeaderEditorPanel from '@/components/HeaderEditorPanel.vue'
import ViaWorkerSelect from '@/components/ViaWorkerSelect.vue'
import WsStepsEditor from './WsStepsEditor.vue'
import ApiTestFilePicker from '@/components/ApiTestFilePicker.vue'
import {
  formatResponseExample,
  parseResponseExampleInput,
  parseResponseExampleAsJson
} from '@/utils/responseExample'

const responseExamplePlaceholder =
  'JSON：{"code":0,"data":{"list":[]},"message":"success"}\n或 SSE：\nevent:message\ndata:{"content":"..."}'

const props = defineProps({
  modelValue: Boolean,
  data: Object
})

const emit = defineEmits(['update:modelValue', 'success'])

const proStore = ProjectStore()
const formRef = ref()
const refEnvId = ref(null)
const tagPickerVisible = ref(false)

async function onDfTagInsert(refStr) {
  const m = String(refStr).match(/^\$\{\{(.+)\}\}$/)
  const name = m ? m[1] : refStr
  const result = await insertVarRef(name)
  if (result?.ok) {
    ElMessage.success(result.mode === 'copy' ? `已复制 ${refStr}，请粘贴到输入框` : `已插入 ${refStr}`)
  } else {
    ElMessage.warning('请先将光标放入 Params / Headers / Body 输入框')
  }
}

const saving = ref(false)
const testing = ref(false)

// 测试相关
const testDialogVisible = ref(false)
const testResultVisible = ref(false)
const testActiveTab = ref('request')
const testForm = reactive({ env_id: null, worker_id: null })
const testResult = ref(null)

// 响应结构折叠面板
const responseCollapse = ref([])

// Schema 生成弹窗
const schemaGenVisible = ref(false)
const schemaGenForm = reactive({ input: '' })

const showSchemaGenDialog = () => {
  const example = form.response_schema?.example
  schemaGenForm.input = (example != null && example !== '')
    ? formatResponseExample(example)
    : ''
  schemaGenVisible.value = true
}

const useExistingExample = () => {
  const example = form.response_schema?.example
  if (example != null && example !== '') {
    schemaGenForm.input = formatResponseExample(example)
  } else {
    ElMessage.warning('尚未填写响应示例')
  }
}

// 递归推断 JSON 值的 Schema 类型
const inferSchema = (value) => {
  if (value === null) {
    return { type: 'null' }
  }
  const t = typeof value
  if (t === 'string') {
    // 尝试识别日期格式
    if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
      return { type: 'string', format: 'date-time' }
    }
    return { type: 'string' }
  }
  if (t === 'number') {
    return Number.isInteger(value) ? { type: 'integer' } : { type: 'number' }
  }
  if (t === 'boolean') {
    return { type: 'boolean' }
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return { type: 'array', items: {} }
    }
    // 取第一个非 null 元素推断 items 类型（不做严格一致性检查，实际场景中元素通常结构相似）
    const firstNonNull = value.find(item => item !== null && item !== undefined)
    if (!firstNonNull) {
      return { type: 'array', items: { type: 'null' } }
    }
    return {
      type: 'array',
      items: inferSchema(firstNonNull)
    }
  }
  if (t === 'object') {
    const properties = {}
    const required = []
    for (const [key, val] of Object.entries(value)) {
      properties[key] = inferSchema(val)
      if (val !== null && val !== undefined) {
        required.push(key)
      }
    }
    return {
      type: 'object',
      properties,
      required
    }
  }
  return {}
}

const confirmGenerateSchema = () => {
  const text = schemaGenForm.input.trim()
  if (!text) {
    ElMessage.warning('请输入响应示例')
    return
  }
  const parsed = parseResponseExampleAsJson(text)
  if (parsed == null) {
    ElMessage.error('无法解析为 JSON：请填写标准 JSON，或 SSE 中 data: 行内为 JSON 对象')
    return
  }
  const schema = inferSchema(parsed)
  if (!form.response_schema) {
    form.response_schema = {}
  }
  form.response_schema.schema = schema
  ElMessage.success('Schema 生成成功')
  schemaGenVisible.value = false
}

// 响应 Schema 文本（只读写 form.response_schema.schema）
const responseSchemaText = computed({
  get() {
    const schema = form.response_schema?.schema
    if (!schema) return ''
    try {
      return JSON.stringify(schema, null, 2)
    } catch {
      return String(schema)
    }
  },
  set(val) {
    try {
      const parsed = val ? JSON.parse(val) : null
      if (!form.response_schema) form.response_schema = {}
      form.response_schema.schema = parsed
    } catch {
      // 解析失败时保留原值
    }
  }
})

// 响应示例文本（JSON 对象或 SSE 等原始字符串）
const responseExampleText = computed({
  get() {
    return formatResponseExample(form.response_schema?.example)
  },
  set(val) {
    if (!form.response_schema) form.response_schema = {}
    form.response_schema.example = parseResponseExampleInput(val)
  }
})

const selectedEnv = computed(() => {
  if (!testForm.env_id) return null
  return proStore.envList.find(e => e.id === testForm.env_id)
})

const getStatusType = (code) => {
  if (code >= 200 && code < 300) return 'success'
  if (code >= 300 && code < 400) return 'warning'
  return 'danger'
}

const showTestDialog = () => {
  testForm.env_id = refEnvId.value || null
  testForm.worker_id = null
  testDialogVisible.value = true
}

function resolveEnvHost(envId) {
  if (!envId) return ''
  const env = proStore.envList.find((e) => e.id === envId)
  return (env?.host || '').trim()
}

function buildRequestUrl({ baseUrl, path, envId }) {
  const pathStr = (path || '').trim()
  if (pathStr.startsWith('http://') || pathStr.startsWith('https://')) {
    return pathStr
  }

  let base = (baseUrl || '').trim()
  if (!base) {
    base = resolveEnvHost(envId)
  }
  if (!base) {
    return pathStr.startsWith('/') ? pathStr : `/${pathStr}`
  }

  const hasVariable = /\$\{\{[^}]+\}\}|\$\{[^}]+\}/.test(base)
  if (!base.startsWith('http') && !hasVariable) {
    base = `http://${base}`
  }
  const normalizedBase = base.replace(/\/$/, '')
  const normalizedPath = pathStr.startsWith('/') ? pathStr : `/${pathStr}`
  return normalizedBase + normalizedPath
}

function formatApiError(error) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join('；')
  }
  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail)
  }
  return error.message || '未知错误'
}

// 弹窗关闭后清理测试相关状态
const handleClosed = () => {
  testResult.value = null
  testResultVisible.value = false
  testDialogVisible.value = false
}

const catalogTree = ref([])

const loadCatalogTree = async () => {
  if (!proStore.projectInfo?.id) return
  try {
    const res = await catalogApi.getList({ project_id: proStore.projectInfo.id, tree: true })
    if (res.status === 200) {
      const data = res.data
      catalogTree.value = Array.isArray(data) && data.some(item => item.children?.length)
        ? data
        : buildCatalogTree(data || [])
    }
  } catch (error) {
    catalogTree.value = []
  }
}

const isEdit = computed(() => !!props.data)

const form = reactive({
  name: '',
  catalog_id: null,
  protocol: 'http',
  method: 'GET',
  path: '',
  base_url: '',
  description: '',
  headers: [],
  params: [],
  body: {},
  body_type: 'json',
  body_fields: [],
  ws_config: { steps: [] },
  grpc_config: { full_method: '', service: '', method: '', use_tls: false },
  response_schema: {}
})

const pathPlaceholder = computed(() => {
  switch (form.protocol) {
    case 'websocket':
      return '/ws/echo 或 ws://host/ws'
    case 'graphql':
      return '/graphql 或完整 HTTP 地址'
    case 'grpc':
      return '留空或 /（基础 URL 填 host:port）'
    default:
      return '/api/v1/users'
  }
})

watch(() => form.protocol, (p) => {
  if (p === 'websocket') form.method = 'WS'
  else if (p === 'graphql') form.method = 'POST'
  else if (p === 'grpc') form.method = 'RPC'
  else if (form.method === 'WS' || form.method === 'RPC') form.method = 'GET'
})

const bodyText = ref('')

const isStructuredBodyType = (type) => ['json'].includes(type)

const syncBodyText = () => {
  if (form.body == null || form.body === '') {
    bodyText.value = ''
    return
  }
  // 空对象在所有类型下都显示空字符串，避免 [object Object]
  if (typeof form.body === 'object' && !Array.isArray(form.body) && Object.keys(form.body).length === 0) {
    bodyText.value = ''
    return
  }
  if (typeof form.body === 'string') {
    bodyText.value = form.body
    return
  }
  if (isStructuredBodyType(form.body_type)) {
    try {
      bodyText.value = JSON.stringify(form.body, null, 2)
    } catch {
      bodyText.value = String(form.body)
    }
    return
  }
  bodyText.value = String(form.body)
}

const bodyPlaceholder = computed(() => {
  switch (form.body_type) {
    case 'form-data':
      return '请通过“选择并上传文件”添加文件字段'
    case 'x-www-form-urlencoded':
      return '示例：name=张三&age=18'
    case 'xml':
      return '<xml>...</xml>'
    case 'raw':
      return '任意文本内容'
    default:
      return '{"key": "value"}'
  }
})

const rules = {
  name: [{ required: true, message: '请输入接口名称', trigger: 'blur' }],
  method: [{ required: true, message: '请选择请求方法', trigger: 'change' }],
  path: [{ required: true, message: '请输入接口路径', trigger: 'blur' }]
}

// 重置表单 - 必须在 watch 之前定义
const resetForm = () => {
  form.name = ''
  form.catalog_id = null
  form.protocol = 'http'
  form.method = 'GET'
  form.path = ''
  form.base_url = ''
  form.description = ''
  form.headers = []
  form.params = []
  form.body = {}
  form.body_type = 'json'
  form.body_fields = [{ name: '', value: '', field_type: 'text', file_name: '', mime_type: 'application/octet-stream', file_key: '', file_bucket: '', description: '' }]
  form.ws_config = { steps: [] }
  form.grpc_config = { full_method: '', service: '', method: '', use_tls: false }
  form.response_schema = {}
  bodyText.value = ''
}

// 获取接口详情（编辑模式，用于补全列表页缺失的 body_fields 等字段）
const fetchApiDetail = async (apiId) => {
  try {
    const res = await http.apiModuleApi.getApiDetail(apiId)
    if (res.status === 200 && res.data) {
      const val = res.data
      form.name = val.name
      form.catalog_id = val.catalog_id ?? val.category_id ?? null
      form.protocol = val.protocol || 'http'
      form.method = val.method
      form.path = val.path
      form.base_url = val.base_url || ''
      form.description = val.description || ''
      form.headers = val.headers || []
      form.params = val.params || []
      form.body = val.body ?? {}
      form.body_type = val.body_type || 'json'
      form.body_fields = Array.isArray(val.body_fields) ? val.body_fields.map(f => ({
        name: f.name || '',
        value: f.value || '',
        field_type: f.field_type || 'text',
        file_name: f.file_name || '',
        mime_type: f.mime_type || 'application/octet-stream',
        file_key: f.file_key || '',
        file_bucket: f.file_bucket || '',
        description: f.description || ''
      })) : []
      form.ws_config = val.ws_config && Array.isArray(val.ws_config.steps)
        ? { steps: val.ws_config.steps.map(s => ({ ...s })) }
        : { steps: [] }
      form.grpc_config = {
        full_method: val.grpc_config?.full_method || '',
        service: val.grpc_config?.service || '',
        method: val.grpc_config?.method || '',
        use_tls: !!val.grpc_config?.use_tls,
      }
      form.response_schema = val.response_schema || {}
      syncBodyText()
    }
  } catch (error) {
    ElMessage.error('获取接口详情失败')
  }
}

// 监听弹窗打开，编辑模式下获取详情
watch(() => props.modelValue, (visible) => {
  if (visible) {
    proStore.refreshProjectGlobals()
    if (!refEnvId.value && proStore.envList.length) {
      refEnvId.value = proStore.envList[0].id
    }
    loadCatalogTree()
    if (props.data?.id) {
      nextTick(() => {
        fetchApiDetail(props.data.id)
      })
    }
  }
})

// 监听数据变化（首次打开或 data 引用变化时触发，先填上基础数据）
watch(() => props.data, (val) => {
  if (val) {
    form.name = val.name
    form.catalog_id = val.catalog_id ?? val.category_id ?? null
    form.protocol = val.protocol || 'http'
    form.method = val.method
    form.path = val.path
    form.base_url = val.base_url || ''
    form.description = val.description || ''
    form.headers = val.headers || []
    form.params = val.params || []
    form.body = val.body ?? {}
    form.body_type = val.body_type || 'json'
    form.body_fields = Array.isArray(val.body_fields) ? val.body_fields.map(f => ({
      name: f.name || '',
      value: f.value || '',
      field_type: f.field_type || 'text',
      file_name: f.file_name || '',
      mime_type: f.mime_type || 'application/octet-stream',
      file_key: f.file_key || '',
      file_bucket: f.file_bucket || '',
      description: f.description || ''
    })) : []
    form.ws_config = val.ws_config && Array.isArray(val.ws_config.steps)
      ? { steps: val.ws_config.steps.map(s => ({ ...s })) }
      : { steps: [] }
    form.grpc_config = {
      full_method: val.grpc_config?.full_method || '',
      service: val.grpc_config?.service || '',
      method: val.grpc_config?.method || '',
      use_tls: !!val.grpc_config?.use_tls,
    }
    form.response_schema = val.response_schema || {}
    syncBodyText()
  } else {
    resetForm()
  }
}, { immediate: true })

// 添加参数
const addParam = () => {
  form.params.push({
    name: '',
    value: '',
    type: 'string',
    required: true,
    description: ''
  })
}

// 删除参数
const removeParam = (index) => {
  form.params.splice(index, 1)
}

const onFormFieldFileUpdate = (index, patch) => {
  Object.assign(form.body_fields[index], patch)
}

const addFormField = () => {
  form.body_fields.push({
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
  form.body_fields.splice(index, 1)
}

// 保存
const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  if (form.body_type === 'form-data') {
    const invalidField = form.body_fields.find(f => f.field_type === 'file' && !f.file_key)
    if (invalidField) {
      ElMessage.error(`字段 ${invalidField.name || '未命名'} 需要先上传文件`)
      return
    }
  }

  let parsedBody = null
  const text = (bodyText.value || '').trim()
  if (form.protocol === 'graphql' || form.protocol === 'grpc') {
    if (text) {
      try {
        parsedBody = JSON.parse(text)
      } catch {
        ElMessage.error('请求 JSON 格式错误，请检查')
        return
      }
    } else {
      parsedBody = {}
    }
  } else if (form.body_type === 'form-data') {
    parsedBody = null
  } else if (isStructuredBodyType(form.body_type)) {
    if (text) {
      try {
        parsedBody = JSON.parse(text)
      } catch {
        ElMessage.error('请求体 JSON 格式错误，请检查')
        return
      }
    }
  } else {
    parsedBody = text || null
  }

  saving.value = true
  try {
    const data = {
      ...form,
      body: parsedBody ?? {},
      project_id: proStore.projectInfo.id,
      body_fields: form.body_fields.map(f => ({
      name: f.name,
      value: f.value,
      field_type: f.field_type,
      file_name: f.file_name,
      mime_type: f.mime_type,
      file_key: f.file_key,
      file_bucket: f.file_bucket,
      description: f.description
    }))
    }
    
    let savedApiId = null
    if (isEdit.value) {
      await http.apiModuleApi.updateApi(props.data.id, data)
      savedApiId = props.data.id
    } else {
      const res = await http.apiModuleApi.createApi(data)
      savedApiId = res.data?.id
    }
    
    ElMessage.success('保存成功')
    emit('success')
    emit('update:modelValue', false)
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 将测试响应保存为响应示例
const saveResponseAsExample = () => {
  if (!testResult.value?.response_detail?.body) {
    ElMessage.warning('没有可保存的响应数据')
    return
  }
  const body = testResult.value.response_detail.body
  if (!form.response_schema) form.response_schema = {}
  form.response_schema.example = typeof body === 'string' ? body : body
  ElMessage.success('已保存为响应示例')
}

// 测试接口
const handleTest = async () => {
  if (form.body_type === 'form-data') {
    const invalidField = form.body_fields.find(f => f.field_type === 'file' && !f.file_key)
    if (invalidField) {
      ElMessage.error(`字段 ${invalidField.name || '未命名'} 需要先上传文件`)
      return
    }
  }
  testing.value = true
  try {
    const envId = testForm.env_id || refEnvId.value
    if (!form.base_url?.trim() && !envId) {
      ElMessage.warning('基础URL 为空时请先选择参考环境或在测试弹窗中选择执行环境')
      return
    }

    const url = buildRequestUrl({
      baseUrl: form.base_url,
      path: form.path,
      envId,
    })

    // 关闭环境选择弹窗
    testDialogVisible.value = false
    
    // 按当前 body_type 从 bodyText 解析 body（确保测试时用的是文本框最新内容）
    let testBody = null
    const text = (bodyText.value || '').trim()
    if (form.body_type === 'form-data') {
      testBody = null
    } else if (isStructuredBodyType(form.body_type)) {
      if (text) {
        try {
          testBody = JSON.parse(text)
        } catch {
          ElMessage.error('请求体 JSON 格式错误，请检查')
          testing.value = false
          return
        }
      }
    } else {
      testBody = text || null
    }

    const res = await http.apiModuleApi.debugApi({
      method: form.method,
      url: url,
      headers: form.headers.filter(h => h.key && h.value),
      params: form.params,
      body: testBody ?? {},
      body_type: form.body_type,
      body_fields: form.body_type === 'form-data' ? form.body_fields : undefined,
      timeout: 30,
      env_id: envId || undefined,
      project_id: proStore.projectInfo?.id || undefined,
      ...(testForm.worker_id ? { worker_id: testForm.worker_id } : {}),
    })
    
    if (res.status === 200) {
      testResult.value = res.data
      testActiveTab.value = 'request'
      testResultVisible.value = true
    } else {
      ElMessage.error('测试失败')
    }
  } catch (error) {
    ElMessage.error('测试失败: ' + formatApiError(error))
  } finally {
    testing.value = false
  }
}
</script>

<style scoped lang="scss">
.var-toolbar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.var-toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  width: 100%;
  overflow-x: auto;
}

.var-toolbar-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 20px 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 500;
}

.param-table {
  margin-bottom: 15px;
  
  :deep(.el-table__cell) {
    padding: 4px 0;
  }
}

.code-editor {
  :deep(.el-textarea__inner) {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    line-height: 1.5;
  }
}

.env-host {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 5px;
}

// 测试结果样式
.test-result-dialog {
  .result-header {
    display: flex;
    align-items: center;
    gap: 20px;
    margin-bottom: 20px;
    padding-bottom: 15px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    
    .response-time {
      color: var(--el-text-color-secondary);
    }
  }
  
  .detail-section {
    max-height: 500px;
    overflow-y: auto;
  }
  
  .detail-block {
    margin-bottom: 20px;
    
    .detail-title {
      font-weight: 600;
      font-size: 14px;
      color: var(--el-text-color-primary);
      margin-bottom: 10px;
      padding-left: 8px;
      border-left: 3px solid var(--el-color-primary);
    }
    
    .detail-content {
      background: var(--el-fill-color-light);
      border-radius: 4px;
      padding: 12px;
      
      pre {
        margin: 0;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 13px;
        line-height: 1.5;
        white-space: pre-wrap;
        word-wrap: break-word;
        max-height: 300px;
        overflow-y: auto;
      }
      
      .compare-row {
        display: flex;
        align-items: center;
        margin-bottom: 8px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .label {
          width: 50px;
          color: var(--el-text-color-secondary);
          font-size: 13px;
        }
        
        code {
          flex: 1;
          padding: 4px 8px;
          border-radius: 4px;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 13px;
          word-break: break-all;
          
          &.original {
            background: #f5f5f5;
            color: #999;
            text-decoration: line-through;
          }
          
          &.final {
            background: #e6f7ff;
            color: #1890ff;
          }
        }
      }
    }
  }
}

.response-collapse {
  margin-top: 10px;

  .field-hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-top: 4px;
  }

  :deep(.response-field-item .el-form-item__label) {
    white-space: nowrap;
    height: auto !important;
    line-height: 32px;
    align-items: center;
  }

  .response-field-label {
    display: inline;
    white-space: nowrap;
  }

  .response-field-toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 4px;
  }
}

.hidden-file-input {
  display: none;
}

.label-tip {
  margin-left: 4px;
  color: var(--el-color-primary);
  cursor: pointer;
  vertical-align: middle;
}
</style>
