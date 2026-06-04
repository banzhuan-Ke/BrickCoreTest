<template>
  <div v-if="rows.length" class="case-stage-timings">
    <h4 v-if="showTitle">⏱️ 阶段耗时分解</h4>
    <el-table :data="rows" border size="small">
      <el-table-column label="阶段" prop="name" width="140" />
      <el-table-column label="耗时" width="100" align="right">
        <template #default="{ row }">
          <span
            :style="{
              color: row.isTotal ? '#409EFF' : row.name === 'HTTP 请求' ? '#67C23A' : '#606266',
              fontWeight: row.isTotal || row.name === 'HTTP 请求' ? 'bold' : 'normal'
            }"
          >{{ row.value }}ms</span>
        </template>
      </el-table-column>
      <el-table-column label="占比" min-width="200">
        <template #default="{ row }">
          <el-progress
            :percentage="row.percentage"
            :color="row.color"
            :show-text="false"
            :stroke-width="10"
            style="width: 100%"
          />
        </template>
      </el-table-column>
    </el-table>
    <div v-if="showHint" class="stage-hint">
      <span>接口耗时（{{ httpLabel }}）为纯 HTTP 网络时间；</span>
      <span>用例总耗时（{{ totalLabel }}）含断言、变量提取、脚本及重试等待。</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatStageTimings } from '../utils/stageTimings'
import { getHttpResponseMs, getCaseTotalMs } from '../utils/runTiming'

const props = defineProps({
  timings: { type: Object, default: null },
  result: { type: Object, default: null },
  showTitle: { type: Boolean, default: true },
  showHint: { type: Boolean, default: true }
})

const rows = computed(() => formatStageTimings(props.timings))
const httpLabel = computed(() => {
  const ms = getHttpResponseMs(props.result)
  return ms != null ? `${ms.toFixed(1)}ms` : '-'
})
const totalLabel = computed(() => {
  const ms = getCaseTotalMs(props.result)
  return ms != null ? `${ms.toFixed(0)}ms` : '-'
})
</script>

<style scoped>
.case-stage-timings h4 {
  margin: 0 0 10px;
  color: #333;
  font-size: 14px;
}

.stage-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
