<template>
  <el-tooltip
    v-if="isLong"
    :content="text"
    placement="top"
    :show-after="200"
    popper-class="execution-env-value-tooltip"
  >
    <span class="env-value-cell">{{ text }}</span>
  </el-tooltip>
  <span v-else class="env-value-cell">{{ text }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: {
    type: [String, Number, Boolean, Object, Array],
    default: ''
  }
})

const text = computed(() => {
  const val = props.value
  if (val == null) return '—'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
})

const isLong = computed(() => text.value.length > 80)
</script>

<style scoped>
.env-value-cell {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
