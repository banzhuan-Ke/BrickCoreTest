<template>
  <div class="json-path-field-wrap" :style="inputStyle">
    <el-input
      :model-value="modelValue"
      :size="size"
      :placeholder="placeholder"
      :disabled="disabled"
      class="json-path-field"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <template #suffix>
        <el-tooltip content="JSONPath 提取工具" :show-after="300" placement="top">
          <el-button
            class="jp-field-btn"
            link
            type="primary"
            :disabled="disabled"
            @click.stop="pickerVisible = true"
          >
            <el-icon><Aim /></el-icon>
          </el-button>
        </el-tooltip>
      </template>
    </el-input>
    <JsonPathPickerDialog
      v-model="pickerVisible"
      :path="modelValue"
      :sample-json="sampleJson"
      @confirm="onConfirm"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Aim } from '@element-plus/icons-vue'
import JsonPathPickerDialog from './JsonPathPickerDialog.vue'

defineProps({
  modelValue: { type: String, default: '' },
  sampleJson: { type: String, default: '' },
  placeholder: { type: String, default: '$.data.token' },
  size: { type: String, default: 'default' },
  disabled: { type: Boolean, default: false },
  /** 外层样式；表格单元格可省略（默认撑满），flex 行内请传 flex:1;min-width:0 */
  inputStyle: { type: [String, Object], default: () => ({ width: '100%' }) },
})

const emit = defineEmits(['update:modelValue'])
const pickerVisible = ref(false)

function onConfirm(path) {
  emit('update:modelValue', path)
}
</script>

<style scoped>
.json-path-field-wrap {
  min-width: 0;
  box-sizing: border-box;
}
.json-path-field {
  width: 100%;
}
.jp-field-btn {
  padding: 0;
  height: 20px;
  width: 20px;
  min-height: 20px;
}
.jp-field-btn :deep(.el-icon) {
  font-size: 14px;
}
</style>
