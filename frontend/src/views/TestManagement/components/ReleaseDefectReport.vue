<template>
  <div class="release-defect-report" v-loading="loading">
    <div class="toolbar">
      <el-button type="primary" :loading="loading" @click="load">刷新报告</el-button>
      <el-button v-if="canDefectView" @click="goDefects">打开缺陷台账</el-button>
    </div>

    <div class="summary-cards" v-if="report">
      <div class="card">
        <div class="num">{{ report.summary?.total || 0 }}</div>
        <div class="lab">缺陷总数</div>
      </div>
      <div class="card warn">
        <div class="num">{{ report.open_count || 0 }}</div>
        <div class="lab">未关闭</div>
      </div>
      <div class="card ok">
        <div class="num">{{ report.closed_count || 0 }}</div>
        <div class="lab">已关闭</div>
      </div>
      <div
        v-for="(label, key) in severityLabels"
        :key="key"
        class="card sev"
      >
        <div class="num">{{ report.summary?.by_severity?.[key] || 0 }}</div>
        <div class="lab">{{ label }}</div>
      </div>
    </div>

    <div class="grid-3" v-if="report">
      <el-card shadow="never" class="stat-card">
        <template #header>按提报人</template>
        <el-table :data="report.by_reporter || []" size="small" empty-text="暂无">
          <el-table-column label="成员" min-width="120">
            <template #default="{ row }">{{ memberLabel(row.user_id) }}</template>
          </el-table-column>
          <el-table-column prop="count" label="数量" width="70" />
        </el-table>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <template #header>按处理人</template>
        <el-table :data="report.by_handler || []" size="small" empty-text="暂无">
          <el-table-column label="成员" min-width="120">
            <template #default="{ row }">{{ memberLabel(row.user_id) }}</template>
          </el-table-column>
          <el-table-column prop="count" label="数量" width="70" />
        </el-table>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <template #header>按归属人</template>
        <el-table :data="report.by_attributor || []" size="small" empty-text="暂无">
          <el-table-column label="成员" min-width="120">
            <template #default="{ row }">{{ memberLabel(row.user_id) }}</template>
          </el-table-column>
          <el-table-column prop="count" label="数量" width="70" />
        </el-table>
      </el-card>
    </div>

    <el-card v-if="report" shadow="never" class="detail-card">
      <template #header>
        <span>缺陷明细</span>
        <el-tag v-if="report.limited" size="small" type="info" style="margin-left: 8px">仅展示最近 {{ rows.length }} 条</el-tag>
      </template>
      <div class="resolution-chips" v-if="resolutionEntries.length">
        <span class="chip-label">解决方案分布：</span>
        <el-tag
          v-for="[k, n] in resolutionEntries"
          :key="k"
          size="small"
          effect="plain"
          style="margin-right: 6px"
        >{{ defectResolutionLabel(k) }} {{ n }}</el-tag>
      </div>
      <el-table :data="rows" border stripe size="small" @row-click="openDefect">
        <el-table-column prop="defect_key" label="编号" width="110" />
        <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
        <el-table-column prop="severity" label="严重度" width="90">
          <template #default="{ row }">{{ defectSeverityLabel(row.severity) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">{{ defectStatusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="提报人" width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ memberLabel(row.reporter_id) }}</template>
        </el-table-column>
        <el-table-column label="处理人" width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ memberLabel(row.handler_id || row.assignee_id) }}</template>
        </el-table-column>
        <el-table-column label="归属人" width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ memberLabel(row.attributor_id) }}</template>
        </el-table-column>
        <el-table-column label="解决方案" width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ defectResolutionLabel(row.resolution_type) }}</template>
        </el-table-column>
        <el-table-column prop="create_time" label="创建" width="160">
          <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-empty v-if="!loading && !report" description="暂无报告数据" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { testDefectApi } from '@/api/testManagement'
import { formatMemberName, loadMemberNameMap } from '@/utils/projectMembers'
import {
  DEFECT_SEVERITY_LABELS,
  defectSeverityLabel,
  defectStatusLabel
} from '@/utils/defectDisplay'
import { defectResolutionLabel } from '@/utils/tmDisplay'

const props = defineProps({
  releaseId: { type: Number, required: true },
  projectId: { type: Number, required: true },
  canDefectView: { type: Boolean, default: false }
})

const emit = defineEmits(['open-defect'])

const router = useRouter()
const loading = ref(false)
const report = ref(null)
const memberNames = ref(new Map())

const severityLabels = DEFECT_SEVERITY_LABELS
const rows = computed(() => report.value?.items || [])
const resolutionEntries = computed(() => {
  const m = report.value?.summary?.by_resolution || {}
  return Object.entries(m).sort((a, b) => b[1] - a[1])
})

const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')
const memberLabel = (id) => formatMemberName(id, memberNames.value)

const load = async () => {
  if (!props.projectId || !props.releaseId) return
  loading.value = true
  try {
    memberNames.value = await loadMemberNameMap(props.projectId)
    const res = await testDefectApi.releaseReport(props.releaseId, props.projectId)
    report.value = res.data?.data || null
  } finally {
    loading.value = false
  }
}

const goDefects = () => {
  router.push({ path: '/test-defects', query: { release_id: String(props.releaseId) } })
}

const openDefect = (row) => {
  if (row?.id) emit('open-defect', row)
}

watch(() => [props.releaseId, props.projectId], () => load())
onMounted(load)

defineExpose({ load })
</script>

<style scoped>
.release-defect-report { display: flex; flex-direction: column; gap: 16px; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.card {
  min-width: 100px;
  padding: 12px 16px;
  border-radius: 10px;
  background: #f4f6f9;
  border: 1px solid #e8edf5;
}
.card .num { font-size: 22px; font-weight: 700; color: #1d2939; }
.card .lab { font-size: 12px; color: #667085; margin-top: 4px; }
.card.warn { background: #fff6e6; border-color: #fedf89; }
.card.warn .num { color: #b54708; }
.card.ok { background: #ecfdf3; border-color: #abefc6; }
.card.ok .num { color: #067647; }
.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
@media (max-width: 960px) {
  .grid-3 { grid-template-columns: 1fr; }
}
.stat-card :deep(.el-card__header) { padding: 10px 14px; font-weight: 600; }
.detail-card :deep(.el-card__header) { display: flex; align-items: center; }
.resolution-chips { margin-bottom: 10px; font-size: 13px; }
.chip-label { color: #667085; margin-right: 6px; }
</style>
