<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="导入接口"
    width="860px"
    destroy-on-close
  >
    <el-steps :active="currentStep" finish-status="success" simple class="import-steps">
      <el-step :title="importType === 'curl' ? '输入命令' : '选择文件'"/>
      <el-step :title="importType === 'jmeter' ? '预览确认' : '编辑确认'"/>
      <el-step title="导入完成"/>
    </el-steps>
    
    <!-- 第一步：输入 curl 命令 -->
    <div v-if="currentStep === 0" class="step-content">
      <el-form label-width="100px">
        <el-form-item label="导入类型">
          <el-radio-group v-model="importType">
            <el-radio-button label="swagger">Swagger/OpenAPI</el-radio-button>
            <el-radio-button label="postman">Postman</el-radio-button>
            <el-radio-button label="jmeter">JMeter</el-radio-button>
            <el-radio-button label="curl">Curl 命令</el-radio-button>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="所属目录">
          <el-tree-select
            v-model="targetCatalog"
            :data="catalogTree"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            clearable
            placeholder="不选择则导入到根目录"
          />
        </el-form-item>
        
        <!-- 文件导入 -->
        <el-form-item label="选择文件" v-if="importType !== 'curl'">
          <el-upload
            drag
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            :accept="importType === 'jmeter' ? '.jmx' : '.json,.yaml,.yml'"
            class="upload-area"
          >
            <el-icon class="el-icon--upload"><Upload-filled /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处或 <em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                <template v-if="importType === 'jmeter'">
                  支持 .jmx（仅转换 HTTP 请求；脚本/复杂控制器会告警）
                </template>
                <template v-else>
                  支持 .json, .yaml, .yml 格式的 {{ importType === 'swagger' ? 'Swagger/OpenAPI' : 'Postman Collection' }} 文件
                </template>
              </div>
            </template>
          </el-upload>
        </el-form-item>
        
        <!-- Curl 命令导入 -->
        <el-form-item label="Curl 命令" v-else>
          <el-input
            v-model="curlCommand"
            type="textarea"
            :rows="10"
            placeholder="请粘贴 curl 命令，例如：
curl -X POST 'http://api.example.com/users' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer token' \\
  -d '{&quot;name&quot;:&quot;test&quot;,&quot;age&quot;:18}'"
          />
          <div class="el-form-item__tip">
            支持标准 curl 命令格式，包括 -X, -H, -d 等常用参数
          </div>
        </el-form-item>
      </el-form>
    </div>
    
    <!-- 第二步：编辑确认 -->
    <div v-if="currentStep === 1" class="step-content">
      <!-- Curl 编辑表单 -->
      <template v-if="importType === 'curl' && previewData">
        <el-alert
          title="请确认接口信息"
          type="info"
          description="已解析 curl 命令，您可以编辑确认后再保存"
          show-icon
          :closable="false"
          class="parse-alert"
        />
        
        <el-form :model="previewData" :rules="formRules" ref="formRef" label-width="80px">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="接口名称" prop="name">
                <el-input v-model="previewData.name" placeholder="请输入接口名称"/>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="所属目录">
                <el-tree-select
                  v-model="previewData.catalog_id"
                  :data="catalogTree"
                  :props="{ label: 'name', value: 'id', children: 'children' }"
                  clearable
                  placeholder="请选择目录"
                />
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="6">
              <el-form-item label="请求方法" prop="method">
                <el-select v-model="previewData.method" placeholder="Method">
                  <el-option label="GET" value="GET"/>
                  <el-option label="POST" value="POST"/>
                  <el-option label="PUT" value="PUT"/>
                  <el-option label="DELETE" value="DELETE"/>
                  <el-option label="PATCH" value="PATCH"/>
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="18">
              <el-form-item label="接口路径" prop="path">
                <el-input v-model="previewData.path" placeholder="/api/v1/users"/>
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-form-item label="基础URL">
            <el-input v-model="previewData.base_url" placeholder="http://localhost:8080"/>
          </el-form-item>
          
          <el-form-item label="接口描述">
            <el-input v-model="previewData.description" type="textarea" rows="2" placeholder="接口功能描述"/>
          </el-form-item>
          
          <!-- 请求头 -->
          <div class="section-title">
            <span>请求头 (Headers)</span>
            <el-button type="primary" link size="small" @click="addHeader" icon="Plus">添加</el-button>
          </div>
          <el-table :data="previewData.headers" size="small" border class="param-table">
            <el-table-column label="Header名" width="180">
              <template #default="{ $index }">
                <el-input v-model="previewData.headers[$index].key" size="small" placeholder="Content-Type"/>
              </template>
            </el-table-column>
            <el-table-column label="Header值">
              <template #default="{ $index }">
                <el-input v-model="previewData.headers[$index].value" size="small" placeholder="application/json"/>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeHeader($index)" icon="Delete"/>
              </template>
            </el-table-column>
          </el-table>
          
          <!-- 请求参数 -->
          <div class="section-title">
            <span>查询参数 (Params)</span>
            <el-button type="primary" link size="small" @click="addParam" icon="Plus">添加</el-button>
          </div>
          <el-table :data="previewData.params" size="small" border class="param-table">
            <el-table-column label="参数名" width="150">
              <template #default="{ $index }">
                <el-input v-model="previewData.params[$index].name" size="small" placeholder="name"/>
              </template>
            </el-table-column>
            <el-table-column label="参数值" width="150">
              <template #default="{ $index }">
                <el-input v-model="previewData.params[$index].value" size="small" placeholder="value"/>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="100">
              <template #default="{ $index }">
                <el-select v-model="previewData.params[$index].type" size="small">
                  <el-option label="string" value="string"/>
                  <el-option label="integer" value="integer"/>
                  <el-option label="boolean" value="boolean"/>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeParam($index)" icon="Delete"/>
              </template>
            </el-table-column>
          </el-table>
          
          <!-- 请求体 -->
          <div class="section-title">
            <span>请求体 (Body)</span>
            <el-radio-group v-model="previewData.body_type" size="small">
              <el-radio-button label="json">JSON</el-radio-button>
              <el-radio-button label="form-data">Form Data</el-radio-button>
              <el-radio-button label="x-www-form-urlencoded">x-www-form-urlencoded</el-radio-button>
              <el-radio-button label="xml">XML</el-radio-button>
              <el-radio-button label="raw">Raw</el-radio-button>
            </el-radio-group>
          </div>
          <JsonTextarea
            v-model="previewData.body"
            :rows="6"
            :placeholder="bodyPlaceholder"
            :json-mode="previewData.body_type === 'json'"
            show-compact
          />
        </el-form>
        
        <!-- 测试结果展示 -->
        <div v-if="testResult" class="test-result">
          <div class="section-title">
            <span>测试结果</span>
            <el-tag :type="testResult.status_code >= 200 && testResult.status_code < 300 ? 'success' : 'danger'" size="small">
              {{ testResult.status_code }}
            </el-tag>
          </div>
          <div class="test-info">
            <div v-if="testResult.time" class="test-meta">
              响应时间: {{ testResult.time }}ms | 大小: {{ testResult.size }} bytes
            </div>
            <el-tabs type="border-card" class="test-tabs">
              <el-tab-pane label="响应体">
                <pre class="response-body">{{ formatResponse(testResult.body) }}</pre>
              </el-tab-pane>
              <el-tab-pane label="响应头">
                <pre class="response-body">{{ formatHeaders(testResult.headers) }}</pre>
              </el-tab-pane>
            </el-tabs>
          </div>
        </div>
      </template>
      
      <!-- JMeter 预览确认 -->
      <template v-else-if="importType === 'jmeter' && jmeterPreview">
        <el-alert
          :title="`已解析：${jmeterPreview.test_plan_name}`"
          type="info"
          :description="`将创建接口 ${jmeterPreview.counts?.apis || 0}、用例 ${jmeterPreview.counts?.cases || 0}、套件 ${jmeterPreview.counts?.suites || 0}、压测场景 ${jmeterPreview.counts?.perf_scenes || 0}；未支持节点 ${jmeterPreview.counts?.unsupported || 0}`"
          show-icon
          :closable="false"
          class="parse-alert"
        />
        <el-form label-width="110px" class="jmeter-options">
          <el-form-item label="冲突策略">
            <el-radio-group v-model="jmeterConflictStrategy">
              <el-radio label="merge_case">复用同 method+path 接口，新建用例</el-radio>
              <el-radio label="skip_existing">已存在则跳过</el-radio>
              <el-radio label="create_always">始终新建接口与用例</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="创建套件">
            <el-switch v-model="jmeterCreateSuites" />
            <span class="jmeter-hint">按 Thread Group 生成接口测试套件</span>
          </el-form-item>
          <el-form-item label="压测场景">
            <el-switch
              v-model="jmeterCreatePerfScenes"
              :disabled="!(jmeterPreview.counts?.perf_scenes > 0)"
            />
            <span class="jmeter-hint">
              <template v-if="jmeterPreview.counts?.perf_scenes > 0">
                可为 {{ jmeterPreview.counts.perf_scenes }} 个简单 Thread Group 生成 journey 压测场景（会同时创建套件）
              </template>
              <template v-else>
                无可自动生成的压测场景（含条件控制器/定时器的 Thread Group 已跳过）
              </template>
            </span>
          </el-form-item>
        </el-form>
        <el-table
          v-if="(jmeterPreview.suites || []).length"
          :data="jmeterPreview.suites"
          size="small"
          max-height="160"
          class="jmeter-suite-table"
        >
          <el-table-column label="Thread Group" prop="name" min-width="140" show-overflow-tooltip />
          <el-table-column label="请求数" width="80" align="center">
            <template #default="{ row }">{{ (row.sampler_paths || []).length }}</template>
          </el-table-column>
          <el-table-column label="压测" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.perf_eligible" size="small" type="success">可生成</el-tag>
              <el-tag v-else size="small" type="info">跳过</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.perf_eligible && row.perf_config">
                {{ row.perf_config.mode }} / {{ row.perf_config.concurrent_users }} 并发
              </span>
              <span v-else>{{ (row.perf_block_reasons || []).join('；') || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-table :data="jmeterPreview.apis || []" size="small" max-height="220">
          <el-table-column type="index" width="50"/>
          <el-table-column label="方法" width="80">
            <template #default="{ row }">
              <el-tag :type="getMethodType(row.method)" size="small">{{ row.method }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="路径" prop="path" show-overflow-tooltip/>
          <el-table-column label="名称" prop="name" show-overflow-tooltip/>
        </el-table>
        <el-alert
          v-if="(jmeterPreview.todos || []).length"
          title="待办"
          type="warning"
          :description="jmeterPreview.todos.join('；')"
          show-icon
          :closable="false"
          class="error-alert"
        />
        <el-collapse v-if="(jmeterPreview.unsupported_nodes || []).length" class="jmeter-unsupported">
          <el-collapse-item :title="`未支持节点（${jmeterPreview.unsupported_nodes.length}）`" name="1">
            <el-table :data="jmeterPreview.unsupported_nodes" size="small" max-height="180">
              <el-table-column label="类型" prop="type" width="140"/>
              <el-table-column label="路径" prop="source_path" show-overflow-tooltip/>
              <el-table-column label="原因" prop="reason" show-overflow-tooltip/>
            </el-table>
          </el-collapse-item>
        </el-collapse>
        <el-alert
          v-if="(jmeterPreview.warnings || []).length"
          :title="`警告 ${jmeterPreview.warnings.length} 条`"
          type="warning"
          :description="jmeterPreview.warnings.slice(0, 8).join('；')"
          show-icon
          :closable="false"
          class="error-alert"
        />
      </template>

      <!-- 文件导入结果预览 -->
      <template v-else>
        <el-alert
          title="文件解析成功"
          type="success"
          :description="`共发现 ${parseResult.total} 个接口，成功导入 ${parseResult.success} 个，失败 ${parseResult.failed} 个`"
          show-icon
          :closable="false"
          class="parse-alert"
        />
        
        <el-table :data="parseResult.apis" size="small" max-height="300" v-if="parseResult.apis.length > 0">
          <el-table-column type="index" width="50"/>
          <el-table-column label="方法" width="80">
            <template #default="{ row }">
              <el-tag :type="getMethodType(row.method)" size="small">{{ row.method }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="路径" prop="path" show-overflow-tooltip/>
          <el-table-column label="名称" prop="name" show-overflow-tooltip/>
        </el-table>
        
        <el-alert
          v-if="parseResult.errors.length > 0"
          :title="`导入失败 ${parseResult.errors.length} 个`"
          type="warning"
          :description="parseResult.errors.join('；')"
          show-icon
          :closable="false"
          class="error-alert"
        />
      </template>
    </div>
    
    <!-- 第三步：导入完成 -->
    <div v-if="currentStep === 2" class="step-content">
      <div class="success-result">
        <el-icon class="success-icon"><Circle-check /></el-icon>
        <h3>导入完成</h3>
        <template v-if="importType === 'jmeter' && jmeterCommitResult">
          <p>
            新建接口 {{ jmeterCommitResult.created_apis }}，
            新建用例 {{ jmeterCommitResult.created_cases }}，
            合并用例 {{ jmeterCommitResult.merged_cases }}，
            跳过 {{ jmeterCommitResult.skipped }}，
            失败 {{ jmeterCommitResult.failed }}，
            套件 {{ jmeterCommitResult.created_suites }}，
            压测场景 {{ jmeterCommitResult.created_scenes || 0 }}
          </p>
        </template>
        <p v-else>成功导入 {{ parseResult.success }} 个接口</p>
      </div>
    </div>
    
    <template #footer>
      <!-- 第一步：只显示下一步 -->
      <template v-if="currentStep === 0">
        <el-button 
          type="primary" 
          @click="handleNext" 
          :loading="importing"
          :disabled="importType === 'curl' ? !curlCommand.trim() : !selectedFile"
        >
          下一步
        </el-button>
      </template>
      
      <!-- 第二步：JMeter 确认导入 -->
      <template v-if="currentStep === 1 && importType === 'jmeter'">
        <el-button @click="currentStep = 0">上一步</el-button>
        <el-button
          type="primary"
          @click="handleJmeterCommit"
          :loading="importing"
          :disabled="!(jmeterPreview?.counts?.apis > 0)"
        >
          确认导入
        </el-button>
      </template>

      <!-- 第二步：curl / 其它 -->
      <template v-else-if="currentStep === 1">
        <el-button @click="currentStep = 0; testResult = null">上一步</el-button>
        <el-button v-if="importType === 'curl'" type="warning" @click="openTestEnvDialog" :loading="testing">
          测试
        </el-button>
        <el-button type="primary" @click="handleSave" :loading="importing">
          保存
        </el-button>
      </template>
      
      <!-- 第三步：显示继续导入 -->
      <template v-if="currentStep === 2">
        <el-button type="primary" @click="resetAndContinue">继续导入</el-button>
      </template>
    </template>
  </el-dialog>
  
  <!-- 环境选择弹窗 -->
  <el-dialog
    v-model="showEnvDialog"
    title="选择测试环境"
    width="400px"
    append-to-body
    destroy-on-close
  >
    <div class="env-select-content">
      <p class="env-hint">请选择要使用的测试环境（可选）</p>
      <el-select 
        v-model="selectedEnvId" 
        placeholder="选择环境（可选）" 
        clearable
        style="width: 100%"
      >
        <el-option
          v-for="env in envList"
          :key="env.id"
          :label="env.name"
          :value="env.id"
        />
      </el-select>
    </div>
    <template #footer>
      <el-button @click="showEnvDialog = false">取消</el-button>
      <el-button type="primary" @click="confirmTest" :loading="testing">
        开始测试
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'

import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'
import JsonTextarea from '@/components/JsonTextarea.vue'

const props = defineProps({
  modelValue: Boolean
})

const emit = defineEmits(['update:modelValue', 'success'])

const proStore = ProjectStore()
const formRef = ref()

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

const currentStep = ref(0)
const importType = ref('curl')  // 默认curl
const targetCatalog = ref(null)
const selectedFile = ref(null)
const curlCommand = ref('')
const importing = ref(false)
const testing = ref(false)
const testResult = ref(null)
const showEnvDialog = ref(false)  // 环境选择弹窗
const selectedEnvId = ref(null)   // 选中的环境ID
const envList = ref([])           // 环境列表

// 预览数据（用于编辑）
const previewData = ref(null)
const jmeterPreview = ref(null)
const jmeterCommitResult = ref(null)
const jmeterConflictStrategy = ref('merge_case')
const jmeterCreateSuites = ref(true)
const jmeterCreatePerfScenes = ref(false)

const parseResult = reactive({
  total: 0,
  success: 0,
  failed: 0,
  errors: [],
  apis: []
})

const formRules = {
  name: [{ required: true, message: '请输入接口名称', trigger: 'blur' }],
  method: [{ required: true, message: '请选择请求方法', trigger: 'change' }],
  path: [{ required: true, message: '请输入接口路径', trigger: 'blur' }]
}

const bodyPlaceholder = computed(() => {
  switch (previewData.value?.body_type) {
    case 'json':
      return '{"key": "value"}'
    case 'form-data':
      return 'Form Data 请通过接口编辑页的表格编辑文件字段'
    case 'x-www-form-urlencoded':
      return '示例：name=张三&age=18'
    case 'xml':
      return '<xml>...</xml>'
    case 'raw':
      return '任意文本内容'
    default:
      return '请求体内容'
  }
})

// body_type 变化时，设置默认值
watch(() => props.modelValue, (visible) => {
  if (visible) loadCatalogTree()
})

watch(() => previewData.value?.body_type, (newType) => {
  if (!previewData.value) return
  if (newType === 'json' && !previewData.value.body) {
    previewData.value.body = '{}'
  }
})

const getMethodType = (method) => {
  const map = {
    'GET': 'success',
    'POST': 'primary',
    'PUT': 'warning',
    'DELETE': 'danger',
    'PATCH': 'info'
  }
  return map[method] || ''
}

const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

const handleNext = async () => {
  if (importType.value === 'curl') {
    if (!curlCommand.value.trim()) {
      ElMessage.warning('请输入 curl 命令')
      return
    }
    await parseCurlCommand()
  } else if (importType.value === 'jmeter') {
    if (!selectedFile.value) {
      ElMessage.warning('请选择 .jmx 文件')
      return
    }
    await handleJmeterPreview()
  } else {
    if (!selectedFile.value) {
      ElMessage.warning('请选择文件')
      return
    }
    await handleFileImport()
  }
}

const handleJmeterPreview = async () => {
  importing.value = true
  jmeterPreview.value = null
  jmeterCommitResult.value = null
  try {
    const res = await http.apiModuleApi.importJmeterPreview(
      proStore.projectInfo.id,
      selectedFile.value,
      targetCatalog.value
    )
    if (res.status === 200) {
      jmeterPreview.value = res.data
      jmeterCreatePerfScenes.value = (res.data.counts?.perf_scenes || 0) > 0
      currentStep.value = 1
      if (!(res.data.counts?.apis > 0)) {
        ElMessage.warning('未解析到可导入的 HTTP 请求，请查看未支持节点说明')
      }
    }
  } catch (error) {
    ElMessage.error('解析失败：' + (error.response?.data?.detail || error.message))
  } finally {
    importing.value = false
  }
}

const handleJmeterCommit = async () => {
  if (!jmeterPreview.value?.preview_token) {
    ElMessage.warning('预览已失效，请重新上传')
    return
  }
  importing.value = true
  try {
    const res = await http.apiModuleApi.importJmeterCommit({
      preview_token: jmeterPreview.value.preview_token,
      project_id: proStore.projectInfo.id,
      catalog_id: targetCatalog.value,
      conflict_strategy: jmeterConflictStrategy.value,
      create_suites: jmeterCreateSuites.value || jmeterCreatePerfScenes.value,
      create_perf_scenes: jmeterCreatePerfScenes.value
    })
    if (res.status === 200) {
      jmeterCommitResult.value = res.data
      parseResult.success = (res.data.created_apis || 0) + (res.data.merged_cases || 0)
      currentStep.value = 2
      emit('success')
      ElMessage.success('JMeter 导入完成')
    }
  } catch (error) {
    ElMessage.error('导入失败：' + (error.response?.data?.detail || error.message))
  } finally {
    importing.value = false
  }
}

// 解析 curl 命令
const parseCurlCommand = async () => {
  importing.value = true
  try {
    const res = await http.apiModuleApi.parseCurl({
      curl_command: curlCommand.value,
      project_id: proStore.projectInfo.id,
      catalog_id: targetCatalog.value
    })
    
    if (res.status === 200 && res.data.success) {
      previewData.value = { ...res.data.api }
      // 将 none 映射为 raw（新选项中没有 none）
      if (previewData.value.body_type === 'none') {
        previewData.value.body_type = 'raw'
      }
      // 设置 body 文本 - 将对象转为字符串便于编辑
      if (previewData.value.body) {
        if (typeof previewData.value.body === 'object') {
          previewData.value.body = JSON.stringify(previewData.value.body, null, 2)
        }
      }
      currentStep.value = 1
    } else {
      ElMessage.error(res.data.message || '解析失败')
    }
  } catch (error) {
    ElMessage.error('解析失败：' + (error.response?.data?.detail || error.message))
  } finally {
    importing.value = false
  }
}

// 文件导入
const handleFileImport = async () => {
  importing.value = true
  try {
    const res = importType.value === 'swagger'
      ? await http.apiModuleApi.importSwagger(proStore.projectInfo.id, selectedFile.value, targetCatalog.value)
      : await http.apiModuleApi.importPostman(proStore.projectInfo.id, selectedFile.value, targetCatalog.value)
    
    if (res.status === 200) {
      parseResult.total = res.data.total
      parseResult.success = res.data.success
      parseResult.failed = res.data.failed
      parseResult.errors = res.data.errors
      parseResult.apis = res.data.apis
      
      // 文件导入如果成功直接完成
      if (res.data.success > 0) {
        currentStep.value = 2
        emit('success')
      } else {
        currentStep.value = 1
      }
    }
  } catch (error) {
    ElMessage.error('导入失败：' + (error.response?.data?.detail || error.message))
  } finally {
    importing.value = false
  }
}

// 获取环境列表
const fetchEnvList = async () => {
  try {
    const res = await http.environmentApi.getList({ project_id: proStore.projectInfo.id })
    if (res.status === 200) {
      envList.value = res.data || []
    }
  } catch (error) {
    console.error('获取环境列表失败:', error)
  }
}

// 打开环境选择弹窗
const openTestEnvDialog = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  
  await fetchEnvList()
  selectedEnvId.value = null
  showEnvDialog.value = true
}

// 确认测试（选择环境后）
const confirmTest = async () => {
  showEnvDialog.value = false
  testing.value = true
  testResult.value = null
  
  try {
    // 组合完整URL
    let url = previewData.value.base_url || ''
    const path = previewData.value.path || ''
    if (url && path) {
      // 处理 URL 拼接，避免重复斜杠
      url = url.replace(/\/$/, '')
      const pathWithSlash = path.startsWith('/') ? path : '/' + path
      url = url + pathWithSlash
    }
    
    // 构建测试数据
    const testData = {
      method: previewData.value.method,
      url: url,
      headers: previewData.value.headers || [],
      params: previewData.value.params || [],
      body_type: previewData.value.body_type,
      body: previewData.value.body,
      timeout: 30,
      env_id: selectedEnvId.value || undefined
    }
    
    // 处理 body - 按类型解析
    const text = (testData.body || '').trim()
    if (testData.body_type === 'json') {
      if (text) {
        try {
          testData.body = JSON.parse(text)
        } catch {
          // 保持原样（字符串）
        }
      }
      if (!testData.body) {
        testData.body = {}
      }
    } else if (testData.body_type === 'form-data') {
      testData.body = null
    } else {
      // x-www-form-urlencoded / xml / raw
      testData.body = text || null
    }
    
    const res = await http.apiModuleApi.debugApi(testData)
    
    if (res.status === 200) {
      testResult.value = res.data
      ElMessage.success('测试成功')
    } else {
      ElMessage.error(res.data?.detail || '测试失败')
    }
  } catch (error) {
    ElMessage.error('测试失败：' + (error.response?.data?.detail || error.message))
  } finally {
    testing.value = false
  }
}

// 保存 curl 导入的接口
const handleSave = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  
  importing.value = true
  try {
    // 构建请求数据
    const data = {
      ...previewData.value,
      project_id: proStore.projectInfo.id,
      catalog_id: previewData.value.catalog_id || targetCatalog.value
    }
    
    // 处理 body - 按类型解析
    const bodyText = (data.body || '').trim()
    if (data.body_type === 'json') {
      if (bodyText) {
        try {
          data.body = JSON.parse(bodyText)
        } catch {
          // 保持原样（字符串）
        }
      }
      if (!data.body) {
        data.body = {}
      }
    } else if (data.body_type === 'form-data') {
      data.body = {}
    } else {
      // x-www-form-urlencoded / xml / raw
      data.body = bodyText || {}
    }
    
    const res = await http.apiModuleApi.importCurl(data)
    
    if ((res.status === 200 || res.status === 201) && res.data.success) {
      parseResult.total = 1
      parseResult.success = 1
      parseResult.failed = 0
      parseResult.apis = res.data.api ? [res.data.api] : []
      
      currentStep.value = 2
      emit('success')
      ElMessage.success(res.data.message)
      // 不自动关闭，让用户点击"继续导入"按钮
    } else {
      ElMessage.error(res.data.message || '保存失败')
    }
  } catch (error) {
    ElMessage.error('保存失败：' + (error.response?.data?.detail || error.message))
  } finally {
    importing.value = false
  }
}

// 格式化响应数据
const formatResponse = (data) => {
  if (!data) return ''
  if (typeof data === 'object') {
    return JSON.stringify(data, null, 2)
  }
  return data
}

const formatHeaders = (headers) => {
  if (!headers) return ''
  if (typeof headers === 'object') {
    return JSON.stringify(headers, null, 2)
  }
  return headers
}

// Headers 操作
const addHeader = () => {
  previewData.value.headers.push({ key: '', value: '', description: '' })
}

const removeHeader = (index) => {
  previewData.value.headers.splice(index, 1)
}

// Params 操作
const addParam = () => {
  previewData.value.params.push({ name: '', value: '', type: 'string', required: true })
}

const removeParam = (index) => {
  previewData.value.params.splice(index, 1)
}

const handleClose = () => {
  currentStep.value = 0
  importType.value = 'curl'
  targetCatalog.value = null
  selectedFile.value = null
  curlCommand.value = ''
  previewData.value = null
  jmeterPreview.value = null
  jmeterCommitResult.value = null
  jmeterConflictStrategy.value = 'merge_case'
  jmeterCreateSuites.value = true
  jmeterCreatePerfScenes.value = false
  testResult.value = null
  parseResult.total = 0
  parseResult.success = 0
  parseResult.failed = 0
  parseResult.errors = []
  parseResult.apis = []
  emit('update:modelValue', false)
}

// 重置并继续导入（第三步点击）
const resetAndContinue = () => {
  currentStep.value = 0
  curlCommand.value = ''
  selectedFile.value = null
  previewData.value = null
  jmeterPreview.value = null
  jmeterCommitResult.value = null
  jmeterConflictStrategy.value = 'merge_case'
  jmeterCreateSuites.value = true
  jmeterCreatePerfScenes.value = false
  testResult.value = null
  parseResult.total = 0
  parseResult.success = 0
  parseResult.failed = 0
  parseResult.errors = []
  parseResult.apis = []
}
</script>

<style scoped lang="scss">
.import-steps {
  margin-bottom: 20px;
}

.step-content {
  min-height: 200px;
  max-height: 520px;
  overflow-y: auto;
}

.jmeter-options {
  margin: 12px 0;
}

.jmeter-hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.jmeter-unsupported {
  margin-top: 12px;
}

.jmeter-suite-table {
  margin-bottom: 12px;
}

.upload-area {
  width: 100%;
  
  :deep(.el-upload-dragger) {
    width: 100%;
    height: 180px;
  }
}

.parse-alert {
  margin-bottom: 15px;
}

.error-alert {
  margin-top: 15px;
}

.success-result {
  text-align: center;
  padding: 40px 0;
  
  .success-icon {
    font-size: 64px;
    color: var(--el-color-success);
    margin-bottom: 20px;
  }
  
  h3 {
    font-size: 20px;
    margin-bottom: 10px;
    color: var(--el-text-color-primary);
  }
  
  p {
    color: var(--el-text-color-secondary);
  }
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 20px 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-light);
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.param-table {
  margin-bottom: 15px;
}

:deep(.el-textarea__inner) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

.test-result {
  margin-top: 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  padding: 15px;
  background: var(--el-fill-color-light);
  
  .section-title {
    margin-top: 0;
    margin-bottom: 15px;
  }
  
  .test-info {
    .test-meta {
      margin-bottom: 10px;
      color: var(--el-text-color-secondary);
      font-size: 13px;
    }
    
    .test-tabs {
      :deep(.el-tabs__content) {
        padding: 10px;
      }
      
      .response-body {
        margin: 0;
        padding: 10px;
        background: var(--el-bg-color);
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 4px;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 12px;
        line-height: 1.5;
        max-height: 200px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-all;
      }
    }
  }
}

.env-select-content {
  padding: 20px 0;
  
  .env-hint {
    margin-bottom: 15px;
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }
}
</style>
