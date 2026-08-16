<template>
  <el-form-item label="超时倍率" class="ui-run-timeout-scale-field">
    <div class="ui-run-timeout-scale-row">
      <el-input-number
        :model-value="modelValue"
        :min="0.5"
        :max="5"
        :step="0.5"
        :precision="1"
        :controls="true"
        controls-position="right"
        placeholder="环境默认"
        @update:model-value="$emit('update:modelValue', $event)"
      />
      <el-button v-if="modelValue != null" link type="primary" @click="$emit('update:modelValue', null)">
        用环境
      </el-button>
    </div>
    <p class="ui-run-act-hint">{{ hintText }}</p>
    <el-alert
      v-if="modelValue != null && Number(modelValue) === 1"
      class="ui-run-timeout-scale-alert"
      type="success"
      :closable="false"
      show-icon
      title="本次强制 1 倍：按步骤实际超时跑，覆盖环境慢站高倍率。"
    />
    <el-alert
      v-else-if="modelValue != null && modelValue > 1"
      class="ui-run-timeout-scale-alert"
      type="warning"
      :closable="false"
      show-icon
      title="慢站建议并发控制在 1～2，避免页面未就绪就继续操作。"
    />
  </el-form-item>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Number, default: null },
  /** case：单用例默认不放大；batch：套件/计划默认跟环境慢站策略 */
  mode: {
    type: String,
    default: 'batch',
    validator: (v) => ['case', 'batch'].includes(v),
  },
})

defineEmits(['update:modelValue'])

const hintText = computed(() => {
  if (props.mode === 'case') {
    return '默认 1：按步骤实际超时跑、不放大。点「用环境」则跟随环境慢站倍率；临时放大可填 2～3。显式填 1 会覆盖环境高倍率。'
  }
  return '默认跟随环境慢站策略（留空）。本次可临时放大（如 2～3）；显式填 1 则本次强制不放大并覆盖环境。'
})
</script>

<style scoped>
.ui-run-timeout-scale-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ui-run-timeout-scale-alert {
  margin-top: 8px;
}
</style>
