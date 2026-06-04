<template>
  <div class="json-textarea" :class="{ 'json-textarea--toolbar': showToolbar }">
    <div v-if="showToolbar" class="json-textarea-toolbar">
      <el-button size="small" text type="primary" @click="handleFormat">格式化 JSON</el-button>
      <el-button v-if="showCompact" size="small" text @click="handleCompact">压缩为一行</el-button>
      <slot name="toolbar-extra" />
    </div>
    <el-input
      :model-value="modelValue"
      type="textarea"
      :rows="rows"
      :placeholder="placeholder"
      :disabled="disabled"
      :class="inputClass"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { compactJsonText, formatJsonText } from '@/utils/jsonFormat.js'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  rows: {
    type: [Number, String],
    default: 8,
  },
  placeholder: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  inputClass: {
    type: String,
    default: 'code-editor',
  },
  /** 是否显示格式化工具栏 */
  jsonMode: {
    type: Boolean,
    default: true,
  },
  showCompact: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const showToolbar = computed(() => props.jsonMode)

function handleFormat() {
  const result = formatJsonText(props.modelValue)
  if (!result.ok) {
    ElMessage.error(result.error)
    return
  }
  emit('update:modelValue', result.text)
  ElMessage.success('JSON 已格式化')
}

function handleCompact() {
  const result = compactJsonText(props.modelValue)
  if (!result.ok) {
    ElMessage.error(result.error)
    return
  }
  emit('update:modelValue', result.text)
  ElMessage.success('JSON 已压缩')
}
</script>

<style scoped lang="scss">
.json-textarea {
  width: 100%;
}

.json-textarea-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.json-textarea--toolbar :deep(.el-textarea__inner) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
}
</style>
