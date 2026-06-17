<template>
  <div class="execution-log-section" v-if="logItems.length > 0">
    <div class="execution-log-section-title">
      <slot name="title">
        执行日志
      </slot>
      <el-tag size="small" type="info">{{ logItems.length }} 条</el-tag>
    </div>
    <div class="execution-log-container" :style="{ height: containerHeight }">
      <RecycleScroller
        class="execution-log-scroller"
        :items="logItems"
        :item-size="EXECUTION_LOG_ROW_HEIGHT"
        key-field="index"
        v-slot="{ item }"
      >
        <div :class="['execution-log-line', item.level]">
          <span class="execution-log-index">[{{ item.index + 1 }}]</span>
          <span v-if="showTime && item.time" class="execution-log-time">{{ item.time }}</span>
          <span v-if="showLevel" class="execution-log-level" :class="item.level">
            {{ item.level?.toUpperCase() }}
          </span>
          <ExecutionLogMessage :message="item.message" />
        </div>
      </RecycleScroller>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import ExecutionLogMessage from '@/components/Report/ExecutionLogMessage.vue'
import { EXECUTION_LOG_ROW_HEIGHT, parseExecutionLogs } from '@/utils/executionLog.js'

const props = defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  containerHeight: {
    type: String,
    default: '300px'
  },
  showTime: {
    type: Boolean,
    default: false
  },
  showLevel: {
    type: Boolean,
    default: false
  }
})

const logItems = computed(() => parseExecutionLogs(props.logs))
</script>

<style scoped lang="scss">
.execution-log-section-title {
  font-size: 16px;
  font-weight: bold;
  margin: 20px 0 12px;
  padding-left: 12px;
  border-left: 4px solid var(--el-color-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.execution-log-container {
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
}

.execution-log-scroller {
  height: 100%;
}

.execution-log-line {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 28px;
  min-height: 28px;
  max-height: 28px;
  padding: 4px 12px;
  box-sizing: border-box;
  overflow: hidden;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 20px;
  color: #d4d4d4;
  border-bottom: 1px solid #2a2a2a;

  &:hover {
    background: #2a2a2a;
  }

  &.error {
    color: #f85149;
  }

  &.warning,
  &.warn {
    color: #ffa657;
  }

  &.success {
    color: #3fb950;
  }
}

.execution-log-index {
  color: #6e7681;
  min-width: 50px;
  flex-shrink: 0;
  font-size: 11px;
}

.execution-log-time {
  color: #6e7681;
  min-width: 80px;
  flex-shrink: 0;
  font-size: 11px;
}

.execution-log-level {
  min-width: 50px;
  flex-shrink: 0;
  font-weight: bold;
  font-size: 11px;

  &.error { color: #f85149; }
  &.warning,
  &.warn { color: #ffa657; }
  &.info { color: #58a6ff; }
  &.debug { color: #8b949e; }
  &.success { color: #3fb950; }
}
</style>
