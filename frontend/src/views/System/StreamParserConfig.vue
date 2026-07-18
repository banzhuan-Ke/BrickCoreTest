<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>SSE 解析配置</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="用途说明"
        description="在此维护 SSE 流式接口的解析方案（内置解析器 + 规则/选项）。问答准确性评测「被测 API」与压测「流式阶段」均可引用此处配置，无需改代码。"
        style="margin-bottom: 16px;"
      />
      <div class="toolbar">
        <el-button v-if="canEdit" type="primary" :icon="Plus" @click="openForm()">新增配置</el-button>
        <el-button :icon="Refresh" @click="loadList">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="parser_display_name" label="解析器类型" width="140" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_builtin" type="info" size="small">内置</el-tag>
            <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
              {{ row.is_enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="70" />
        <el-table-column prop="update_by" label="更新人" width="100" show-overflow-tooltip />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">编辑</el-button>
            <el-button
              v-if="canEdit && !row.is_builtin"
              link
              type="danger"
              size="small"
              @click="removeRow(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-drawer v-model="formVisible" :title="form.id ? '编辑解析配置' : '新增解析配置'" size="720px" destroy-on-close>
        <el-form label-width="110px" class="config-form">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" placeholder="如：问答接口 SSE v1" />
          </el-form-item>
          <el-form-item label="说明文档">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="4"
              placeholder="Markdown：适用接口、字段说明、鉴权注意事项等"
            />
          </el-form-item>
          <el-form-item label="解析器类型" required>
            <el-select v-model="form.parser_id" style="width: 100%" @change="onParserTypeChange">
              <el-option
                v-for="p in builtinParsers"
                :key="p.parser_id"
                :label="p.display_name"
                :value="p.parser_id"
              >
                <span>{{ p.display_name }}</span>
                <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px">
                  {{ p.parser_id }}
                </span>
              </el-option>
            </el-select>
            <div class="field-hint">
              「问答流式 v1」适用于问答接口标准协议；「规则配置」可自定义阶段匹配；「仅总耗时」不做内容解析。
            </div>
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.is_enabled" />
          </el-form-item>
          <el-form-item label="排序">
            <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
          </el-form-item>
          <el-form-item v-if="form.parser_id === 'rule_based'" label="阶段规则">
            <StreamRuleBuilder v-model="form.parser_options.rules" />
          </el-form-item>
          <el-form-item label="成功判定">
            <el-select v-model="successPhaseKey" style="width: 160px" @change="onSuccessRuleChange">
              <el-option label="阶段出现即成功" value="phase_exists" />
              <el-option label="HTTP 2xx 即成功" value="status_ok" />
            </el-select>
            <el-select
              v-if="successPhaseKey === 'phase_exists'"
              v-model="form.success_rule.phase"
              style="width: 180px; margin-left: 12px"
              placeholder="选择阶段"
            >
              <el-option
                v-for="s in currentPhaseSchema"
                :key="s.key"
                :label="s.label || s.key"
                :value="s.key"
              />
            </el-select>
          </el-form-item>

          <el-divider content-position="left">解析测试</el-divider>
          <el-form-item label="SSE 原始行">
            <el-input
              v-model="testLinesText"
              type="textarea"
              :rows="8"
              placeholder="粘贴 data: {...} 格式的 SSE 行，每行一条"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="success" :loading="testing" @click="runTest">测试解析</el-button>
          </el-form-item>
          <el-form-item v-if="testResult" label="解析结果">
            <pre class="test-result">{{ testResult }}</pre>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="formVisible = false">取消</el-button>
          <el-button v-if="canEdit" type="primary" :loading="saving" @click="saveForm">保存</el-button>
        </template>
      </el-drawer>
    </template>
  </ConfigShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import ConfigShell from '@/components/ConfigShell.vue'
import StreamRuleBuilder from '@/components/perf/StreamRuleBuilder.vue'
import { streamParserConfigApi } from '@/api/modules/sys.js'
import { UserStore } from '@/stores/module/UserStore'

defineProps({
  embedded: { type: Boolean, default: false }
})

const uStore = UserStore()
const canEdit = computed(() => uStore.hasPermission('ai_config:edit'))

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const rows = ref([])
const builtinParsers = ref([])
const formVisible = ref(false)
const testLinesText = ref('')
const testResult = ref('')
const successPhaseKey = ref('phase_exists')

const form = reactive({
  id: null,
  name: '',
  description: '',
  parser_id: 'qa_sse_v1',
  parser_options: { rules: {} },
  success_rule: { type: 'phase_exists', phase: 'first_char' },
  is_enabled: true,
  sort_order: 0
})

const currentPhaseSchema = computed(() => {
  const p = builtinParsers.value.find((x) => x.parser_id === form.parser_id)
  return p?.phase_schema || []
})

function resetForm() {
  form.id = null
  form.name = ''
  form.description = ''
  form.parser_id = 'qa_sse_v1'
  form.parser_options = { rules: {} }
  form.success_rule = { type: 'phase_exists', phase: 'first_char' }
  form.is_enabled = true
  form.sort_order = 0
  testLinesText.value = ''
  testResult.value = ''
  successPhaseKey.value = 'phase_exists'
}

function openForm(row) {
  resetForm()
  if (row) {
    form.id = row.id
    form.name = row.name
    form.description = row.description || ''
    form.parser_id = row.parser_id
    form.parser_options = row.parser_options?.rules
      ? { rules: JSON.parse(JSON.stringify(row.parser_options.rules)) }
      : { rules: {} }
    form.success_rule = row.success_rule?.type
      ? { ...row.success_rule }
      : { type: 'phase_exists', phase: 'first_char' }
    form.is_enabled = row.is_enabled !== false
    form.sort_order = row.sort_order || 0
    successPhaseKey.value = form.success_rule.type === 'status_ok' ? 'status_ok' : 'phase_exists'
  }
  formVisible.value = true
}

function onParserTypeChange() {
  const p = builtinParsers.value.find((x) => x.parser_id === form.parser_id)
  if (p?.default_success_rule) {
    form.success_rule = { ...p.default_success_rule }
    successPhaseKey.value = form.success_rule.type === 'status_ok' ? 'status_ok' : 'phase_exists'
  }
  if (form.parser_id === 'rule_based' && !form.parser_options?.rules?.phases?.length) {
    const preset = p?.default_options?.rules
    if (preset) {
      form.parser_options = { rules: JSON.parse(JSON.stringify(preset)) }
    }
  }
}

function onSuccessRuleChange() {
  if (successPhaseKey.value === 'status_ok') {
    form.success_rule = { type: 'status_ok' }
  } else {
    form.success_rule = {
      type: 'phase_exists',
      phase: form.success_rule?.phase || 'first_char'
    }
  }
}

async function loadBuiltinParsers() {
  const res = await streamParserConfigApi.getBuiltinParsers()
  builtinParsers.value = res.data?.data || res.data || []
}

async function loadList() {
  loading.value = true
  try {
    await loadBuiltinParsers()
    const res = await streamParserConfigApi.getList()
    rows.value = res.data?.data || res.data || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function buildPayload() {
  const payload = {
    name: (form.name || '').trim(),
    description: form.description || '',
    parser_id: form.parser_id,
    parser_options: form.parser_id === 'rule_based' ? { rules: form.parser_options?.rules || {} } : {},
    success_rule: form.success_rule || {},
    is_enabled: form.is_enabled,
    sort_order: form.sort_order || 0
  }
  if (!payload.name) {
    throw new Error('请填写名称')
  }
  return payload
}

async function saveForm() {
  if (!canEdit.value) return
  let payload
  try {
    payload = buildPayload()
  } catch (e) {
    ElMessage.warning(e.message)
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await streamParserConfigApi.update(form.id, payload)
      ElMessage.success('已保存')
    } else {
      await streamParserConfigApi.create(payload)
      ElMessage.success('已创建')
    }
    formVisible.value = false
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function removeRow(row) {
  if (!canEdit.value || row.is_builtin) return
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」？`, '删除确认', { type: 'warning' })
    await streamParserConfigApi.delete(row.id)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

async function runTest() {
  const lines = (testLinesText.value || '').split(/\r?\n/).filter((l) => l.trim())
  if (!lines.length) {
    ElMessage.warning('请粘贴 SSE 原始行')
    return
  }
  testing.value = true
  testResult.value = ''
  try {
    const payload = buildPayload()
    const res = await streamParserConfigApi.test({
      parser_id: payload.parser_id,
      lines,
      parser_options: payload.parser_options,
      success_rule: payload.success_rule
    })
    const data = res.data?.data || res.data
    testResult.value = JSON.stringify(data, null, 2)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '测试失败')
  } finally {
    testing.value = false
  }
}

onMounted(loadList)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.test-result {
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
