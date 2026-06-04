<template>
  <span v-if="hasAny" class="run-timing-badges">
    <span
      v-if="httpMs != null"
      class="run-timing run-timing--http"
      title="仅 httpx 发起请求到收到响应的网络耗时，用于评估接口性能"
    >
      接口耗时: {{ formatTimingMs(httpMs, digits) }}
    </span>
    <span
      v-if="totalMs != null"
      class="run-timing run-timing--total"
      title="含断言、变量提取、脚本及重试等待的用例执行总耗时"
    >
      用例总耗时: {{ formatTimingMs(totalMs, digits) }}
    </span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { getHttpResponseMs, getCaseTotalMs, formatTimingMs } from '../utils/runTiming'

const props = defineProps({
  result: { type: Object, default: null },
  digits: { type: Number, default: 2 }
})

const httpMs = computed(() => getHttpResponseMs(props.result))
const totalMs = computed(() => getCaseTotalMs(props.result))
const hasAny = computed(() => httpMs.value != null || totalMs.value != null)
</script>

<style scoped>
.run-timing-badges {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-left: 12px;
}

.run-timing {
  font-size: 13px;
}

.run-timing--http {
  color: #67c23a;
  font-weight: 600;
}

.run-timing--total {
  color: #909399;
}
</style>
