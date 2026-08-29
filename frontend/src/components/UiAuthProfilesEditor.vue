<template>
  <div class="ui-auth-profiles">
    <div class="ui-auth-profiles__toolbar">
      <el-button type="primary" size="small" @click="openCreate">新建登录态</el-button>
      <span class="ui-auth-profiles__hint">
        每个站点一条配置（类似 Token 授权）；启用项会合并注入，换执行机无需本机路径。
      </span>
    </div>

    <el-table v-if="modelValue.length" :data="modelValue" size="small" border class="ui-auth-profiles__table">
      <el-table-column label="启用" width="70" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled !== false" @change="(v) => patchRow(row, { enabled: v })" />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
      <el-table-column label="站点提示" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.host_hint || '—' }}</template>
      </el-table-column>
      <el-table-column label="摘要" min-width="220">
        <template #default="{ row }">
          <span class="muted">{{ formatSummary(row.storage_state) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ $index, row }">
          <el-button type="primary" link size="small" @click="openEdit(row, $index)">编辑/导入</el-button>
          <el-button type="success" link size="small" @click="exportRow(row)">导出</el-button>
          <el-button type="danger" link size="small" @click="removeAt($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="尚未添加站点登录态，可新建或导入导出的 json" :image-size="64" />

    <el-collapse class="ui-auth-profiles__legacy">
      <el-collapse-item title="高级：本机路径兼容（不推荐）" name="legacy">
        <el-input v-model="legacyPathProxy" placeholder="执行机本机路径，换机器会失效" clearable />
        <div class="field-hint">仅当尚未导入 JSON、仍依赖某台执行机本地文件时使用。优先上方「导入」。</div>
      </el-collapse-item>
    </el-collapse>

    <el-dialog
      v-model="dialogVisible"
      :title="editingIndex == null ? '新建登录态' : '编辑登录态'"
      width="860px"
      destroy-on-close
      append-to-body
      @closed="resetDialog"
    >
      <el-form label-width="96px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：知识库 / 管理后台" maxlength="80" show-word-limit />
        </el-form-item>
        <el-form-item label="站点提示">
          <el-input v-model="form.host_hint" placeholder="可选，如 kbs.example.com（仅备注，不参与匹配）" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" placeholder="可选" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>

        <el-form-item label="导入导出">
          <div class="ui-auth-profiles__io">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".json,application/json"
              :on-change="onImportFile"
            >
              <el-button type="primary" plain>导入 JSON 文件</el-button>
            </el-upload>
            <el-button @click="pasteImport">粘贴 JSON</el-button>
            <el-button @click="exportForm">导出当前</el-button>
          </div>
          <div v-if="summaryText" class="ui-auth-profiles__summary">
            解析摘要：{{ summaryText }}
          </div>
        </el-form-item>

        <el-tabs v-model="editTab">
          <el-tab-pane label="Cookie" name="cookies">
            <div
              v-for="(row, idx) in form.cookies"
              :key="'ck-' + idx"
              class="auth-edit-row auth-edit-row--cookie"
            >
              <el-input v-model="row.name" placeholder="name" />
              <el-input v-model="row.value" placeholder="value" />
              <el-input v-model="row.domain" placeholder="domain" />
              <el-input v-model="row.path" placeholder="path" />
              <el-input v-model="row.expires" placeholder="expires(Unix)" />
              <el-button type="danger" link :disabled="form.cookies.length <= 1" @click="form.cookies.splice(idx, 1)">删</el-button>
            </div>
            <el-button type="primary" link @click="form.cookies.push(emptyCookie())">添加 Cookie</el-button>
          </el-tab-pane>
          <el-tab-pane label="LocalStorage" name="ls">
            <div
              v-for="(row, idx) in form.localRows"
              :key="'ls-' + idx"
              class="auth-edit-row"
            >
              <el-input v-model="row.origin" placeholder="origin，如 https://app.example.com" />
              <el-input v-model="row.name" placeholder="键名" />
              <el-input v-model="row.value" placeholder="值" />
              <el-button type="danger" link :disabled="form.localRows.length <= 1" @click="form.localRows.splice(idx, 1)">删</el-button>
            </div>
            <el-button type="primary" link @click="form.localRows.push(emptyKv())">添加一行</el-button>
          </el-tab-pane>
          <el-tab-pane label="SessionStorage" name="ss">
            <div
              v-for="(row, idx) in form.sessionRows"
              :key="'ss-' + idx"
              class="auth-edit-row"
            >
              <el-input v-model="row.origin" placeholder="origin" />
              <el-input v-model="row.name" placeholder="键名" />
              <el-input v-model="row.value" placeholder="值（可改关键字段）" />
              <el-button type="danger" link :disabled="form.sessionRows.length <= 1" @click="form.sessionRows.splice(idx, 1)">删</el-button>
            </div>
            <el-button type="primary" link @click="form.sessionRows.push(emptyKv())">添加一行</el-button>
          </el-tab-pane>
          <el-tab-pane label="原始 JSON" name="raw">
            <el-input v-model="rawJson" type="textarea" :rows="12" placeholder="可直接改 JSON，失焦后回填表格" @blur="applyRawJson" />
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDialog">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  buildStorageStateFromEdit,
  downloadJsonFile,
  emptyStorageState,
  flattenStorageStateForEdit,
  parseStorageStateText,
  readJsonFile,
  summarizeStorageState,
} from '@/utils/uiStorageState.js'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  legacyPath: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:modelValue', 'update:legacyPath'])

const legacyPathProxy = computed({
  get: () => props.legacyPath,
  set: (v) => emit('update:legacyPath', String(v || '')),
})

const dialogVisible = ref(false)
const editingIndex = ref(null)
const editTab = ref('cookies')
const rawJson = ref('')
const form = reactive({
  name: '',
  host_hint: '',
  note: '',
  enabled: true,
  cookies: [],
  localRows: [],
  sessionRows: [],
})

function emptyCookie() {
  return { name: '', value: '', domain: '', path: '/', url: '', expires: '', _extra: {} }
}
function emptyKv() {
  return { origin: '', name: '', value: '' }
}

function newId() {
  return `p-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function formatSummary(doc) {
  const s = summarizeStorageState(doc)
  return `Cookie ${s.cookies} · LS ${s.localStorageKeys} · SS ${s.sessionStorageKeys}`
}

const summaryText = computed(() => {
  const doc = buildStorageStateFromEdit({
    cookies: form.cookies,
    localRows: form.localRows,
    sessionRows: form.sessionRows,
  })
  const s = summarizeStorageState(doc)
  const domains = s.cookieDomains.slice(0, 3).join(', ')
  return `Cookie ${s.cookies}${domains ? `（${domains}）` : ''}；LocalStorage 键 ${s.localStorageKeys}；SessionStorage 键 ${s.sessionStorageKeys}${s.hasSessionStorageExtension ? '（含扩展字段）' : ''}`
})

function applyDocToForm(doc) {
  const flat = flattenStorageStateForEdit(doc || emptyStorageState())
  form.cookies = flat.cookies
  form.localRows = flat.localRows
  form.sessionRows = flat.sessionRows
  rawJson.value = JSON.stringify(doc || emptyStorageState(), null, 2)
}

function resetDialog() {
  editingIndex.value = null
  editTab.value = 'cookies'
  form.name = ''
  form.host_hint = ''
  form.note = ''
  form.enabled = true
  applyDocToForm(emptyStorageState())
}

function openCreate() {
  resetDialog()
  form.name = `站点${(props.modelValue?.length || 0) + 1}`
  dialogVisible.value = true
}

function openEdit(row, index) {
  resetDialog()
  editingIndex.value = index
  form.name = row.name || ''
  form.host_hint = row.host_hint || ''
  form.note = row.note || ''
  form.enabled = row.enabled !== false
  applyDocToForm(row.storage_state || emptyStorageState())
  dialogVisible.value = true
}

function patchRow(row, patch) {
  const list = (props.modelValue || []).map((r) => (r === row ? { ...r, ...patch } : r))
  emit('update:modelValue', list)
}

function removeAt(index) {
  const list = [...(props.modelValue || [])]
  list.splice(index, 1)
  emit('update:modelValue', list)
}

function exportRow(row) {
  const name = String(row.name || 'storage_state').replace(/[\\/:*?"<>|]/g, '_')
  downloadJsonFile(`${name}.json`, row.storage_state || emptyStorageState())
}

function exportForm() {
  const doc = buildStorageStateFromEdit({
    cookies: form.cookies,
    localRows: form.localRows,
    sessionRows: form.sessionRows,
  })
  downloadJsonFile(`${form.name || 'storage_state'}.json`, doc)
}

async function onImportFile(uploadFile) {
  try {
    const file = uploadFile?.raw
    const parsed = await readJsonFile(file)
    applyDocToForm(parsed.doc)
    ElMessage.success(`已导入：${formatSummary(parsed.doc)}`)
    editTab.value = parsed.summary.sessionStorageKeys ? 'ss' : 'cookies'
  } catch (e) {
    ElMessage.error(e?.message || '导入失败')
  }
}

async function pasteImport() {
  try {
    const { value } = await ElMessageBox.prompt('粘贴导出的 storage_state JSON', '导入 JSON', {
      inputType: 'textarea',
      confirmButtonText: '解析',
      cancelButtonText: '取消',
    })
    const parsed = parseStorageStateText(value)
    if (!parsed.ok) {
      ElMessage.error(parsed.error)
      return
    }
    applyDocToForm(parsed.doc)
    ElMessage.success(`已解析：${formatSummary(parsed.doc)}`)
  } catch {
    /* cancel */
  }
}

function applyRawJson() {
  const parsed = parseStorageStateText(rawJson.value)
  if (!parsed.ok) {
    ElMessage.warning(parsed.error)
    return
  }
  applyDocToForm(parsed.doc)
}

function saveDialog() {
  const name = String(form.name || '').trim()
  if (!name) {
    ElMessage.error('请填写名称')
    return
  }
  // 原始 JSON 页可能未失焦：确定前先尝试合并
  if (editTab.value === 'raw' && String(rawJson.value || '').trim()) {
    const parsed = parseStorageStateText(rawJson.value)
    if (!parsed.ok) {
      ElMessage.error(parsed.error || '原始 JSON 无效')
      return
    }
    applyDocToForm(parsed.doc)
  }
  const doc = buildStorageStateFromEdit({
    cookies: form.cookies,
    localRows: form.localRows,
    sessionRows: form.sessionRows,
  })
  const entry = {
    id: editingIndex.value != null
      ? (props.modelValue[editingIndex.value]?.id || newId())
      : newId(),
    name,
    enabled: form.enabled !== false,
    host_hint: String(form.host_hint || '').trim(),
    note: String(form.note || '').trim(),
    storage_state: doc,
  }
  const list = [...(props.modelValue || [])]
  if (editingIndex.value == null) {
    list.push(entry)
  } else {
    list.splice(editingIndex.value, 1, entry)
  }
  emit('update:modelValue', list)
  // 有有效登录态数据时再清本机路径，避免空配置挤掉旧路径
  const s = summarizeStorageState(doc)
  if (props.legacyPath && (s.cookies > 0 || s.localStorageKeys > 0 || s.sessionStorageKeys > 0)) {
    emit('update:legacyPath', '')
  }
  dialogVisible.value = false
}

watch(
  () => [form.cookies, form.localRows, form.sessionRows],
  () => {
    if (!dialogVisible.value) return
    const doc = buildStorageStateFromEdit({
      cookies: form.cookies,
      localRows: form.localRows,
      sessionRows: form.sessionRows,
    })
    rawJson.value = JSON.stringify(doc, null, 2)
  },
  { deep: true }
)
</script>

<style scoped lang="scss">
.ui-auth-profiles__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.ui-auth-profiles__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

.ui-auth-profiles__table {
  width: 100%;
  margin-bottom: 8px;
}

.ui-auth-profiles__table :deep(.el-table__header th) {
  background: var(--el-fill-color-lighter);
  font-weight: 600;
}

.ui-auth-profiles :deep(.el-empty) {
  padding: 16px 0;
}

.ui-auth-profiles__legacy {
  margin-top: 8px;
  border: none;
}

.ui-auth-profiles__legacy :deep(.el-collapse-item__header) {
  height: 36px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: transparent;
  border: none;
}

.ui-auth-profiles__legacy :deep(.el-collapse-item__wrap) {
  border: none;
}

.ui-auth-profiles__legacy :deep(.el-collapse-item__content) {
  padding: 0 0 4px;
}

.ui-auth-profiles__io {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.ui-auth-profiles__summary {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.auth-edit-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1.4fr auto;
  gap: 6px;
  margin-bottom: 6px;
  align-items: center;
}

.auth-edit-row--cookie {
  grid-template-columns: 1fr 1.2fr 1fr 0.7fr 0.9fr auto;
}

.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

@media (max-width: 720px) {
  .auth-edit-row,
  .auth-edit-row--cookie {
    grid-template-columns: 1fr;
  }
}
</style>
