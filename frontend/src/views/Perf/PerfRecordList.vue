<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">📊 性能测试记录</div>
    </template>
    <template #main>
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input
          v-model="sceneNameFilter"
          placeholder="场景名称"
          clearable
          style="width: 160px"
          @keyup.enter="fetchData"
        />
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 120px" @change="fetchData">
          <el-option label="全部" value="" />
          <el-option label="执行中" value="running" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="已停止" value="stopped" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          class="filter-date-range"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          size="small"
          @change="fetchData"
        />
        <el-button type="primary" @click="fetchData" :icon="Refresh">刷新</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button
          v-if="selectedRecords.length > 0"
          type="danger"
          @click="handleBatchDelete"
          :icon="Delete"
        >批量删除({{ selectedRecords.length }})</el-button>
        <el-button
          v-if="selectedRecords.length === 2"
          type="warning"
          @click="handleCompare"
          :icon="TrendCharts"
        >对比</el-button>
      </div>

      <!-- 表格 -->
      <el-table :data="tableData" v-loading="loading" stripe @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="scene_name" label="场景名称" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="140" align="center">
          <template #default="{ row }">
            <div style="display:flex;flex-direction:column;align-items:center;gap:4px">
              <el-tag size="small" :type="getStatusType(row.status)">
                {{ getStatusLabel(row.status) }}
              </el-tag>
              <el-progress
                v-if="row.status === 'running' && row._progress"
                :percentage="row._progress.percentage"
                :stroke-width="10"
                :text-inside="true"
                :format="() => row._progress.text"
                style="width:120px"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="模式" width="80" align="center">
          <template #default="{ row }">
            <div class="mode-cell">
              <el-tag size="small" :type="getModeType(row.mode)">
                {{ getModeLabel(row.mode) }}
              </el-tag>
              <el-tag size="small" :type="row.config_snapshot?.distribution_mode === 'fixed_ratio' ? 'success' : 'info'" style="margin-top: 2px;">
                {{ row.config_snapshot?.distribution_mode === 'fixed_ratio' ? '固定' : '随机' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="并发数" width="75" align="center">
          <template #default="{ row }">
            {{ row.config_snapshot?.concurrent_users || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Ramp-up" width="80" align="center">
          <template #default="{ row }">
            {{ row.config_snapshot?.ramp_up_seconds !== undefined ? row.config_snapshot.ramp_up_seconds + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="持续时间" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.mode === 'fixed'">
              {{ row.config_snapshot?.duration_seconds ? row.config_snapshot.duration_seconds + 's' : '-' }}
            </span>
            <span v-else-if="row.mode === 'loop'">
              {{ row.config_snapshot?.loop_count ? row.config_snapshot.loop_count + '次' : '-' }}
            </span>
            <span v-else-if="row.mode === 'stepping'">
              {{ row.config_snapshot?.steps ? row.config_snapshot.steps.length + '阶段' : '-' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_requests" label="总请求" width="75" align="center" />
        <el-table-column prop="qps" label="QPS" width="70" align="center" />
        <el-table-column label="错误率" width="80" align="center">
          <template #default="{ row }">
            {{ row.error_rate !== undefined ? row.error_rate + '%' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="触发方式" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.trigger_type === 'cron'" type="warning" size="small">定时</el-tag>
            <el-tag v-else type="primary" size="small">手动</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="run_by" label="执行人" width="90" />
        <el-table-column prop="started_at" label="开始时间" width="150" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button
                v-if="row.status === 'running'"
                type="danger"
                size="small"
                :icon="VideoPause"
                @click="handleStop(row)"
              >停止</el-button>
              <el-button
                v-if="row.status !== 'running' && row.status !== 'pending'"
                type="primary"
                size="small"
                :icon="Document"
                @click="handleViewReport(row)"
              >报告</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>
    </template>
  </PageCard>

  <!-- 报告对比弹窗 -->
  <el-dialog v-model="compareDialogVisible" title="报告对比" width="800px" destroy-on-close>
    <div v-if="compareData" v-loading="compareLoading">
      <!-- 基础信息 -->
      <el-table :data="compareData.records" border size="small" style="margin-bottom: 20px">
        <el-table-column label="指标" width="120">
          <template #default="{ $index }">
            <span style="font-weight: bold;">{{ $index === 0 ? '基准记录' : '对比记录' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="场景" min-width="140">
          <template #default="{ row }">
            {{ row.scene_name }}
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="160">
          <template #default="{ row }">
            {{ row.started_at }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="getStatusType(row.status)">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 核心指标对比 -->
      <h4 style="margin-bottom: 12px;">📊 核心指标对比</h4>
      <el-table :data="getCompareRows()" border size="small">
        <el-table-column prop="label" label="指标" width="140" />
        <el-table-column label="基准值" width="160" align="right">
          <template #default="{ row }">
            {{ formatCompareValue(row.key, compareData.records[0]) }}
          </template>
        </el-table-column>
        <el-table-column label="对比值" width="160" align="right">
          <template #default="{ row }">
            {{ formatCompareValue(row.key, compareData.records[1]) }}
          </template>
        </el-table-column>
        <el-table-column label="变化" width="120" align="right">
          <template #default="{ row }">
            <span
              v-if="compareData.changes"
              :style="{ color: row.key === 'qps' || row.key === 'total_requests' ? getQpsChangeColor(compareData.changes[row.key]?.change_pct) : getChangeColor(compareData.changes[row.key]?.change_pct) }"
            >
              {{ compareData.changes[row.key]?.change_pct > 0 ? '+' : '' }}{{ compareData.changes[row.key]?.change_pct }}%
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="趋势" width="80" align="center">
          <template #default="{ row }">
            <template v-if="compareData.changes">
              <el-icon v-if="compareData.changes[row.key]?.change_pct > 0" :size="18" :color="row.key === 'qps' || row.key === 'total_requests' ? '#67c23a' : '#f56c6c'">
                <Top />
              </el-icon>
              <el-icon v-else-if="compareData.changes[row.key]?.change_pct < 0" :size="18" :color="row.key === 'qps' || row.key === 'total_requests' ? '#f56c6c' : '#67c23a'">
                <Bottom />
              </el-icon>
              <el-icon v-else :size="18" color="#909399">
                <Minus />
              </el-icon>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <!-- 响应时间分布对比 -->
      <h4 style="margin: 20px 0 12px;">⏱️ 响应时间分布对比 (ms)</h4>
      <el-table :data="getRtCompareRows()" border size="small">
        <el-table-column prop="label" label="分位" width="100" />
        <el-table-column label="基准值" width="120" align="right">
          <template #default="{ row }">
            {{ compareData.records[0][row.key] ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column label="对比值" width="120" align="right">
          <template #default="{ row }">
            {{ compareData.records[1][row.key] ?? '-' }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Document, VideoPause, Delete, TrendCharts, Top, Bottom, Minus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfRecordApi, perfExecApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'

const router = useRouter()
const proStore = ProjectStore()

const loading = ref(false)
const tableData = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const statusFilter = ref('')
const sceneNameFilter = ref('')
const dateRange = ref(null)
const selectedRecords = ref([])

let pollTimer = null

const getStatusType = (status) => {
  const map = { running: 'warning', success: 'success', failed: 'danger', stopped: 'info', pending: 'info' }
  return map[status] || ''
}

const getStatusLabel = (status) => {
  const map = { running: '执行中', success: '成功', failed: '失败', stopped: '已停止', pending: '等待中' }
  return map[status] || status
}

const getModeType = (mode) => {
  const map = { fixed: 'primary', loop: 'success', stepping: 'warning' }
  return map[mode] || ''
}

const getModeLabel = (mode) => {
  const map = { fixed: '固定', loop: '循环', stepping: '梯度', stream_burst: '流式阶段', sse_burst: '流式阶段' }
  return map[mode] || mode
}

const fetchData = async () => {
  if (!proStore.projectInfo?.id) return
  loading.value = true
  try {
    const params = {
      project_id: proStore.projectInfo.id,
      status: statusFilter.value || undefined,
      scene_name: sceneNameFilter.value || undefined,
      page: page.value,
      size: size.value
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const res = await perfRecordApi.getList(params)
    const data = res.data || res
    tableData.value = data.data || []
    total.value = data.total || 0
    // 对执行中的记录获取实时进度
    await fetchRunningProgress()
  } catch (err) {
    console.error(err)
    ElMessage.error('获取记录列表失败')
  } finally {
    loading.value = false
  }
}

const fetchRunningProgress = async () => {
  const runningRows = tableData.value.filter(r => r.status === 'running')
  if (runningRows.length === 0) return
  await Promise.all(
    runningRows.map(async (row) => {
      try {
        const res = await perfExecApi.getStatus(row.id)
        const progress = (res.data || res).progress
          if (progress) {
          let text = ''
          const countModes = ['loop', 'journey_loop', 'stream_burst', 'sse_burst']
          if (countModes.includes(progress.mode)) {
            text = `${progress.current}/${progress.total}`
          } else {
            text = `${progress.current}s/${progress.total}s`
          }
          row._progress = { ...progress, text }
        }
      } catch (e) {
        // 忽略单个记录的状态查询失败
      }
    })
  )
}

const handleStop = async (row) => {
  try {
    await ElMessageBox.confirm('确定停止当前压测任务吗？', '提示', { type: 'warning' })
    await perfExecApi.stop(row.id)
    ElMessage.success('停止信号已发送')
    fetchData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('停止失败')
    }
  }
}

const handleViewReport = (row) => {
  router.push(`/perf-report/${row.id}`)
}

// 报告对比
const compareDialogVisible = ref(false)
const compareData = ref(null)
const compareLoading = ref(false)

const handleCompare = async () => {
  if (selectedRecords.value.length !== 2) {
    ElMessage.warning('请恰好选择两条记录进行对比')
    return
  }
  compareLoading.value = true
  try {
    const ids = selectedRecords.value.map(r => r.id)
    const res = await perfRecordApi.compare(ids)
    compareData.value = res.data || res
    compareDialogVisible.value = true
  } catch (err) {
    console.error(err)
    ElMessage.error('对比失败')
  } finally {
    compareLoading.value = false
  }
}

const getChangeColor = (pct) => {
  if (pct > 0) return '#f56c6c'  // 红色：上升（QPS上升好，但RT/错误率上升差）
  if (pct < 0) return '#67c23a'  // 绿色：下降
  return '#909399'
}

const getQpsChangeColor = (pct) => {
  if (pct > 0) return '#67c23a'  // QPS上升是好的
  if (pct < 0) return '#f56c6c'
  return '#909399'
}

const handleSelectionChange = (selection) => {
  selectedRecords.value = selection
}

const resetFilters = () => {
  statusFilter.value = ''
  sceneNameFilter.value = ''
  dateRange.value = null
  page.value = 1
  fetchData()
}

const handleBatchDelete = async () => {
  if (selectedRecords.value.length === 0) {
    ElMessage.warning('请选择要删除的记录')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedRecords.value.length} 条记录吗？此操作不可恢复！`,
      '警告',
      { type: 'warning' }
    )
    const ids = selectedRecords.value.map(r => r.id)
    await perfRecordApi.batchDelete(ids)
    ElMessage.success('批量删除成功')
    selectedRecords.value = []
    fetchData()
  } catch (err) {
    if (err !== 'cancel') {
      console.error(err)
      ElMessage.error('批量删除失败')
    }
  }
}

// 轮询执行中的记录
const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    const hasRunning = tableData.value.some(r => r.status === 'running')
    if (hasRunning) {
      fetchData()
    }
  }, 3000)
}

onMounted(() => {
  fetchData()
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

const getCompareRows = () => {
  return [
    { label: 'QPS', key: 'qps' },
    { label: '平均响应时间(ms)', key: 'avg_response_time' },
    { label: '错误率(%)', key: 'error_rate' },
    { label: '总请求数', key: 'total_requests' }
  ]
}

const getRtCompareRows = () => {
  return [
    { label: '最小值', key: 'min_response_time' },
    { label: '最大值', key: 'max_response_time' },
    { label: '中位数', key: 'median_response_time' },
    { label: 'P90', key: 'p90_response_time' },
    { label: 'P95', key: 'p95_response_time' },
    { label: 'P99', key: 'p99_response_time' }
  ]
}

const formatCompareValue = (key, record) => {
  const val = record[key]
  if (val === undefined || val === null) return '-'
  if (key === 'error_rate') return val + '%'
  if (key === 'qps') return val.toFixed(2)
  return val
}
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.toolbar :deep(.filter-date-range) {
  width: 220px;
  max-width: 220px;
  flex: 0 0 auto;
}
.toolbar :deep(.filter-date-range .el-range-editor) {
  width: 100%;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.op-btns {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
}
</style>
