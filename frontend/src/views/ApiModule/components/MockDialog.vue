<template>
  <el-dialog
    :model-value="modelValue"
    width="680px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
    @closed="resetForm"
  >
    <template #header>
      <div style="display:flex;align-items:center;gap:8px">
        <span>{{ isEdit ? '编辑 Mock 接口' : '新建 Mock 接口' }}</span>
        <el-tooltip placement="top" :show-after="300">
          <template #content>
            <div style="max-width:360px;line-height:1.6">
              <div><b>Mock 使用说明：</b></div>
              <div>1. 保存后，调用地址：{baseUrl}/api-module/mock-call/匹配路径</div>
              <div>2. 支持通过 ?_project_id=xxx 参数缩小匹配范围</div>
              <div>3. 同一路径可配置多个 Mock，通过【高级匹配规则】区分不同场景</div>
              <div>4. 状态码：HTTP 响应状态码；延迟：模拟网络延迟(ms)</div>
            </div>
          </template>
          <el-icon style="color:#909399;cursor:pointer"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
    </template>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="Mock 接口名称" maxlength="100" show-word-limit />
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="请求方法" prop="method">
            <el-select v-model="form.method" style="width:100%">
              <el-option v-for="m in methods" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="16">
          <el-form-item label="匹配路径" prop="path">
            <el-input v-model="form.path" placeholder="/api/users" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="响应状态码" prop="response_status">
            <el-input v-model.number="form.response_status" type="number" :min="100" :max="599" placeholder="200" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="延迟(ms)" prop="response_delay">
            <el-input v-model.number="form.response_delay" type="number" :min="0" :max="60000" placeholder="0" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="启用">
            <el-switch v-model="form.is_enabled" active-text="启用" inactive-text="禁用" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="响应 Headers">
        <div style="width:100%">
          <div style="display:flex; justify-content:flex-end; margin-bottom:4px">
            <el-button size="small" text @click="formatJson('response_headers')">格式化</el-button>
          </div>
          <el-input
            v-model="form.response_headers_str"
            type="textarea"
            :rows="3"
            placeholder='{"Content-Type": "application/json"}'
            :class="{ 'json-error': jsonErrors.response_headers }"
          />
          <div v-if="jsonErrors.response_headers" style="color:#f56c6c;font-size:12px;margin-top:4px">JSON 格式错误</div>
        </div>
      </el-form-item>

      <el-form-item label="响应 Body" prop="response_body_str">
        <div style="width:100%">
          <div style="display:flex; justify-content:flex-end; margin-bottom:4px">
            <el-button size="small" text @click="formatJson('response_body')">格式化</el-button>
          </div>
          <el-input
            v-model="form.response_body_str"
            type="textarea"
            :rows="6"
            placeholder='{"code": 0, "data": {}, "message": "success"}'
            :class="{ 'json-error': jsonErrors.response_body }"
          />
          <div v-if="jsonErrors.response_body" style="color:#f56c6c;font-size:12px;margin-top:4px">JSON 格式错误（支持 object/array/字符串）</div>
        </div>
      </el-form-item>

      <el-collapse style="margin-bottom:0">
        <el-collapse-item title="高级匹配规则（match_rules）" name="match">
          <div style="font-size:12px;color:#909399;margin-bottom:10px;line-height:1.8">
            <div>用于同一路径配置多个 Mock，按请求条件精确匹配返回不同响应。</div>
            <div>支持匹配维度：<code>header</code>（请求头）、<code>query</code>（URL 参数）、<code>body</code>（请求体）。</div>
            <div style="margin-top:6px;padding:8px 12px;background:#f5f7fa;border-radius:4px;color:#606266">
              <div style="margin-bottom:4px"><b>📝 示例：同一路径 /api/order，按订单类型返回不同数据</b></div>
              <pre style="margin:0;font-size:11px;white-space:pre-wrap;word-break:break-all">{
  "query": {"type": "1"},
  "body": {"status": "pending"}
}</pre>
              <div style="margin-top:4px">表示：当请求 <code>POST /api-module/mock-call/api/order?type=1</code> 且 Body 中包含 <code>status=pending</code> 时，才会命中此 Mock。</div>
            </div>
          </div>
          <div style="display:flex; justify-content:flex-end; margin-bottom:4px">
            <el-button size="small" text @click="formatJson('match_rules')">格式化</el-button>
          </div>
          <el-input
            v-model="form.match_rules_str"
            type="textarea"
            :rows="4"
            placeholder='{"header": {"Authorization": "Bearer xxx"}, "query": {"type": "1"}}'
            :class="{ 'json-error': jsonErrors.match_rules }"
          />
          <div v-if="jsonErrors.match_rules" style="color:#f56c6c;font-size:12px;margin-top:4px">JSON 格式错误</div>
        </el-collapse-item>
      </el-collapse>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { httpMockApi } from '@/api/modules/http'
import { formatJsonText } from '@/utils/jsonFormat.js'

const props = defineProps({
  modelValue: Boolean,
  data: { type: Object, default: null },
  projectId: { type: Number, required: true }
})
const emit = defineEmits(['update:modelValue', 'success'])

const methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const formRef = ref(null)
const submitting = ref(false)
const isEdit = ref(false)

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

watch(() => props.data, (val) => {
  if (val) {
    isEdit.value = true
    form.name = val.name
    form.method = val.method
    form.path = val.path
    form.response_status = val.response_status
    form.response_delay = val.response_delay
    form.is_enabled = val.is_enabled
    form.response_headers_str = JSON.stringify(val.response_headers || {}, null, 2)
    form.match_rules_str = JSON.stringify(val.match_rules || {}, null, 2)
    // response_body 支持任意类型
    try {
      form.response_body_str = typeof val.response_body === 'string'
        ? val.response_body
        : JSON.stringify(val.response_body, null, 2)
    } catch {
      form.response_body_str = String(val.response_body || '{}')
    }
  } else {
    isEdit.value = false
    Object.assign(form, defaultForm())
  }
}, { immediate: true })

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
  isEdit.value = false
}

const handleSubmit = async () => {
  await formRef.value?.validate()

  const response_headers = parseJsonField(form.response_headers_str, 'response_headers')
  const match_rules = parseJsonField(form.match_rules_str, 'match_rules')
  // response_body 允许任意 JSON 或字符串
  let response_body
  try {
    response_body = JSON.parse(form.response_body_str)
    jsonErrors.response_body = false
  } catch {
    // 不是合法 JSON，作为字符串存储
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
      ElMessage.success('创建成功')
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
.json-error :deep(.el-textarea__inner) {
  border-color: #f56c6c;
}
</style>
