<template>
  <el-button class="tm-back-btn" text bg @click="$emit('click', $event)">
    <el-icon><ArrowLeft /></el-icon>
    <span>{{ label }}</span>
  </el-button>
</template>

<script setup>
import { ArrowLeft } from '@element-plus/icons-vue'

defineProps({
  label: { type: String, default: '返回' },
})
defineEmits(['click'])
</script>

<style scoped>
.tm-back-btn {
  --el-button-bg-color: var(--el-fill-color-light);
  --el-button-hover-bg-color: var(--el-fill-color);
  --el-button-active-bg-color: var(--el-fill-color-dark);
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  gap: 4px;
}
.tm-back-btn:hover {
  color: var(--el-color-primary);
}
</style>
