<template>
  <div class="db-assertions-editor">
    <div class="toolbar">
      <el-button type="primary" size="small" icon="Plus" @click="addRow">添加断言</el-button>
      <span class="tip">{{ tipText }}</span>
    </div>
    <el-table :data="modelValue" size="small" border class="config-table">
      <el-table-column label="名称" width="120">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].name" size="small" placeholder="断言名称" />
        </template>
      </el-table-column>
      <el-table-column label="数据源" width="160">
        <template #default="{ $index }">
          <el-select v-model="modelValue[$index].datasource_id" size="small" clearable placeholder="默认数据源" style="width: 100%">
            <el-option v-for="ds in datasources" :key="ds.id" :label="dsLabel(ds)" :value="ds.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column :label="sqlColumnLabel" min-width="260">
        <template #default="{ $index }">
          <MonacoEditor
            v-model="modelValue[$index].sql"
            language="sql"
            height="100px"
          />
        </template>
      </el-table-column>
      <el-table-column label="字段" width="90">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].field" size="small" :placeholder="fieldPlaceholder($index)" />
        </template>
      </el-table-column>
      <el-table-column label="操作符" width="130">
        <template #default="{ $index }">
          <el-select v-model="modelValue[$index].operator" size="small" style="width: 100%">
            <el-option v-for="op in operators" :key="op.value" :label="op.label" :value="op.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="期望值" width="100">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].expected" size="small" :disabled="['exists', 'not_exists'].includes(modelValue[$index].operator)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeRow($index)" icon="Delete" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MonacoEditor from '@/components/MonacoEditor'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  datasources: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const operators = [
  { label: '等于', value: 'equals' },
  { label: '不等于', value: 'not_equals' },
  { label: '大于', value: 'gt' },
  { label: '大于等于', value: 'gte' },
  { label: '小于', value: 'lt' },
  { label: '小于等于', value: 'lte' },
  { label: '包含', value: 'contains' },
  { label: '行数等于', value: 'row_count_equals' },
  { label: '存在记录', value: 'exists' },
  { label: '不存在', value: 'not_exists' },
]

const hasRedis = computed(() => (props.datasources || []).some((d) => (d.db_type || '').toLowerCase() === 'redis'))
const hasPg = computed(() => (props.datasources || []).some((d) => (d.db_type || '').toLowerCase() === 'postgresql'))

const tipText = computed(() => {
  const parts = ['变量语法 ${{变量名}}']
  if (hasRedis.value) parts.push('Redis 用 GET/HGET 等只读命令')
  if (hasPg.value) parts.push('PostgreSQL 支持 SELECT')
  else parts.push('MySQL/PostgreSQL 仅 SELECT')
  return parts.join('；')
})

const sqlColumnLabel = computed(() => (hasRedis.value ? 'SQL / Redis 命令' : 'SQL (SELECT)'))

function dsById(id) {
  return (props.datasources || []).find((d) => d.id === id)
}

function dsLabel(ds) {
  const t = (ds.db_type || 'mysql').toLowerCase()
  const tag = { mysql: 'MySQL', postgresql: 'PG', redis: 'Redis' }[t] || t
  return `${ds.name} [${tag}]`
}

function fieldPlaceholder(index) {
  const ds = dsById(props.modelValue?.[index]?.datasource_id)
  return (ds?.db_type || '').toLowerCase() === 'redis' ? '可选' : 'cnt'
}

function addRow() {
  const next = [...(props.modelValue || []), {
    name: '',
    datasource_id: null,
    sql: '',
    field: '',
    operator: 'equals',
    expected: '',
  }]
  emit('update:modelValue', next)
}

function removeRow(index) {
  const next = [...(props.modelValue || [])]
  next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.tip {
  font-size: 12px;
  color: #909399;
}
.config-table {
  width: 100%;
}
</style>
