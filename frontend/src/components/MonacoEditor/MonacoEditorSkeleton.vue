<template>
  <div class="monaco-skeleton" :style="{ height }">
    <span class="monaco-skeleton-text">加载编辑器…</span>
  </div>
</template>

<script setup>
defineProps({
  height: { type: String, default: '160px' },
})
</script>

<style scoped>
.monaco-skeleton {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: var(--el-fill-color-lighter, #f5f7fa);
}
.monaco-skeleton-text {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
</style>
