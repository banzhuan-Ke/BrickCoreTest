<template>
  <div class="header-template-editor">
    <div class="toolbar">
      <el-button size="small" type="primary" link icon="Plus" @click="addRow">添加 Header</el-button>
      <el-button size="small" link @click="triggerImport">导入 JSON</el-button>
      <el-button size="small" link :disabled="!headerList.length" @click="exportJson">导出 JSON</el-button>
    </div>

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
          label="插入变量"
          hint-text="含项目/环境/Token 授权/内置变量；工厂标签与工具请用旁侧按钮。"
        />
        <ToolInsertButton :env-id="refEnvId" label="插入工具" />
        <el-button type="info" link size="small" icon="Collection" @click="openTagPicker">
          数据工厂标签
        </el-button>
      </div>
      <span class="var-toolbar-hint">先点击下方「Header 值」输入框再插入；变量 <code v-pre>${{名}}</code> / 标签 <code v-pre>${{df:标签}}</code> / 工具 <code v-pre>${{dt:...}}</code></span>
    </div>

    <input ref="fileInputRef" type="file" accept=".json,application/json" class="hidden-file" @change="onFileImport" />

    <el-table :data="headerList" size="small" border max-height="360" empty-text="暂无 Header">
      <el-table-column label="Header 名" min-width="140">
        <template #default="{ $index }">
          <el-input v-model="headerList[$index].key" size="small" placeholder="Authorization" @blur="syncFromTable" />
        </template>
      </el-table-column>
      <el-table-column label="Header 值" min-width="280">
        <template #default="{ $index }">
          <div class="value-row">
            <el-input
              v-model="headerList[$index].value"
              size="small"
              placeholder="Bearer token 或 ${{变量名}}"
              @blur="syncFromTable"
            />
            <VarInsertButton
              :env-id="refEnvId"
              :show-env-edit="false"
              label="变量"
              size="small"
            />
            <ToolInsertButton :env-id="refEnvId" label="工具" size="small" link />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="120">
        <template #default="{ $index }">
          <el-input v-model="headerList[$index].description" size="small" placeholder="描述" @blur="syncFromTable" />
        </template>
      </el-table-column>
      <el-table-column width="56" align="center">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" icon="Delete" @click="removeRow($index)" />
        </template>
      </el-table-column>
    </el-table>

    <div class="quick-hints">
      <span class="hint-label">提示：</span>
      <span class="hint-text">值支持 <code v-pre>${{变量名}}</code>，执行时会按所选环境替换；模板仅用于编辑时快速导入，不会自动参与请求</span>
    </div>

    <el-alert v-if="lastError" :title="lastError" type="error" show-icon closable class="validate-alert" @close="lastError = ''" />

    <DataFactoryTagPicker
      v-if="projectId"
      v-model="tagPickerVisible"
      :project-id="projectId"
      @insert="onDfTagInsert"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { normalizeTemplateHeaderList, validateTemplateHeaders } from '@/utils/headerTemplates.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import VarInsertButton from '@/components/VarInsertButton.vue'
import ToolInsertButton from '@/components/ToolInsertButton.vue'
import DataFactoryTagPicker from '@/views/ApiModule/components/DataFactoryTagPicker.vue'
import { insertVarRef, snapshotInsertTarget } from '@/utils/varInsert.js'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:modelValue', 'validate'])

const proStore = ProjectStore()
const headerList = ref([])
const lastError = ref('')
const fileInputRef = ref(null)
const syncing = ref(false)
const refEnvId = ref(null)
const tagPickerVisible = ref(false)

const projectId = computed(() => proStore.projectInfo?.id)

function loadFromModel(val) {
  syncing.value = true
  headerList.value = normalizeTemplateHeaderList(val)
  syncing.value = false
}

watch(
  () => props.modelValue,
  (v) => loadFromModel(v),
  { immediate: true, deep: true }
)

watch(
  () => proStore.envList,
  (list) => {
    if (!refEnvId.value && Array.isArray(list) && list.length) {
      refEnvId.value = list[0].id
    }
  },
  { immediate: true }
)

function emitList() {
  const check = validateTemplateHeaders(headerList.value)
  if (!check.ok) {
    lastError.value = check.error
    emit('validate', check)
    return false
  }
  lastError.value = ''
  emit('update:modelValue', check.items)
  emit('validate', check)
  return true
}

function syncFromTable() {
  if (syncing.value) return
  emitList()
}

function addRow() {
  headerList.value.push({ key: '', value: '', description: '' })
}

function removeRow(index) {
  headerList.value.splice(index, 1)
  syncFromTable()
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
      const list = Array.isArray(parsed) ? parsed : parsed?.headers
      if (!Array.isArray(list)) throw new Error('JSON 需为数组或 { headers: [] }')
      loadFromModel(list)
      emitList()
      ElMessage.success('已导入 JSON')
    } catch (err) {
      ElMessage.error(`导入失败：${err.message || 'JSON 格式错误'}`)
    }
  }
  reader.readAsText(file, 'utf-8')
}

function exportJson() {
  const blob = new Blob([JSON.stringify(headerList.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'header-template.json'
  a.click()
  URL.revokeObjectURL(url)
}

function openTagPicker() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  snapshotInsertTarget()
  tagPickerVisible.value = true
}

async function onDfTagInsert(refStr) {
  const m = String(refStr).match(/^\$\{\{(.+)\}\}$/)
  const name = m ? m[1] : refStr
  const result = await insertVarRef(name)
  if (result?.ok) {
    syncFromTable()
    ElMessage.success(result.mode === 'copy' ? `已复制 ${refStr}，请粘贴到输入框` : `已插入 ${refStr}`)
  } else {
    ElMessage.warning('请先将光标放入「Header 值」输入框')
  }
}

function validateAndGet() {
  const check = validateTemplateHeaders(headerList.value)
  if (!check.ok) {
    lastError.value = check.error
    ElMessage.error(check.error)
    return null
  }
  lastError.value = ''
  return check.items
}

defineExpose({ validateAndGet })
</script>

<style scoped lang="scss">
.header-template-editor {
  width: 100%;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.var-toolbar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
  padding: 8px 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.var-toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.var-toolbar-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;

  code {
    font-family: monospace;
    background: var(--el-fill-color);
    padding: 0 3px;
    border-radius: 3px;
  }
}

.value-row {
  display: flex;
  align-items: center;
  gap: 2px;

  .el-input {
    flex: 1;
    min-width: 0;
  }
}

.hidden-file {
  display: none;
}

.quick-hints {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.hint-label {
  margin-right: 4px;
}

.validate-alert {
  margin-top: 10px;
}
</style>
