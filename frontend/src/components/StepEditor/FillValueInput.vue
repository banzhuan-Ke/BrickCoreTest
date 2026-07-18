<template>
  <div class="fill-value-input">
    <el-select v-model="mode" size="small" style="width: 140px; flex-shrink: 0" @change="emitValue">
      <el-option v-for="m in FILL_VALUE_MODES" :key="m.value" :label="m.label" :value="m.value" />
    </el-select>
    <el-input
      v-if="mode === 'fixed'"
      v-model="fixedText"
      :placeholder="fixedPlaceholder"
      style="flex: 1"
      @input="emitValue"
    />
    <el-input
      v-else-if="mode === 'prefix_timestamp' || mode === 'prefix_datetime'"
      v-model="prefixText"
      placeholder="前缀，如 order_、auto_"
      style="flex: 1"
      @input="emitValue"
    />
    <el-text v-else type="info" size="small" class="preview">
      执行时填入：{{ preview }}
    </el-text>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  FILL_VALUE_MODES,
  detectFillValueMode,
  buildFillValue,
} from '@/utils/fillValueMode.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const fixedPlaceholder = '输入固定文本，可含 ${{var}}'

const mode = ref('fixed')
const fixedText = ref('')
const prefixText = ref('')

const preview = computed(() =>
  buildFillValue(mode.value, { fixed: fixedText.value, prefix: prefixText.value })
)

function syncFromModel(val) {
  const parsed = detectFillValueMode(val)
  mode.value = parsed.mode
  fixedText.value = parsed.fixed ?? ''
  prefixText.value = parsed.prefix ?? ''
}

function emitValue() {
  emit('update:modelValue', buildFillValue(mode.value, {
    fixed: fixedText.value,
    prefix: prefixText.value,
  }))
}

watch(
  () => props.modelValue,
  (v) => syncFromModel(v),
  { immediate: true },
)
</script>

<style scoped>
.fill-value-input {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.preview {
  flex: 1;
  font-family: monospace;
  word-break: break-all;
}
</style>
