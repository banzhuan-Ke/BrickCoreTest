<template>
  <el-select
    :model-value="modelValue"
    :size="size"
    :style="selectStyle"
    :placeholder="placeholder"
    class="http-extractor-source-select"
    popper-class="http-extractor-source-popper"
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
        :label="optionLabel(group, opt)"
        :value="opt.value"
      >
        <div class="opt-main">
          <span class="opt-title">{{ optionLabel(group, opt) }}</span>
          <span v-if="opt.hint" class="opt-hint">{{ opt.hint }}</span>
        </div>
      </el-option>
    </el-option-group>
  </el-select>
</template>

<script setup>
import { EXTRACTOR_SOURCE_GROUPS } from '../utils/httpExtractAssertUi.js'

defineProps({
  modelValue: { type: String, default: 'json' },
  size: { type: String, default: 'default' },
  placeholder: { type: String, default: '从哪里取值' },
  selectStyle: { type: [String, Object], default: 'width: 100%' },
})

defineEmits(['update:modelValue'])

const optionLabel = (group, opt) => `${group.label} · ${opt.label}`
</script>

<style scoped>
.opt-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.35;
  padding: 2px 0;
  white-space: normal;
}
.opt-title {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.opt-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: normal;
  word-break: break-word;
}
</style>

<!-- 下拉挂到 body，需非 scoped 才能抬高 option 行高，避免标题/说明叠字 -->
<style>
.http-extractor-source-popper.el-select__popper,
.http-extractor-source-popper {
  max-width: min(420px, 92vw);
}
.http-extractor-source-popper .el-select-dropdown__item {
  height: auto !important;
  min-height: 34px;
  line-height: 1.35 !important;
  padding-top: 8px;
  padding-bottom: 8px;
  white-space: normal;
}
.http-extractor-source-popper .el-select-group__title {
  line-height: 1.4;
  padding: 8px 12px 4px;
}
</style>
