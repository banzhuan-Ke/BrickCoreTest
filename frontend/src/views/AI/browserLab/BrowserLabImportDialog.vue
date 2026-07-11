<template>
  <el-dialog
    v-model="visible"
    title="导入 Web 自动化用例"
    width="860px"
    destroy-on-close
    @closed="handleClosed"
  >
    <div v-loading="loading">
      <el-alert type="info" :closable="false" show-icon class="tip">
        将 Browser Lab 探索步骤转为 Playwright 步骤。定位器为启发式生成，导入后请核对并微调。
      </el-alert>
      <el-form label-width="100px" class="form">
        <el-form-item label="用例名称" required>
          <el-input v-model="form.case_name" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="用例描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="4000" show-word-limit />
        </el-form-item>
        <el-form-item label="打开浏览器">
          <el-switch v-model="form.include_open_browser" @change="loadPreview" />
        </el-form-item>
      </el-form>
      <div v-if="warnings.length" class="warnings">
        <el-text type="warning">规范化提示：{{ warnings.join('；') }}</el-text>
      </div>
      <el-table :data="steps" size="small" max-height="360" border>
        <el-table-column type="index" width="50" />
        <el-table-column prop="desc" label="操作名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="method" label="method" width="130" />
        <el-table-column label="关键参数" min-width="220">
          <template #default="{ row }">
            <span class="param-preview">{{ paramPreview(row) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !steps.length" description="无可导入步骤" />
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!steps.length" @click="submit">
        导入并打开编辑
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { browserLabApi } from '@/api/modules/ai.js'

const props = defineProps({
  taskId: { type: [Number, String], required: true },
  projectId: { type: [Number, String], required: true },
  defaultCaseName: { type: String, default: '' },
  taskText: { type: String, default: '' },
})

const visible = defineModel({ type: Boolean, default: false })
const router = useRouter()

const loading = ref(false)
const submitting = ref(false)
const steps = ref([])
const warnings = ref([])
const form = reactive({
  case_name: '',
  description: '',
  include_open_browser: true,
})

watch(visible, (v) => {
  if (v) {
    form.case_name = props.defaultCaseName || `BrowserLab-${props.taskId}`
    form.description = props.taskText ? `来源：智能浏览器 #${props.taskId}\n${props.taskText}` : ''
    loadPreview()
  }
})

async function loadPreview() {
  if (!props.taskId || !props.projectId) return
  loading.value = true
  try {
    const res = await browserLabApi.previewUiSteps(props.taskId, props.projectId, {
      include_open_browser: form.include_open_browser,
    })
    const data = res.data?.data || res.data
    steps.value = data?.steps || []
    warnings.value = data?.warnings || []
    if (data?.default_case_name && !props.defaultCaseName) {
      form.case_name = data.default_case_name
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '预览步骤失败')
    steps.value = []
  } finally {
    loading.value = false
  }
}

function paramPreview(row) {
  const p = row.params || {}
  if (p.url) return p.url
  if (p.locator) return p.locator
  if (p.value != null && p.value !== '') return String(p.value)
  if (p.template) return p.template
  if (p.script) return String(p.script).slice(0, 80)
  return JSON.stringify(p).slice(0, 80)
}

async function submit() {
  if (!form.case_name.trim()) {
    ElMessage.warning('请填写用例名称')
    return
  }
  submitting.value = true
  try {
    const res = await browserLabApi.importUiCase(
      props.taskId,
      {
        case_name: form.case_name.trim(),
        description: form.description.trim() || undefined,
        include_open_browser: form.include_open_browser,
        steps: steps.value,
      },
      props.projectId,
    )
    const data = res.data?.data || res.data
    ElMessage.success(res.data?.message || '导入成功')
    visible.value = false
    if (data?.case_id) {
      router.push({ name: 'editCase', params: { id: data.case_id } })
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    submitting.value = false
  }
}

function handleClosed() {
  steps.value = []
  warnings.value = []
}
</script>

<style scoped>
.tip {
  margin-bottom: 12px;
}
.form {
  margin-bottom: 8px;
}
.warnings {
  margin-bottom: 8px;
}
.param-preview {
  font-family: monospace;
  font-size: 12px;
}
</style>
