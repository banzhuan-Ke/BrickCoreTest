<template>
  <el-dialog
    v-model="visible"
    :title="`🤖 AI 生成用例 - ${apiData?.name || ''}`"
    width="900px"
    destroy-on-close
    :close-on-click-modal="false"
    class="ai-generator-dialog"
  >
    <div v-if="!generatedCases.length && !generating" class="generator-form">
      <!-- 接口信息卡片 -->
      <el-card shadow="never" class="api-info-card">
        <div class="api-info-row">
          <el-tag :type="getMethodType(apiData?.method)" size="small">{{ apiData?.method }}</el-tag>
          <code class="api-path">{{ apiData?.path }}</code>
        </div>
        <div v-if="apiData?.description" class="api-desc">{{ apiData.description }}</div>
        <div v-if="(apiData?.case_count ?? 0) > 0" class="existing-cases-hint">
          <el-tag type="warning" size="small">已有 {{ apiData.case_count }} 条用例</el-tag>
          <span>AI 将参考已有用例的断言风格，并避免生成重复场景</span>
        </div>
        <div v-if="apiData?.body_type" class="existing-cases-hint">
          <el-tag size="small">请求体：{{ apiData.body_type }}</el-tag>
          <span>生成用例将按该类型输出（form-data 含字段表，不会误写成 JSON）</span>
        </div>
      </el-card>

      <!-- 响应结构信息 -->
      <el-card v-if="apiData?.response_schema && Object.keys(apiData.response_schema).length" shadow="never" class="response-schema-card">
        <el-collapse>
          <el-collapse-item title="📋 已关联响应结构定义（AI 将基于此生成精准断言）" name="schema">
            <div v-if="apiData.response_schema.example" class="schema-section">
              <div class="schema-label">响应示例</div>
              <pre class="schema-code">{{ formatExample(apiData.response_schema.example) }}</pre>
            </div>
            <div v-else-if="apiData.response_schema.schema" class="schema-section">
              <div class="schema-label">响应 Schema</div>
              <pre class="schema-code">{{ JSON.stringify(apiData.response_schema.schema, null, 2) }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>
      <el-alert
        v-else
        title="该接口暂无响应结构定义，AI 将基于请求信息推断响应格式"
        type="info"
        :closable="false"
        show-icon
        class="no-schema-alert"
      >
        <template #default>
          <div>建议：在接口编辑页维护响应示例，或在下方补充要求中描述预期响应格式，以提升生成断言的精准度</div>
        </template>
      </el-alert>

      <!-- 生成配置 -->
      <el-form :model="form" label-width="100px" class="gen-form">
        <el-form-item label="生成数量">
          <el-slider v-model="form.count" :min="1" :max="10" show-stops style="width: 300px;" />
          <span class="count-label">{{ form.count }} 条</span>
        </el-form-item>
        <el-form-item label="补充要求">
          <el-input
            v-model="form.prompt_override"
            type="textarea"
            :rows="3"
            placeholder="例如：重点测试边界值和鉴权场景。&#10;如果接口无响应结构定义，可在此描述预期返回格式，如：返回 {code: 0, data: {list: [], total: 0}}"
          />
        </el-form-item>
        <el-form-item label="所属目录">
          <el-tree-select
            v-model="form.catalog_id"
            :data="catalogTree"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            placeholder="选择目录（可选）"
            clearable
            style="width: 250px;"
          />
        </el-form-item>
        <el-form-item label="AI 模型">
          <el-select
            v-model="aiConfigId"
            placeholder="默认模型"
            clearable
            style="width: 100%; max-width: 400px;"
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
      </el-form>
    </div>

    <!-- 生成中 -->
    <div v-if="generating" class="generating-state">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
      <p>AI 正在生成测试用例，请稍候...</p>
      <p class="hint">根据接口复杂度，通常需要 10-30 秒</p>
    </div>

    <!-- 生成结果 -->
    <div v-if="generatedCases.length && !generating" class="result-section">
      <div class="result-header">
        <span class="result-title">生成结果（{{ generatedCases.length }} 条）</span>
        <el-button type="primary" size="small" @click="handleRegenerate" icon="Refresh">重新生成</el-button>
      </div>

      <el-alert v-if="errors.length" :title="`校验提示：${errors.join('；')}`" type="warning" show-icon :closable="false" class="error-alert" />

      <div class="case-list">
        <el-card
          v-for="(item, index) in generatedCases"
          :key="index"
          shadow="never"
          class="case-card"
        >
          <div class="case-header">
            <div class="case-title">
              <el-tag size="small" type="info">#{{ index + 1 }}</el-tag>
              <el-tag v-if="item.request_body_type" size="small" type="warning">{{ item.request_body_type }}</el-tag>
              <el-input v-model="item.name" size="small" class="name-input" placeholder="用例名称" />
            </div>
            <el-button type="danger" link size="small" @click="handleDeleteCase(index)" icon="Delete">删除</el-button>
          </div>

          <el-collapse>
            <el-collapse-item title="请求参数">
              <div class="json-block">
                <div class="json-label">Headers</div>
                <el-input v-model="item._request_headers_str" type="textarea" :rows="2" size="small" />
              </div>
              <div class="json-block">
                <div class="json-label">Params</div>
                <el-input v-model="item._request_params_str" type="textarea" :rows="2" size="small" />
              </div>
              <div v-if="item.request_body_type === 'form-data'" class="json-block">
                <div class="json-label">Form Data 字段</div>
                <el-table :data="item.request_body_fields || []" size="small" border max-height="220">
                  <el-table-column label="字段名" prop="name" min-width="100" />
                  <el-table-column label="类型" prop="field_type" width="80" />
                  <el-table-column label="值" min-width="140" show-overflow-tooltip>
                    <template #default="{ row }">
                      <span v-if="row.field_type === 'file'" class="file-hint">（文件，导入后请上传）</span>
                      <span v-else>{{ row.value }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="说明" prop="description" show-overflow-tooltip />
                </el-table>
              </div>
              <div v-else class="json-block">
                <div class="json-label">Body（{{ item.request_body_type || 'json' }}）</div>
                <el-input v-model="item._request_body_str" type="textarea" :rows="3" size="small" />
              </div>
            </el-collapse-item>

            <el-collapse-item :title="`断言规则 (${(item.assertions || []).length})`">
              <el-table :data="item.assertions || []" size="small" border max-height="200">
                <el-table-column label="类型" prop="type" width="110" />
                <el-table-column label="目标路径" prop="target" width="150" show-overflow-tooltip />
                <el-table-column label="操作符" prop="operator" width="100" />
                <el-table-column label="期望值" prop="expected" show-overflow-tooltip />
                <el-table-column label="描述" prop="description" show-overflow-tooltip />
              </el-table>
            </el-collapse-item>

            <el-collapse-item :title="`变量提取 (${(item.extractors || []).length})`">
              <el-table :data="item.extractors || []" size="small" border max-height="160">
                <el-table-column label="变量名" prop="name" width="120" />
                <el-table-column label="来源" prop="source" width="110" />
                <el-table-column label="提取路径" prop="path" />
                <el-table-column label="描述" prop="description" show-overflow-tooltip />
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <template v-if="!generatedCases.length && !generating">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" @click="handleGenerate" :loading="generating" icon="MagicStick">开始生成</el-button>
        </template>
        <template v-if="generatedCases.length && !generating">
          <el-button @click="visible = false">关闭</el-button>
          <el-button type="primary" @click="handleImport" :loading="importing" icon="Download">一键导入</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { aiGenerateApi } from '@/api/modules/ai'
import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import { formatResponseExample } from '@/utils/responseExample'

const formatExample = formatResponseExample

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const props = defineProps({
  modelValue: Boolean,
  apiData: Object
})

const emit = defineEmits(['update:modelValue', 'success'])

const proStore = ProjectStore()
const visible = ref(false)
const generating = ref(false)
const importing = ref(false)
const generatedCases = ref([])
const errors = ref([])
const catalogTree = ref([])

const form = reactive({
  count: 3,
  prompt_override: '',
  catalog_id: null
})

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val) {
    resetForm()
    loadCatalogTree()
    await loadConfigs()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const resetForm = () => {
  form.count = 3
  form.prompt_override = ''
  form.catalog_id = null
  generatedCases.value = []
  errors.value = []
}

const loadCatalogTree = async () => {
  try {
    const res = await catalogApi.getList({ project_id: proStore.projectInfo.id, tree: true })
    if (res.status === 200) {
      const data = res.data
      catalogTree.value = Array.isArray(data) && data.some(item => item.children?.length)
        ? data
        : buildCatalogTree(data || [])
    }
  } catch (error) {
    console.error('加载测试目录失败:', error)
  }
}

const getMethodType = (method) => {
  const map = { 'GET': 'success', 'POST': 'primary', 'PUT': 'warning', 'DELETE': 'danger', 'PATCH': 'info' }
  return map[method] || ''
}

const objToStr = (obj) => {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return '{}'
  }
}

const strToObj = (str) => {
  try {
    return JSON.parse(str)
  } catch {
    return {}
  }
}

const handleGenerate = async () => {
  if (!props.apiData?.id) {
    ElMessage.warning('接口信息不完整')
    return
  }

  generating.value = true
  generatedCases.value = []
  errors.value = []

  try {
    const res = await aiGenerateApi.generateApiCase({
      api_definition_id: props.apiData.id,
      count: form.count,
      prompt_override: form.prompt_override || undefined,
      catalog_id: form.catalog_id || undefined,
      ai_config_id: aiConfigId.value || undefined,
    })

    if (res.status === 200 && res.data?.data?.cases) {
      generatedCases.value = res.data.data.cases.map(item => ({
        ...item,
        request_body_type: item.request_body_type || props.apiData?.body_type || 'json',
        request_body_fields: Array.isArray(item.request_body_fields) ? item.request_body_fields : [],
        _request_headers_str: objToStr(item.request_headers),
        _request_params_str: objToStr(item.request_params),
        _request_body_str: objToStr(item.request_body)
      }))
      errors.value = res.data.data.errors || []

      if (errors.value.length > 0) {
        ElMessage.warning(`生成完成，但存在 ${errors.value.length} 处校验提示`)
      } else {
        ElMessage.success(`成功生成 ${generatedCases.value.length} 条用例`)
      }
    } else {
      ElMessage.error(res.data?.message || '生成失败')
    }
  } catch (error) {
    console.error('生成失败:', error)
    ElMessage.error(error.response?.data?.detail || 'AI 生成失败，请检查 LLM 配置')
  } finally {
    generating.value = false
  }
}

const handleRegenerate = () => {
  generatedCases.value = []
  errors.value = []
}

const handleDeleteCase = (index) => {
  generatedCases.value.splice(index, 1)
}

const handleImport = async () => {
  if (!generatedCases.value.length) {
    ElMessage.warning('没有可导入的用例')
    return
  }

  const casesToImport = generatedCases.value.map(item => ({
    name: item.name,
    request_headers: strToObj(item._request_headers_str),
    request_params: strToObj(item._request_params_str),
    request_body: item.request_body_type === 'form-data' ? {} : strToObj(item._request_body_str),
    request_body_type: item.request_body_type || props.apiData?.body_type || 'json',
    request_body_fields: item.request_body_type === 'form-data'
      ? (item.request_body_fields || [])
      : [],
    assertions: item.assertions || [],
    extractors: item.extractors || [],
    priority: item.priority || 'P2',
    tags: item.tags || []
  }))

  importing.value = true
  try {
    const res = await aiGenerateApi.importApiCases({
      api_definition_id: props.apiData.id,
      cases: casesToImport,
      catalog_id: form.catalog_id || undefined
    })

    if (res.status === 200) {
      const importedCount = res.data?.data?.imported_count || 0
      ElMessage.success(`成功导入 ${importedCount} 条用例`)
      visible.value = false
      emit('success')
    } else {
      ElMessage.error(res.data?.message || '导入失败')
    }
  } catch (error) {
    console.error('导入失败:', error)
    ElMessage.error(error.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped lang="scss">
.ai-generator-dialog {
  :deep(.el-dialog__body) {
    max-height: 70vh;
    overflow-y: auto;
    padding-top: 10px;
  }

  .generator-form {
    .api-info-card {
      margin-bottom: 20px;
      background: var(--el-fill-color-light);

      .api-info-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;

        .api-path {
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 14px;
          color: var(--el-color-primary);
        }
      }

      .api-desc {
        color: var(--el-text-color-secondary);
        font-size: 13px;
      }

      .existing-cases-hint {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 8px;
        font-size: 13px;
        color: var(--el-text-color-secondary);
      }
    }

    .gen-form {
      .count-label {
        margin-left: 15px;
        color: var(--el-text-color-secondary);
        font-size: 14px;
      }
    }

    .response-schema-card {
      margin-bottom: 15px;
      background: var(--el-fill-color-light);

      .schema-section {
        margin-bottom: 10px;

        .schema-label {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          margin-bottom: 5px;
        }

        .schema-code {
          background: var(--el-bg-color);
          padding: 10px;
          border-radius: 4px;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 12px;
          max-height: 200px;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-word;
          margin: 0;
        }
      }
    }

    .no-schema-alert {
      margin-bottom: 15px;
    }
  }

  .generating-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;

    p {
      margin-top: 15px;
      color: var(--el-text-color-primary);
      font-size: 16px;
    }

    .hint {
      color: var(--el-text-color-secondary);
      font-size: 13px;
    }
  }

  .result-section {
    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 15px;

      .result-title {
        font-weight: 600;
        font-size: 15px;
      }
    }

    .error-alert {
      margin-bottom: 15px;
    }

    .case-list {
      display: flex;
      flex-direction: column;
      gap: 12px;

      .case-card {
        .case-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;

          .case-title {
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;

            .name-input {
              flex: 1;
              max-width: 400px;
            }
          }
        }

        .json-block {
          margin-bottom: 10px;

          .json-label {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-bottom: 4px;
          }

          .file-hint {
            color: var(--el-text-color-secondary);
            font-size: 12px;
          }
        }
      }
    }
  }

  .dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }
}
</style>
