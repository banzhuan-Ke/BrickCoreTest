<template>
  <el-select
    :model-value="modelValue"
    :size="size"
    :style="selectStyle"
    :placeholder="placeholder"
    class="http-assertion-type-select"
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
        :label="`${group.label} · ${opt.label}`"
        :value="opt.value"
      >
        <div class="opt-main">
          <span class="opt-title">{{ group.label }} · {{ opt.label }}</span>
        </div>
      </el-option>
    </el-option-group>
  </el-select>
</template>

<script setup>
import { computed } from 'vue'
import { assertionTypeGroups } from '../utils/httpExtractAssertUi.js'

const props = defineProps({
  modelValue: { type: String, default: 'status_code' },
  size: { type: String, default: 'default' },
  placeholder: { type: String, default: '断言对象' },
  selectStyle: { type: [String, Object], default: 'width: 100%' },
  includeWs: { type: Boolean, default: false },
})

defineEmits(['update:modelValue'])

const groups = computed(() => assertionTypeGroups({ includeWs: props.includeWs }))
</script>

<style scoped>
.opt-main {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
  padding: 2px 0;
}
.opt-title {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
</style>
