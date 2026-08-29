<template>
  <div class="tm-trace" v-loading="loading">
    <div class="header">
      <h2>追溯矩阵</h2>
      <div class="filters">
        <ReleaseSelect
          v-if="projectId"
          v-model="releaseId"
          :project-id="projectId"
          placeholder="全部版本（可选）"
          width="280px"
        />
        <el-input
          v-model="keyword"
          clearable
          placeholder="需求/用例关键词"
          style="width: 180px"
          @keyup.enter="search"
        />
        <el-select v-model="traceFilter" clearable placeholder="状态" style="width: 120px" @change="search">
          <el-option label="通过" value="green" />
          <el-option label="风险" value="yellow" />
          <el-option label="缺口" value="red" />
        </el-select>
        <el-select v-model="reviewFilter" clearable placeholder="评审" style="width: 120px" @change="search">
          <el-option label="待评" value="pending" />
          <el-option label="通过" value="approved" />
          <el-option label="需改" value="changes_requested" />
          <el-option label="驳回" value="rejected" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button :disabled="!total" :loading="exporting" @click="exportCsv">导出 CSV</el-button>
        <el-button @click="goReleases">版本列表</el-button>
      </div>
    </div>

    <el-card v-if="coverage" class="cov-card" shadow="never">
      <div class="cov-grid">
        <div><span class="label">功能用例</span>{{ coverage.functional_case_total }}</div>
        <div><span class="label">已执行</span>{{ coverage.cases_executed }}</div>
        <div><span class="label">通过</span>{{ coverage.cases_passed }}</div>
        <div><span class="label">未关缺陷项</span>{{ coverage.cases_with_open_defects }}</div>
        <div><span class="label">需求覆盖</span>{{ pct(coverage.requirement_coverage_rate) }}</div>
        <div><span class="label">执行率</span>{{ pct(coverage.execution_rate) }}</div>
      </div>
    </el-card>

    <el-table :data="rows" border stripe row-key="rowKey">
      <el-table-column prop="requirement_name" label="需求" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ row.requirement_name }}</span>
          <el-button
            v-if="row.requirement_id"
            link
            type="primary"
            class="preview-btn"
            @click="openReqPreview(row)"
          >预览</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="test_point_title" label="测试点" width="120" show-overflow-tooltip />
      <el-table-column prop="case_title" label="功能用例" min-width="160" show-overflow-tooltip />
      <el-table-column label="需求评审" width="96">
        <template #default="{ row }">{{ reqReviewLabel(row.requirement_review_status) }}</template>
      </el-table-column>
      <el-table-column label="用例评审" width="90">
        <template #default="{ row }">{{ reviewLabel(row.review_decision) }}</template>
      </el-table-column>
      <el-table-column prop="automation_summary" label="自动化" width="110" show-overflow-tooltip />
      <el-table-column prop="run_result" label="最近执行" width="90" />
      <el-table-column label="未关缺陷" width="90">
        <template #default="{ row }">
          <el-button
            v-if="row.open_defect_count > 0"
            link
            type="danger"
            @click="goDefects(row)"
          >{{ row.open_defect_count }}</el-button>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="traceTagType(row.trace_status)" size="small">
            {{ traceLabel(row.trace_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <template v-if="row.functional_case_id">
            <el-button link type="primary" @click="openCase(row)">打开用例</el-button>
            <el-button link type="success" @click="goExecute(row)">去执行</el-button>
            <el-button
              v-if="row.run_id"
              link
              @click="goRun(row)"
            >运行详情</el-button>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager" v-if="total">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="load"
        @size-change="onSizeChange"
      />
    </div>

    <RequirementPreviewDrawer
      v-model="reqPreviewVisible"
      :ai-requirement-id="previewReqId"
      :project-id="projectId"
      :show-actions="false"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { testTraceApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import ReleaseSelect from './components/ReleaseSelect.vue'
import RequirementPreviewDrawer from './components/RequirementPreviewDrawer.vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const loading = ref(false)
const exporting = ref(false)
const releaseId = ref(route.query.release_id ? Number(route.query.release_id) : null)
const rows = ref([])
const coverage = ref(null)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const keyword = ref('')
const traceFilter = ref('')
const reviewFilter = ref('')

const reqPreviewVisible = ref(false)
const previewReqId = ref(null)

const projectId = computed(() => proStore.projectInfo?.id)

const openReqPreview = (row) => {
  if (!row?.requirement_id) return
  previewReqId.value = Number(row.requirement_id)
  reqPreviewVisible.value = true
}

const pct = (v) => (v != null ? `${Math.round(Number(v) * 100)}%` : '—')
const traceLabel = (s) => ({ green: '通过', yellow: '风险', red: '缺口' }[s] || s)
const traceTagType = (s) => ({ green: 'success', yellow: 'warning', red: 'danger' }[s] || 'info')
const reviewLabel = (s) =>
  ({
    approved: '通过',
    pending: '待评',
    rejected: '驳回',
    changes_requested: '需改',
    in_review: '评审中'
  }[s] || s || '—')

const reqReviewLabel = (s) =>
  ({
    approved: '已通过',
    pending: '待评审',
    rejected: '已驳回',
    changes_requested: '需修改',
    in_review: '评审中'
  }[s] || s || '—')

const csvEscape = (v) => {
  const s = String(v ?? '')
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

const matrixParams = (extra = {}) => ({
  page: page.value,
  size: pageSize.value,
  keyword: keyword.value.trim() || undefined,
  trace_status: traceFilter.value || undefined,
  review_decision: reviewFilter.value || undefined,
  ...extra
})

const exportCsv = async () => {
  if (!projectId.value) return
  exporting.value = true
  try {
    const res = await testTraceApi.matrix(projectId.value, releaseId.value, {
      ...matrixParams({ all_rows: true })
    })
    const data = res.data?.data || {}
    const list = data.rows || []
    const header = ['需求', '测试点', '功能用例', '需求评审', '用例评审', '自动化', '最近执行', '未关缺陷', '状态']
    const lines = [header.join(',')]
    for (const r of list) {
      lines.push(
        [
          r.requirement_name,
          r.test_point_title,
          r.case_title,
          reqReviewLabel(r.requirement_review_status),
          reviewLabel(r.review_decision),
          r.automation_summary,
          r.run_result,
          r.open_defect_count,
          traceLabel(r.trace_status)
        ]
          .map(csvEscape)
          .join(',')
      )
    }
    const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `traceability-${releaseId.value || 'all'}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${list.length} 行`)
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

const load = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const res = await testTraceApi.matrix(projectId.value, releaseId.value, matrixParams())
    const data = res.data?.data || {}
    rows.value = data.rows || []
    total.value = data.pagination?.total ?? rows.value.length
    const covRes = await testTraceApi.coverage(projectId.value, releaseId.value)
    coverage.value = covRes.data?.data?.coverage || data.coverage || null
    if (coverage.value && covRes.data?.data?.coverage) {
      // coverage endpoint includes rates
      coverage.value = covRes.data.data.coverage
    }
  } finally {
    loading.value = false
  }
}

const search = () => {
  page.value = 1
  load()
}

const onSizeChange = () => {
  page.value = 1
  load()
}

const goReleases = () => router.push('/test-releases')
const goDefects = (row) => {
  const query = {}
  if (releaseId.value) query.release_id = String(releaseId.value)
  if (row?.functional_case_id) query.case_id = String(row.functional_case_id)
  router.push({ path: '/test-defects', query })
}
const openCase = (row) => {
  if (!row.functional_case_id) return
  router.push({
    path: '/ai-functional-cases',
    query: { case_id: String(row.functional_case_id) }
  })
}
const goRun = (row) => {
  if (!row.run_id) return
  router.push(`/test-plan-runs/${row.run_id}`)
}
const goExecute = (row) => {
  if (row.run_id) {
    goRun(row)
    return
  }
  if (releaseId.value) {
    router.push({
      path: `/test-releases/${releaseId.value}`,
      query: { tab: 'plans' }
    })
    return
  }
  ElMessage.info('请先选择版本，再进入版本「测试计划」执行；或先打开用例纳入版本')
  openCase(row)
}

watch(projectId, () => {
  page.value = 1
  load()
})
watch(
  () => route.query.release_id,
  (v) => {
    const next = v ? Number(v) : null
    if (next === releaseId.value) return
    releaseId.value = next
  }
)
watch(releaseId, () => {
  page.value = 1
  load()
})
onMounted(load)
</script>

<style scoped>
.tm-trace { padding: 16px; }
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.header h2 { margin: 0; font-size: 20px; }
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.cov-card { margin-bottom: 12px; }
.cov-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 24px;
}
.cov-grid .label { color: #909399; margin-right: 6px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.muted { color: #c0c4cc; }
.preview-btn {
  margin-left: 4px;
}
</style>
