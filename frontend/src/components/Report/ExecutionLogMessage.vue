<template>
  <el-tooltip
    class="execution-log-message-wrap"
    placement="top"
    :show-after="200"
    :teleported="true"
    popper-class="execution-log-tooltip"
  >
    <template #content>
      <div class="execution-log-tooltip-body">{{ message }}</div>
    </template>
    <span class="execution-log-message">{{ message }}</span>
  </el-tooltip>
</template>

<script setup>
defineProps({
  message: {
    type: String,
    default: ''
  }
})
</script>

<style scoped lang="scss">
.execution-log-message-wrap {
  flex: 1;
  min-width: 0;
  display: block;
  overflow: hidden;
  height: 20px;
  line-height: 20px;
}

.execution-log-message-wrap :deep(.el-tooltip__trigger) {
  display: block;
  width: 100%;
  overflow: hidden;
}

.execution-log-message {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

<style lang="scss">
.execution-log-tooltip {
  max-width: min(800px, 92vw) !important;
}

.execution-log-tooltip-body {
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  max-height: 60vh;
  overflow-y: auto;
}
</style>
