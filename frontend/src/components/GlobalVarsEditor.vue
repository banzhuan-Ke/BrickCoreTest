<template>
  <div class="global-vars-editor">
    <div class="toolbar">
      <el-radio-group v-model="mode" size="small" @change="onModeChange">
        <el-radio-button label="table">键值表格</el-radio-button>
        <el-radio-button label="json">JSON 高级</el-radio-button>
      </el-radio-group>
      <div class="toolbar-actions">
        <el-button v-if="mode === 'table'" size="small" type="primary" link icon="Plus" @click="addRow">
          添加变量
        </el-button>
        <el-button size="small" link @click="validateCurrent">校验</el-button>
        <el-button size="small" link @click="triggerImport">导入 JSON</el-button>
        <el-button size="small" link :disabled="!hasVars" @click="exportJson">导出 JSON</el-button>
      </div>
    </div>

    <input ref="fileInputRef" type="file" accept=".json,application/json" class="hidden-file" @change="onFileImport" />

    <div v-show="mode === 'table'" class="table-panel">
      <el-table :data="varList" size="small" border max-height="320" empty-text="暂无变量，点击「添加变量」">
        <el-table-column label="变量名" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-model="varList[$index].key"
              size="small"
              placeholder="如 token、username"
              @blur="syncFromTable"
            />
          </template>
        </el-table-column>
        <el-table-column label="变量值" min-width="220">
          <template #default="{ row, $index }">
            <el-input
              v-model="varList[$index].value"
              size="small"
              :type="row.secret ? 'password' : 'text'"
              :show-password="row.secret"
              placeholder="支持 faker.random_int(min=1,max=99)"
              @blur="syncFromTable"
            />
          </template>
        </el-table-column>
        <el-table-column label="敏感" width="72" align="center">
          <template #default="{ row, $index }">
            <el-switch v-model="varList[$index].secret" size="small" />
          </template>
        </el-table-column>
        <el-table-column width="56" align="center">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" icon="Delete" @click="removeRow($index)" />
          </template>
        </el-table-column>
      </el-table>
      <div class="quick-hints">
        <span class="hint-label">快捷插入值：</span>
        <el-tag
          v-for="h in builtinHints"
          :key="h.key"
          size="small"
          class="hint-tag"
          effect="plain"
          @click="insertBuiltin(h.key)"
        >{{ h.label }}</el-tag>
      </div>
    </div>

    <div v-if="mode === 'json'" class="json-panel">
      <JsonTextarea v-model="jsonText" :rows="jsonRows" placeholder="{}" />
    </div>

    <el-alert
      v-if="lastError"
      :title="lastError"
      type="error"
      show-icon
      :closable="true"
      class="validate-alert"
      @close="lastError = ''"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import JsonTextarea from '@/components/JsonTextarea.vue'
import {
  BUILTIN_VAR_HINTS,
  isSecretKey,
  listToVarsObject,
  validateVarsObject,
  varsObjectToList,
} from '@/utils/globalVars.js'

const props = defineProps({
  modelValue: {
    type: [Object, String],
    default: () => ({}),
  },
  jsonHeight: {
    type: String,
    default: '280px',
  },
})

const emit = defineEmits(['update:modelValue', 'validate'])

const mode = ref('table')
const varList = ref([])
const lastError = ref('')
const fileInputRef = ref(null)
const jsonText = ref('{}')
const syncing = ref(false)

const builtinHints = BUILTIN_VAR_HINTS

const jsonRows = computed(() => {
  const px = parseInt(String(props.jsonHeight).replace(/px$/i, ''), 10)
  return Number.isFinite(px) ? Math.max(8, Math.round(px / 22)) : 12
})

const hasVars = computed(() => {
  const obj = normalizeObject(props.modelValue)
  return Object.keys(obj).length > 0
})

function normalizeObject(val) {
  if (!val) return {}
  if (typeof val === 'string') {
    try {
      const parsed = JSON.parse(val)
      return typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    } catch {
      return {}
    }
  }
  if (typeof val === 'object' && !Array.isArray(val)) return { ...val }
  return {}
}

function stringifyObject(obj) {
  return JSON.stringify(obj ?? {}, null, 2)
}

function parseJsonText() {
  try {
    const parsed = JSON.parse(jsonText.value || '{}')
    if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
      throw new Error('环境变量必须是 JSON 对象（键值对）')
    }
    return parsed
  } catch (err) {
    throw new Error(err.message || 'JSON 格式错误')
  }
}

function loadFromModel(val) {
  syncing.value = true
  const obj = normalizeObject(val)
  varList.value = varsObjectToList(obj)
  if (mode.value !== 'json') {
    jsonText.value = stringifyObject(obj)
  }
  syncing.value = false
}

watch(
  () => props.modelValue,
  (v) => {
    if (syncing.value) return
    loadFromModel(v)
  },
  { immediate: true, deep: true }
)

function emitObject(obj) {
  const check = validateVarsObject(obj)
  if (!check.ok) {
    lastError.value = check.error
    emit('validate', check)
    return false
  }
  lastError.value = ''
  syncing.value = true
  emit('update:modelValue', obj)
  emit('validate', check)
  syncing.value = false
  return true
}

function syncFromTable() {
  if (syncing.value) return
  varList.value.forEach((row) => {
    if (!row.secret && row.key) row.secret = isSecretKey(row.key)
  })
  const obj = listToVarsObject(varList.value)
  jsonText.value = stringifyObject(obj)
  emitObject(obj)
}

function onModeChange(nextMode) {
  lastError.value = ''
  if (nextMode === 'json') {
    jsonText.value = stringifyObject(listToVarsObject(varList.value))
    return
  }
  try {
    const obj = parseJsonText()
    const check = validateVarsObject(obj)
    if (!check.ok) {
      lastError.value = check.error
      mode.value = 'json'
      ElMessage.error(check.error)
      return
    }
    varList.value = varsObjectToList(obj)
    emitObject(obj)
  } catch (err) {
    lastError.value = err.message
    mode.value = 'json'
    ElMessage.error(err.message)
  }
}

function addRow() {
  varList.value.push({ key: '', value: '', secret: false })
}

function removeRow(index) {
  varList.value.splice(index, 1)
  syncFromTable()
}

function insertBuiltin(key) {
  const row = varList.value.find((r) => !r.key?.trim())
  const expr = key === 'random_int' ? 'faker.random_int(min=1000,max=9999)' : `\${{${key}}}`
  if (row) {
    row.key = row.key || key
    row.value = expr
  } else {
    varList.value.push({ key, value: expr, secret: false })
  }
  syncFromTable()
}

function validateCurrent() {
  let obj
  if (mode.value === 'json') {
    try {
      obj = parseJsonText()
    } catch (err) {
      lastError.value = err.message
      ElMessage.error(err.message)
      emit('validate', { ok: false, error: err.message })
      return false
    }
  } else {
    obj = listToVarsObject(varList.value)
  }
  const check = validateVarsObject(obj)
  if (check.ok) {
    lastError.value = ''
    ElMessage.success('变量格式校验通过')
  } else {
    lastError.value = check.error
    ElMessage.error(check.error)
  }
  emit('validate', check)
  return check.ok
}

function triggerImport() {
  fileInputRef.value?.click()
}

function onFileImport(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const parsed = JSON.parse(reader.result)
      if (typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('根节点必须是对象')
      }
      loadFromModel(parsed)
      jsonText.value = stringifyObject(parsed)
      emitObject(parsed)
      ElMessage.success('已导入 JSON')
    } catch (err) {
      ElMessage.error(`导入失败：${err.message || 'JSON 格式错误'}`)
    }
  }
  reader.readAsText(file, 'utf-8')
}

function exportJson() {
  let obj
  if (mode.value === 'json') {
    try {
      obj = parseJsonText()
    } catch {
      obj = listToVarsObject(varList.value)
    }
  } else {
    obj = listToVarsObject(varList.value)
  }
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'environment-variables.json'
  a.click()
  URL.revokeObjectURL(url)
}

/** 供父组件保存前调用 */
function validateAndGet() {
  if (mode.value === 'json') {
    try {
      const obj = parseJsonText()
      const check = validateVarsObject(obj)
      if (!check.ok) {
        lastError.value = check.error
        ElMessage.error(check.error)
        emit('validate', check)
        return null
      }
      lastError.value = ''
      emitObject(obj)
      return obj
    } catch (err) {
      lastError.value = err.message
      ElMessage.error(err.message)
      emit('validate', { ok: false, error: err.message })
      return null
    }
  }
  if (!validateCurrent()) return null
  return listToVarsObject(varList.value)
}

defineExpose({ validateAndGet, validateCurrent })
</script>

<style scoped lang="scss">
.global-vars-editor {
  width: 100%;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.hidden-file {
  display: none;
}

.quick-hints {
  margin-top: 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}

.hint-label {
  color: var(--el-text-color-secondary);
}

.hint-tag {
  cursor: pointer;
}

.validate-alert {
  margin-top: 10px;
}
</style>
