<template>
  <el-select
    :model-value="displayValue"
    :placeholder="placeholder"
    :style="style"
    :size="size"
    :clearable="clearable"
    @update:model-value="onSelect"
  >
    <el-option :label="projectCommonLabel" :value="PROJECT_SCOPE" />
    <el-option
      v-for="e in envList"
      :key="e.id"
      :label="e.name"
      :value="e.id"
    />
  </el-select>
</template>

<script setup>
import { computed } from 'vue'
import { ProjectStore } from '@/stores/module/ProjectStore'

/** el-select 无法稳定回显 value=null，对外仍用 null 表示项目通用 */
const PROJECT_SCOPE = '__project__'

const props = defineProps({
  modelValue: { type: [Number, String, null], default: null },
  placeholder: { type: String, default: '选择环境范围' },
  style: { type: [String, Object], default: () => ({ width: '100%' }) },
  size: { type: String, default: 'default' },
  clearable: { type: Boolean, default: false },
  projectCommonLabel: {
    type: String,
    default: '当前项目通用（全环境可用）',
  },
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const envList = computed(() => proStore.envList || [])

const displayValue = computed(() => {
  if (props.modelValue === null || props.modelValue === undefined || props.modelValue === '') {
    return PROJECT_SCOPE
  }
  return props.modelValue
})

function onSelect(value) {
  if (value === PROJECT_SCOPE || value === null || value === undefined || value === '') {
    emit('update:modelValue', null)
    return
  }
  emit('update:modelValue', value)
}
</script>
