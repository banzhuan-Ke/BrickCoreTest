<template>
  <div v-if="slots?.length" class="input-doc-picker">
    <el-divider v-if="showDivider" content-position="left">{{ title }}</el-divider>
    <div v-if="hint" class="picker-hint">{{ hint }}</div>
    <el-form-item
      v-for="slot in slots"
      :key="slot.key"
      :label="slotLabel(slot)"
      label-width="108px"
    >
      <el-select
        :model-value="slotValue(slot)"
        :multiple="!!slot.multiple"
        :collapse-tags="!!slot.multiple"
        :collapse-tags-tooltip="!!slot.multiple"
        clearable
        filterable
        :placeholder="slotPlaceholder(slot)"
        style="width: 100%;"
        @update:model-value="val => updateSlot(slot, val)"
      >
        <el-option
          v-for="candidate in slot.candidates || []"
          :key="candidate.id"
          :label="optionLabel(candidate)"
          :value="candidate.id"
        />
      </el-select>
      <div v-if="!(slot.candidates || []).length" class="field-hint warn">
        文件夹内暂无「{{ slot.label }}」类文件，请先上传或调整文档类型
      </div>
      <div v-else-if="slot.multiple" class="field-hint">
        可多选；单文档过长时生成报告将自动分块提炼要点后合并（Map-Reduce），无需手动截断
      </div>
    </el-form-item>
  </div>
</template>

<script setup>
const props = defineProps({
  slots: { type: Array, default: () => [] },
  modelValue: { type: Object, default: () => ({}) },
  title: { type: String, default: '输入文档' },
  hint: { type: String, default: '' },
  showDivider: { type: Boolean, default: true }
})

const emit = defineEmits(['update:modelValue'])

function slotLabel(slot) {
  return slot.required ? `${slot.label} *` : slot.label
}

function slotPlaceholder(slot) {
  if (slot.multiple) {
    return slot.required ? `请选择${slot.label}（可多选）` : `可选：${slot.label}（可多选）`
  }
  return slot.required ? `请选择${slot.label}` : `可选：${slot.label}`
}

function optionLabel(candidate) {
  const name = candidate.file_name || candidate.title || `#${candidate.id}`
  if (candidate.title && candidate.file_name && candidate.title !== candidate.file_name) {
    return `${name}（${candidate.title}）`
  }
  return name
}

function slotValue(slot) {
  const val = props.modelValue?.[slot.key]
  if (slot.multiple) {
    return Array.isArray(val) ? val : val ? [val] : []
  }
  return val ?? null
}

function updateSlot(slot, val) {
  const next = { ...(props.modelValue || {}) }
  if (slot.multiple) {
    next[slot.key] = Array.isArray(val) ? val.filter(Boolean) : []
  } else {
    next[slot.key] = val ?? null
  }
  emit('update:modelValue', next)
}
</script>

<style scoped>
.picker-hint {
  margin: -4px 0 12px 108px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.field-hint.warn {
  color: var(--el-color-warning);
}
</style>
