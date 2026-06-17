<template>
  <div class="ws-steps-editor">
    <el-table :data="modelValue" size="small" border>
      <el-table-column label="动作" width="110">
        <template #default="{ $index }">
          <el-select v-model="modelValue[$index].action" size="small">
            <el-option label="发送" value="send" />
            <el-option label="接收" value="receive" />
            <el-option label="等待" value="wait" />
            <el-option label="关闭" value="close" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="消息/参数" min-width="220">
        <template #default="{ row, $index }">
          <template v-if="row.action === 'send'">
            <el-input v-model="modelValue[$index].message" size="small" placeholder="发送内容，支持变量占位符" />
          </template>
          <template v-else-if="row.action === 'receive'">
            <span class="inline-fields">
              条数
              <el-input-number v-model="modelValue[$index].count" :min="1" :max="20" size="small" controls-position="right" />
              超时(s)
              <el-input-number v-model="modelValue[$index].timeout" :min="1" :max="120" size="small" controls-position="right" />
            </span>
          </template>
          <template v-else-if="row.action === 'wait'">
            延迟(ms)
            <el-input-number v-model="modelValue[$index].delay_ms" :min="0" :max="60000" size="small" controls-position="right" />
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="100">
        <template #default="{ row, $index }">
          <el-select v-if="row.action === 'send'" v-model="modelValue[$index].message_type" size="small">
            <el-option label="文本" value="text" />
            <el-option label="JSON" value="json" />
          </el-select>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeStep($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-button type="primary" link size="small" @click="addStep" icon="Plus" class="add-btn">添加步骤</el-button>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const addStep = () => {
  emit('update:modelValue', [
    ...props.modelValue,
    { action: 'send', message: '', message_type: 'text', delay_ms: 0, count: 1, timeout: 5 }
  ])
}

const removeStep = (index) => {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.add-btn { margin-top: 8px; }
.inline-fields { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
