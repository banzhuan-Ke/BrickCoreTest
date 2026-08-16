<template>
  <el-select
    :model-value="modelValue"
    :size="size"
    :style="selectStyle"
    :placeholder="placeholder"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-option-group
      v-for="group in groups"
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
import { computed } from 'vue'
import { assertionTypeGroups } from '../utils/httpExtractAssertUi.js'

const props = defineProps({
  modelValue: { type: String, default: 'status_code' },
  size: { type: String, default: 'default' },
  placeholder: { type: String, default: '选择断言方式' },
  selectStyle: { type: [String, Object], default: 'width: 100%' },
  includeWs: { type: Boolean, default: false },
})

defineEmits(['update:modelValue'])

const groups = computed(() => assertionTypeGroups({ includeWs: props.includeWs }))
</script>
