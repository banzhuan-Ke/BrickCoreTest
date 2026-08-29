<template>
  <el-dialog
    :model-value="modelValue"
    width="720px"
    class="mock-dialog"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <template #header>
      <div class="mock-dialog__title">
        <span>{{ dialogTitle }}</span>
        <el-button link type="primary" @click="openMockDocs">查看帮助手册</el-button>
      </div>
    </template>

    <div class="mock-tip">
      <div class="mock-tip__main">
        调用地址：<code>{平台}/api-module/mock-call/{匹配路径}</code>
        · 方法须与配置一致 · 响应 Body 填什么就返回什么
      </div>
      <div class="mock-tip__sub">
        <template v-if="mode === 'copy'">
          已复制方法/路径/响应；请改<strong>名称</strong>与<strong>高级匹配</strong>（以及需要时的 Body），保存后成为新场景。
        </template>
        <template v-else>
          同 URL 要返回不同内容：列表「复制为新场景」可少填一遍；或新建多条，方法+路径相同，用高级匹配区分。
        </template>
      </div>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" class="mock-form">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="列表里好辨认即可，如「订单-待支付」" maxlength="100" show-word-limit />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="请求方法" prop="method">
            <el-select v-model="form.method" style="width:100%">
              <el-option v-for="m in methods" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="16">
          <el-form-item label="匹配路径" prop="path">
            <el-input v-model="form.path" placeholder="/api/order" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="响应状态码" prop="response_status">
            <el-input v-model.number="form.response_status" type="number" :min="100" :max="599" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="延迟(ms)" prop="response_delay">
            <el-input v-model.number="form.response_delay" type="number" :min="0" :max="60000" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="启用">
            <el-switch v-model="form.is_enabled" active-text="启用" inactive-text="禁用" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="响应 Headers">
        <div class="json-field">
          <div class="json-field__bar">
            <el-button size="small" text @click="formatJson('response_headers')">格式化</el-button>
          </div>
          <el-input
            v-model="form.response_headers_str"
            type="textarea"
            :rows="2"
            placeholder='{"Content-Type": "application/json"}'
            :class="{ 'json-error': jsonErrors.response_headers }"
          />
          <div v-if="jsonErrors.response_headers" class="json-field__err">JSON 格式错误</div>
        </div>
      </el-form-item>

      <el-form-item label="响应 Body" prop="response_body_str">
        <div class="json-field">
          <div class="json-field__bar">
            <el-button size="small" type="primary" plain :loading="aiGenerating" @click="openAiDialog">AI 生成响应体</el-button>
            <el-button size="small" text @click="formatJson('response_body')">格式化</el-button>
          </div>
          <el-input
            v-model="form.response_body_str"
            type="textarea"
            :rows="5"
            placeholder='{"code": 0, "data": {}, "message": "success"}'
            :class="{ 'json-error': jsonErrors.response_body }"
          />
          <div v-if="jsonErrors.response_body" class="json-field__err">JSON 格式错误（支持 object/array/字符串）</div>
        </div>
      </el-form-item>

      <div class="match-panel">
        <div class="match-panel__head">
          <span class="match-panel__title">高级匹配规则</span>
          <el-tag size="small" type="info" effect="plain">同路径多场景时填写</el-tag>
          <el-button link type="primary" class="match-panel__docs" @click="openMockDocs">完整示例 → 帮助手册</el-button>
        </div>
        <ol class="match-panel__steps">
          <li>同路径多场景：列表点<strong>复制为新场景</strong>（或新建多条）；方法+路径相同</li>
          <li><strong>名称建议不同</strong>，好辨认；系统靠下方匹配规则分流，不靠名称</li>
          <li>每条填不同匹配规则 + 响应 Body；可留一条 <code>{}</code> 作兜底</li>
        </ol>
        <div class="match-panel__example">
          <div class="match-panel__example-title">快捷填入本条规则（路径建议 <code>/api/order</code>，方法 <code>POST</code>）</div>
          <div class="match-panel__actions">
            <el-button size="small" @click="applyScene('pending')">待支付 type=1</el-button>
            <el-button size="small" @click="applyScene('paid')">已支付 type=2</el-button>
            <el-button size="small" @click="applyScene('default')">默认兜底 {}</el-button>
          </div>
          <div class="match-panel__hint">
            调用 <code>?type=1</code> + Body <code>status:pending</code> → 待支付；
            <code>?type=2</code> → 已支付；其它 → 兜底。
          </div>
        </div>
        <div class="json-field">
          <div class="json-field__bar">
            <span class="json-field__label">match_rules（header / query / body）</span>
            <el-button size="small" text @click="formatJson('match_rules')">格式化</el-button>
          </div>
          <el-input
            v-model="form.match_rules_str"
            type="textarea"
            :rows="4"
            placeholder='{"query": {"type": "1"}, "body": {"status": "pending"}}'
            :class="{ 'json-error': jsonErrors.match_rules }"
          />
          <div v-if="jsonErrors.match_rules" class="json-field__err">JSON 格式错误</div>
        </div>
      </div>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="aiDialogVisible" title="AI 生成 Mock 响应体" width="520px" append-to-body destroy-on-close>
    <el-form label-width="90px">
      <el-form-item label="业务描述">
        <el-input
          v-model="aiDescription"
          type="textarea"
          :rows="4"
          placeholder="例如：返回用户列表，含 id、name、mobile；或登录成功返回 token 与用户信息"
        />
      </el-form-item>
      <div class="ai-hint">
        将结合当前 Mock 的方法、路径、状态码生成 JSON 响应体；需在「AI 模型配置」中绑定场景「Mock 响应生成」或使用默认模型。
      </div>
    </el-form>
    <template #footer>
      <el-button @click="aiDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="aiGenerating" @click="handleAiGenerate">生成并填入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { httpMockApi } from '@/api/modules/http'
import { formatJsonText } from '@/utils/jsonFormat.js'

const props = defineProps({
  modelValue: Boolean,
  data: { type: Object, default: null },
  /** create | edit | copy */
  mode: { type: String, default: 'create' },
  projectId: { type: Number, required: true }
})
const emit = defineEmits(['update:modelValue', 'success'])
const router = useRouter()

const methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const formRef = ref(null)
const submitting = ref(false)
const aiDialogVisible = ref(false)
const aiDescription = ref('')
const aiGenerating = ref(false)

const isEdit = computed(() => props.mode === 'edit')
const dialogTitle = computed(() => {
  if (props.mode === 'edit') return '编辑 Mock 接口'
  if (props.mode === 'copy') return '复制为新场景'
  return '新建 Mock 接口'
})

const SCENE_PRESETS = {
  pending: {
    name: '订单-待支付',
    method: 'POST',
    path: '/api/order',
    match_rules: { query: { type: '1' }, body: { status: 'pending' } },
    response_body: { code: 0, scene: 'pending', amount: 99 },
  },
  paid: {
    name: '订单-已支付',
    method: 'POST',
    path: '/api/order',
    match_rules: { query: { type: '2' } },
    response_body: { code: 0, scene: 'paid', amount: 199 },
  },
  default: {
    name: '订单-默认',
    method: 'POST',
    path: '/api/order',
    match_rules: {},
    response_body: { code: 0, scene: 'default' },
  },
}

const defaultForm = () => ({
  name: '',
  method: 'GET',
  path: '',
  response_status: 200,
  response_delay: 0,
  is_enabled: true,
  response_headers_str: '{}',
  response_body_str: '{}',
  match_rules_str: '{}'
})

const form = reactive(defaultForm())
const jsonErrors = reactive({ response_headers: false, response_body: false, match_rules: false })

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  method: [{ required: true, message: '请选择请求方法', trigger: 'change' }],
  path: [{ required: true, message: '请输入匹配路径', trigger: 'blur' }],
  response_status: [{ required: true, message: '请输入状态码', trigger: 'blur' }]
}

const fillFormFromData = (val, { asCopy = false } = {}) => {
  const baseName = (val.name || '').trim() || 'Mock'
  form.name = asCopy
    ? (baseName.endsWith('-场景副本') ? baseName : `${baseName}-场景副本`).slice(0, 100)
    : val.name
  form.method = val.method || 'GET'
  form.path = val.path || ''
  form.response_status = val.response_status ?? 200
  form.response_delay = val.response_delay ?? 0
  form.is_enabled = val.is_enabled !== false
  form.response_headers_str = JSON.stringify(val.response_headers || {}, null, 2)
  form.match_rules_str = JSON.stringify(val.match_rules || {}, null, 2)
  try {
    form.response_body_str = typeof val.response_body === 'string'
      ? val.response_body
      : JSON.stringify(val.response_body ?? {}, null, 2)
  } catch {
    form.response_body_str = String(val.response_body || '{}')
  }
}

watch(
  () => [props.data, props.mode, props.modelValue],
  () => {
    if (!props.modelValue) return
    if (props.data && (props.mode === 'edit' || props.mode === 'copy')) {
      fillFormFromData(props.data, { asCopy: props.mode === 'copy' })
    } else if (props.mode === 'create') {
      Object.assign(form, defaultForm())
    }
  },
  { immediate: true }
)

const openMockDocs = () => {
  const route = router.resolve({ path: '/docs', query: { doc: 'api-mock' } })
  window.open(route.href, '_blank')
}

const applyScene = (key) => {
  const preset = SCENE_PRESETS[key]
  if (!preset) return
  if (!form.name?.trim()) form.name = preset.name
  form.method = preset.method
  if (!form.path?.trim() || form.path === '/api/users') form.path = preset.path
  form.match_rules_str = JSON.stringify(preset.match_rules, null, 2)
  form.response_body_str = JSON.stringify(preset.response_body, null, 2)
  jsonErrors.match_rules = false
  jsonErrors.response_body = false
  ElMessage.success(`已填入「${preset.name}」示例，保存后再新建下一条场景`)
}

const formatJson = (field) => {
  const strKey = field + '_str'
  const result = formatJsonText(form[strKey])
  if (!result.ok) {
    jsonErrors[field] = true
    ElMessage.error(result.error)
    return
  }
  form[strKey] = result.text
  jsonErrors[field] = false
}

const parseJsonField = (str, fieldName) => {
  try {
    jsonErrors[fieldName] = false
    return JSON.parse(str)
  } catch {
    jsonErrors[fieldName] = true
    return null
  }
}

const resetForm = () => {
  Object.assign(form, defaultForm())
  Object.assign(jsonErrors, { response_headers: false, response_body: false, match_rules: false })
  aiDescription.value = ''
}

const openAiDialog = () => {
  if (!form.path?.trim()) {
    ElMessage.warning('请先填写匹配路径')
    return
  }
  aiDescription.value = form.name ? `Mock 名称：${form.name}` : ''
  aiDialogVisible.value = true
}

const handleAiGenerate = async () => {
  if (!form.path?.trim()) {
    ElMessage.warning('请先填写匹配路径')
    return
  }
  aiGenerating.value = true
  try {
    const res = await httpMockApi.aiGenerate({
      method: form.method,
      path: form.path,
      name: form.name,
      description: aiDescription.value,
      response_status: form.response_status,
      project_id: props.projectId,
    })
    const data = res.data || {}
    form.response_body_str = JSON.stringify(data.response_body ?? {}, null, 2)
    if (data.response_status) {
      form.response_status = data.response_status
    }
    jsonErrors.response_body = false
    aiDialogVisible.value = false
    ElMessage.success('AI 已生成响应体')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || err.message || 'AI 生成失败')
  } finally {
    aiGenerating.value = false
  }
}

const handleSubmit = async () => {
  await formRef.value?.validate()

  const response_headers = parseJsonField(form.response_headers_str, 'response_headers')
  const match_rules = parseJsonField(form.match_rules_str, 'match_rules')
  let response_body
  try {
    response_body = JSON.parse(form.response_body_str)
    jsonErrors.response_body = false
  } catch {
    response_body = form.response_body_str
    jsonErrors.response_body = false
  }

  if (jsonErrors.response_headers || jsonErrors.match_rules) {
    ElMessage.error('请修正 JSON 格式错误后再保存')
    return
  }

  submitting.value = true
  try {
    const payload = {
      name: form.name,
      method: form.method,
      path: form.path,
      response_status: form.response_status,
      response_delay: form.response_delay,
      is_enabled: form.is_enabled,
      response_headers: response_headers || {},
      response_body: response_body,
      match_rules: match_rules || {}
    }
    if (isEdit.value && props.data) {
      await httpMockApi.update(props.data.id, payload)
      ElMessage.success('更新成功')
    } else {
      await httpMockApi.create({ ...payload, project_id: props.projectId })
      ElMessage.success(props.mode === 'copy' ? '新场景已创建' : '创建成功')
    }
    emit('update:modelValue', false)
    emit('success')
  } catch (err) {
    ElMessage.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.mock-dialog__title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.mock-tip {
  margin: 0 0 16px;
  padding: 10px 12px;
  border-radius: 8px;
  background: linear-gradient(135deg, #f0f7ff 0%, #f7fafc 100%);
  border: 1px solid #e4eef8;
  line-height: 1.55;
  font-size: 12px;
  color: #606266;
}
.mock-tip__main {
  color: #303133;
}
.mock-tip__sub {
  margin-top: 4px;
}
.mock-tip code,
.match-panel code {
  padding: 0 4px;
  border-radius: 3px;
  background: #eef2f7;
  font-size: 11px;
}
.mock-form :deep(.el-form-item) {
  margin-bottom: 14px;
}
.json-field {
  width: 100%;
}
.json-field__bar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.json-field__label {
  margin-right: auto;
  font-size: 12px;
  color: #909399;
}
.json-field__err {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
}
.match-panel {
  margin-top: 4px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  background: #fafbfc;
}
.match-panel__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.match-panel__title {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}
.match-panel__docs {
  margin-left: auto;
}
.match-panel__steps {
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}
.match-panel__example {
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px dashed #dcdfe6;
}
.match-panel__example-title {
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}
.match-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}
.match-panel__hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
.ai-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
.json-error :deep(.el-textarea__inner) {
  border-color: #f56c6c;
}
</style>
