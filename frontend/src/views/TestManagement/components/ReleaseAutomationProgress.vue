<template>
  <el-card class="auto-progress" shadow="never">
    <div class="ap-header">
      <div>
        <h3 class="ap-title">自动化渐进</h3>
        <p class="ap-sub">可选补强，不阻塞发布。映射覆盖 {{ stats.mapped }}/{{ stats.total }}（{{ stats.percent }}%）</p>
      </div>
      <div class="ap-actions">
        <el-progress
          type="circle"
          :percentage="stats.percent"
          :width="52"
          :stroke-width="6"
        />
      </div>
    </div>
    <div class="ap-metrics">
      <el-tag type="info" effect="plain">核心高风险 {{ stats.highMapped }}/{{ stats.highTotal }}</el-tag>
      <el-tag v-if="phase3Progress != null" type="success" effect="plain">向导 {{ phase3Progress }}%</el-tag>
    </div>
    <div v-if="unmappedHigh.length" class="ap-list">
      <div class="ap-list-title">未映射核心用例</div>
      <div
        v-for="row in unmappedHigh.slice(0, 8)"
        :key="row.id"
        class="ap-row"
      >
        <span class="ap-row-title">{{ row.case_title || `#${row.functional_case_id}` }}</span>
        <el-tag size="small" :type="riskTagType(row.risk_level)">{{ riskLabel(row.risk_level) }}</el-tag>
        <el-button link type="primary" size="small" @click="emit('map', row)">映射</el-button>
      </div>
      <div v-if="unmappedHigh.length > 8" class="ap-more">另有 {{ unmappedHigh.length - 8 }} 项…</div>
    </div>
    <el-empty v-else-if="stats.total" description="核心用例均已映射或暂无高风险项" :image-size="48" />
    <el-empty v-else description="请先纳入测试范围" :image-size="48" />
    <div class="ap-footer">
      <el-button size="small" @click="emit('scopes')">查看全部范围</el-button>
      <el-button
        v-if="unmappedAll.length"
        size="small"
        type="primary"
        plain
        @click="emit('map', unmappedAll[0])"
      >映射下一例</el-button>
      <el-button
        v-if="canEdit && primaryPlanId"
        size="small"
        type="success"
        plain
        @click="emit('gen-automation')"
      >补齐自动化项</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import {
  automationCoverageStats,
  listUnmappedScopes
} from '@/utils/releaseAgileWorkflow'

const props = defineProps({
  scopes: { type: Array, default: () => [] },
  phase3Progress: { type: Number, default: null },
  primaryPlanId: { type: Number, default: null },
  canEdit: { type: Boolean, default: false }
})

const emit = defineEmits(['map', 'scopes', 'gen-automation'])

const stats = computed(() => automationCoverageStats(props.scopes))
const unmappedHigh = computed(() => listUnmappedScopes(props.scopes, { highRiskOnly: true }))
const unmappedAll = computed(() => listUnmappedScopes(props.scopes))

const riskLabel = (r) =>
  ({ low: '低', medium: '中', high: '高', critical: '严重' }[r] || r)
const riskTagType = (r) =>
  ({ low: 'info', medium: '', high: 'warning', critical: 'danger' }[r] || 'info')
</script>

<style scoped>
.auto-progress {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
}
.ap-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}
.ap-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
}
.ap-sub {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.ap-metrics {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.ap-list-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}
.ap-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.ap-row-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.ap-more {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}
.ap-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
</style>
