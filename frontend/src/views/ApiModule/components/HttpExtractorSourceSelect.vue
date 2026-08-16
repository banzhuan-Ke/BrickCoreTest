<template>
  <el-select
    :model-value="modelValue"
    :size="size"
    :style="selectStyle"
    :placeholder="placeholder"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-option-group
      v-for="group in EXTRACTOR_SOURCE_GROUPS"
      :key="group.label"
      :label="group.label"
    >
      <el-option
        v-for="opt in group.options"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-option-group>
  </el-select>
</template>

<script setup>
import { EXTRACTOR_SOURCE_GROUPS } from '../utils/httpExtractAssertUi.js'

defineProps({
  modelValue: { type: String, default: 'json' },
  size: { type: String, default: 'default' },
  placeholder: { type: String, default: '选择来源' },
  selectStyle: { type: [String, Object], default: 'width: 100%' },
})

defineEmits(['update:modelValue'])
</script>
