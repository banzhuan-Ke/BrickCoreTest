<template>
  <div>
    <el-alert type="info" show-icon :closable="false" class="tip">
      在 Word 模板中使用 <code v-pre>{{ 变量名 }}</code> 标注自动填充位置；自定义变量可在报告向导中填写或由默认值注入。
    </el-alert>
    <div class="var-toolbar">
      <el-radio-group v-model="varFilter" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="builtin">内置</el-radio-button>
        <el-radio-button value="custom">自定义</el-radio-button>
      </el-radio-group>
      <el-button v-if="canExecute" type="primary" size="small" @click="openVarForm()">新增自定义变量</el-button>
    </div>
    <div class="var-filters">
      <el-input
        v-model="nameFilter"
        clearable
        placeholder="按变量名或说明搜索"
        size="small"
        class="filter-name"
      />
      <el-select
        v-model="categoryFilter"
        clearable
        placeholder="按类别筛选"
        size="small"
        class="filter-category"
      >
        <el-option
          v-for="opt in CATEGORY_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-select
        v-model="typeFilter"
        clearable
        placeholder="按类型筛选"
        size="small"
        class="filter-category"
      >
        <el-option
          v-for="opt in BUILTIN_VALUE_TYPE_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>
    <el-table :data="paginatedVariables" size="small" stripe v-loading="loading">
      <el-table-column prop="name" label="变量" width="168">
        <template #default="{ row }">
          <code>{{ row.name }}</code>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="96" align="center">
        <template #default="{ row }">
          <el-tag :type="valueTypeTag(row.value_type)" size="small">{{ valueTypeLabel(row.value_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="88">
        <template #default="{ row }">
          {{ categoryLabel(row.category) }}
        </template>
      </el-table-column>
      <el-table-column prop="label" label="说明" width="120" show-overflow-tooltip />
      <el-table-column prop="value_hint" label="取值说明" min-width="220" show-overflow-tooltip />
      <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
      <el-table-column prop="default_value" label="默认值" width="120" show-overflow-tooltip />
      <el-table-column label="来源" width="72" align="center">
        <template #default="{ row }">
          <el-tag :type="row.builtin ? 'info' : 'success'" size="small">
            {{ row.builtin ? '内置' : '自定义' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="canExecute" label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.builtin">
            <el-button link type="primary" @click="openVarForm(row)">编辑</el-button>
            <el-button link type="danger" @click="removeVar(row)">删除</el-button>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="var-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="filteredVariables.length"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        small
        background
      />
    </div>

    <el-dialog v-model="varForm.visible" :title="varForm.id ? '编辑自定义变量' : '新增自定义变量'" width="560px">
      <el-form label-width="96px">
        <el-form-item label="变量名" required>
          <el-input
            v-model="varForm.name"
            :disabled="!!varForm.id"
            placeholder="小写 snake_case，如 release_version"
          />
        </el-form-item>
        <el-form-item label="显示名称" required>
          <el-input v-model="varForm.label" placeholder="如：发布版本号" />
        </el-form-item>
        <el-form-item label="变量类型" required>
          <el-select v-model="varForm.value_type" style="width: 100%;">
            <el-option
              v-for="opt in VALUE_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <div class="form-hint">{{ valueTypeFormHint(varForm.value_type) }}</div>
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="varForm.category" placeholder="请选择类别" style="width: 100%;">
            <el-option
              v-for="opt in FORM_CATEGORY_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="varForm.value_type === 'table'" label="表格列">
          <div class="schema-editor">
            <div v-for="(col, idx) in varForm.schemaColumns" :key="idx" class="schema-row">
              <el-input v-model="col.key" placeholder="字段 key" size="small" class="schema-key" />
              <el-input v-model="col.label" placeholder="列标题" size="small" class="schema-label" />
              <el-select v-model="col.input" size="small" class="schema-input">
                <el-option label="文本" value="text" />
                <el-option label="日期" value="date" />
              </el-select>
              <el-button link type="danger" :disabled="varForm.schemaColumns.length <= 1" @click="removeSchemaColumn(idx)">删</el-button>
            </div>
            <el-button link type="primary" @click="addSchemaColumn">添加列</el-button>
          </div>
        </el-form-item>
        <el-form-item label="取值说明">
          <el-input v-model="varForm.value_hint" type="textarea" :rows="2" placeholder="渲染到 Word 时的值格式、填写方式等" />
        </el-form-item>
        <el-form-item label="默认值">
          <el-input
            v-if="varForm.value_type !== 'table'"
            v-model="varForm.default_value"
            :type="varForm.value_type === 'textarea' || varForm.value_type === 'lines' ? 'textarea' : 'text'"
            :rows="varForm.value_type === 'textarea' || varForm.value_type === 'lines' ? 3 : 1"
            placeholder="生成报告时自动填入（可被向导覆盖）"
          />
          <span v-else class="form-hint">表格类型请在报告向导中填写行数据</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="varForm.visible = false">取消</el-button>
        <el-button type="primary" :loading="varForm.saving" @click="saveVar">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'
import {
  BUILTIN_VALUE_TYPE_OPTIONS,
  VALUE_TYPE_OPTIONS,
  defaultTableSchema,
  valueTypeLabel,
  valueTypeTag
} from '@/modules/knowledge/utils/templateVariableTypes.js'

const CATEGORY_OPTIONS = [
  { value: 'system', label: '系统' },
  { value: 'knowledge', label: '资料库' },
  { value: 'ai', label: 'AI 生成' },
  { value: 'user', label: '用户填写' },
  { value: 'custom', label: '自定义' }
]

const FORM_CATEGORY_OPTIONS = [
  { value: 'custom', label: '自定义' },
  { value: 'user', label: '用户填写' }
]

const CATEGORY_LABEL_MAP = Object.fromEntries(CATEGORY_OPTIONS.map(o => [o.value, o.label]))

function categoryLabel(cat) {
  return CATEGORY_LABEL_MAP[cat] || cat || '-'
}

const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canEdit: canExecute } = useKnowledgePermissions()

const loading = ref(false)
const variables = ref([])
const varFilter = ref('all')
const nameFilter = ref('')
const categoryFilter = ref('')
const typeFilter = ref('')
const page = ref(1)
const pageSize = ref(20)
const varForm = ref({
  visible: false,
  id: null,
  name: '',
  label: '',
  category: 'custom',
  value_type: 'text',
  description: '',
  value_hint: '',
  default_value: '',
  schemaColumns: [],
  saving: false
})

function valueTypeFormHint(type) {
  return {
    text: '报告向导中单行输入，写入 {{ 变量名 }}',
    textarea: '报告向导中多行文本框',
    date: '报告向导中日期选择器，建议模板侧按 YYYY-MM-DD 展示',
    table: '报告向导中可编辑表格；Word 模板使用 {% for row in 变量名 %} 循环',
    lines: '报告向导中多行输入，按行拆分为段落循环（每行 {{ line }}）'
  }[type] || ''
}

function addSchemaColumn() {
  varForm.value.schemaColumns.push({ key: '', label: '', input: 'text' })
}

function removeSchemaColumn(index) {
  varForm.value.schemaColumns.splice(index, 1)
}

function resetSchemaColumns(schema) {
  const cols = schema?.columns?.length ? schema.columns.map(c => ({ ...c })) : defaultTableSchema().columns.map(c => ({ ...c }))
  varForm.value.schemaColumns = cols
}

function buildValueSchema() {
  if (varForm.value.value_type !== 'table') return null
  const columns = varForm.value.schemaColumns
    .map(c => ({
      key: (c.key || '').trim(),
      label: (c.label || c.key || '').trim(),
      input: c.input || 'text'
    }))
    .filter(c => c.key)
  return columns.length ? { columns } : null
}

const filteredVariables = computed(() => {
  let list = variables.value
  if (varFilter.value === 'builtin') list = list.filter(v => v.builtin)
  if (varFilter.value === 'custom') list = list.filter(v => !v.builtin)
  const q = nameFilter.value.trim().toLowerCase()
  if (q) {
    list = list.filter(v =>
      (v.name || '').toLowerCase().includes(q)
      || (v.label || '').toLowerCase().includes(q)
      || (v.value_hint || '').toLowerCase().includes(q)
    )
  }
  if (categoryFilter.value) {
    list = list.filter(v => v.category === categoryFilter.value)
  }
  if (typeFilter.value) {
    list = list.filter(v => v.value_type === typeFilter.value)
  }
  return list
})

const paginatedVariables = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredVariables.value.slice(start, start + pageSize.value)
})

watch([varFilter, nameFilter, categoryFilter, typeFilter], () => {
  page.value = 1
})

async function loadVariables() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await knowledgeApi.getTemplateVariables(projectId.value)
    variables.value = res.data?.items || []
  } catch {
    variables.value = []
  } finally {
    loading.value = false
  }
}

function openVarForm(row) {
  if (row) {
    varForm.value = {
      visible: true,
      id: row.id,
      name: row.name,
      label: row.label,
      category: row.category || 'custom',
      value_type: row.value_type || 'text',
      description: row.description || '',
      value_hint: row.value_hint || row.description || '',
      default_value: row.default_value || '',
      schemaColumns: [],
      saving: false
    }
    resetSchemaColumns(row.value_schema)
  } else {
    varForm.value = {
      visible: true,
      id: null,
      name: '',
      label: '',
      category: 'custom',
      value_type: 'text',
      description: '',
      value_hint: '',
      default_value: '',
      schemaColumns: [],
      saving: false
    }
    resetSchemaColumns(defaultTableSchema())
  }
}

async function saveVar() {
  const f = varForm.value
  if (!f.name?.trim() || !f.label?.trim()) {
    ElMessage.warning('请填写变量名和显示名称')
    return
  }
  if (f.value_type === 'table' && !buildValueSchema()) {
    ElMessage.warning('表格类型至少定义一列（含 key）')
    return
  }
  const payload = {
    label: f.label,
    category: f.category,
    value_type: f.value_type,
    value_schema: buildValueSchema(),
    description: f.value_hint || f.description || '',
    default_value: f.default_value
  }
  f.saving = true
  try {
    if (f.id) {
      await knowledgeApi.updateTemplateVariable(f.id, payload, projectId.value)
      ElMessage.success('已更新')
    } else {
      await knowledgeApi.createTemplateVariable({
        name: f.name.trim(),
        ...payload
      }, projectId.value)
      ElMessage.success('已添加')
    }
    f.visible = false
    await loadVariables()
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    f.saving = false
  }
}

async function removeVar(row) {
  try {
    await ElMessageBox.confirm(`确定删除自定义变量「${row.name}」？`, '确认')
    await knowledgeApi.deleteTemplateVariable(row.id, projectId.value)
    ElMessage.success('已删除')
    await loadVariables()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

watch(projectId, loadVariables)

onMounted(loadVariables)
</script>

<style scoped>
.tip {
  margin-bottom: 12px;
}
.var-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.var-filters {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.filter-name {
  width: 240px;
}
.filter-category {
  width: 160px;
}
.schema-editor {
  width: 100%;
}
.schema-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.schema-key {
  width: 120px;
}
.schema-label {
  flex: 1;
}
.schema-input {
  width: 96px;
}
.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.var-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
