<template>
  <div class="template-var-table-editor">
    <div class="table-toolbar">
      <span class="field-hint">{{ hint }}</span>
      <el-button type="primary" link size="small" @click="addRow">添加一行</el-button>
    </div>
    <el-table :data="rows" size="small" border class="var-table">
      <el-table-column
        v-for="col in columns"
        :key="col.key"
        :label="col.label"
        :min-width="col.input === 'date' ? 148 : 120"
      >
        <template #default="{ row }">
          <el-date-picker
            v-if="col.input === 'date'"
            v-model="row[col.key]"
            type="date"
            value-format="YYYY-MM-DD"
            :placeholder="col.label"
            size="small"
            style="width: 100%;"
            clearable
          />
          <el-input
            v-else
            v-model="row[col.key]"
            :placeholder="col.label"
            size="small"
          />
        </template>
      </el-table-column>
      <el-table-column label="" width="52" align="center">
        <template #default="{ $index }">
          <el-button
            link
            type="danger"
            size="small"
            :disabled="rows.length <= 1"
            @click="removeRow($index)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { emptyTableRow } from '@/modules/knowledge/utils/templateVariableTypes.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  schema: { type: Object, default: null },
  hint: { type: String, default: '填写后写入 Word 表格循环；留空行将被忽略。' }
})

const emit = defineEmits(['update:modelValue'])

const columns = computed(() => props.schema?.columns || [])

const rows = computed({
  get() {
    return props.modelValue?.length ? props.modelValue : [emptyTableRow(props.schema)]
  },
  set(val) {
    emit('update:modelValue', val)
  }
})

function addRow() {
  emit('update:modelValue', [...rows.value, emptyTableRow(props.schema)])
}

function removeRow(index) {
  const next = rows.value.filter((_, i) => i !== index)
  emit('update:modelValue', next.length ? next : [emptyTableRow(props.schema)])
}
</script>

<style scoped>
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.var-table {
  width: 100%;
}
</style>
