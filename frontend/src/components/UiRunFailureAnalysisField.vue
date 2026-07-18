<template>
  <el-form-item v-if="options?.failure_analysis_enabled" label="失败分析" class="ui-run-failure-field">
    <div v-if="options.failure_analysis_allow_run_override" class="ui-run-segment-group">
      <div
        :class="['ui-run-segment', 'ui-run-segment--grow', { active: modelValue === true }]"
        @click="$emit('update:modelValue', true)"
      >
        <el-icon><CircleCheck /></el-icon><span>开启</span>
      </div>
      <div
        :class="['ui-run-segment', 'ui-run-segment--grow', { active: modelValue === false }]"
        @click="$emit('update:modelValue', false)"
      >
        <el-icon><CircleClose /></el-icon><span>关闭</span>
      </div>
    </div>
    <el-alert
      v-else
      type="info"
      :closable="false"
      show-icon
      :title="`报告页将按项目默认：${options.failure_analysis_default_on_report ? '展示' : '隐藏'}失败 AI 分析入口`"
    />
    <p v-if="options.failure_analysis_allow_run_override" class="ui-run-act-hint">
      关闭后，本次执行产生的报告不展示「AI 分析 / 批量分析」入口，可加快大批量回归浏览。
    </p>
  </el-form-item>
</template>

<script setup>
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'

defineProps({
  options: { type: Object, default: null },
  modelValue: { type: Boolean, default: true },
})

defineEmits(['update:modelValue'])
</script>

<style lang="scss">
@use '@/style/ui-run-config.scss';

.ui-run-failure-field {
  :deep(.el-form-item__label) {
    white-space: nowrap;
  }
}
</style>
