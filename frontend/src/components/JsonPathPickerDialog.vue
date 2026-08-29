<template>
  <el-dialog
    :model-value="modelValue"
    title="JSONPath 提取工具"
    width="960px"
    top="6vh"
    append-to-body
    destroy-on-close
    class="json-path-picker-dialog"
    @update:model-value="emit('update:modelValue', $event)"
    @opened="initState"
  >
    <JsonPathWorkbench
      v-model:json-text="jsonText"
      v-model:path="path"
      :sample-json="sampleJson"
      @enter="confirm"
    />
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import JsonPathWorkbench from './JsonPathWorkbench.vue'
import {
  defaultJsonPathSample,
  readCachedJsonSample,
  writeCachedJsonSample,
} from '@/utils/jsonPath.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  path: { type: String, default: '' },
  sampleJson: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const jsonText = ref('')
const path = ref('')

function initState() {
  path.value = props.path || ''
  const cached = readCachedJsonSample()
  if (cached.trim()) jsonText.value = cached
  else if (props.sampleJson.trim()) jsonText.value = props.sampleJson
  else jsonText.value = defaultJsonPathSample()
}

function confirm() {
  const next = String(path.value || '').trim()
  if (!next) {
    ElMessage.warning('请填写 JSONPath')
    return
  }
  writeCachedJsonSample(jsonText.value)
  emit('confirm', next)
  emit('update:modelValue', false)
}
</script>
