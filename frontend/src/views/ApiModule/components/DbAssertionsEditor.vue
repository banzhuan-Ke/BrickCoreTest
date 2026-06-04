<template>
  <div class="db-assertions-editor">
    <div class="toolbar">
      <el-button type="primary" size="small" icon="Plus" @click="addRow">添加断言</el-button>
      <span class="tip">仅支持 SELECT；变量语法 <code v-pre>${{变量名}}</code></span>
    </div>
    <el-table :data="modelValue" size="small" border class="config-table">
      <el-table-column label="名称" width="120">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].name" size="small" placeholder="断言名称" />
        </template>
      </el-table-column>
      <el-table-column label="数据源" width="150">
        <template #default="{ $index }">
          <el-select v-model="modelValue[$index].datasource_id" size="small" clearable placeholder="默认数据源" style="width: 100%">
            <el-option v-for="ds in datasources" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="SQL (SELECT)" min-width="220">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].sql" size="small" type="textarea" :rows="2" placeholder="SELECT count(*) AS cnt FROM user WHERE mobile='${{phone}}'" />
        </template>
      </el-table-column>
      <el-table-column label="字段" width="90">
        <template #default="{ $index }">
          <el-input v-model="modelValue[$index].field" size="small" placeholder="cnt" />
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
