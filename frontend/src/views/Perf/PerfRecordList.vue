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
          v-if="selectedRecords.length >= 2 && selectedRecords.length <= 20"
          type="warning"
          @click="openCreateReportDialog"
          :icon="TrendCharts"
        >{{ selectedReportActionLabel }}</el-button>
        <el-button
          v-else-if="selectedRecords.length > 20"
          type="info"
          disabled
        >最多对比 20 条</el-button>
        <el-button link type="primary" @click="router.push('/perf-comparisons')">增强报告列表</el-button>
      </div>

      <!-- 表格 -->
      <el-table :data="tableData" v-loading="loading" stripe @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="scene_name" label="场景名称" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="168" align="center">
          <template #default="{ row }">
            <div class="status-cell">
              <el-tag size="small" :type="getStatusType(row.status)">
                {{
                  row.status === 'running' && row._progress?.phase === 'wind_down'
                    ? '收尾中'
                    : getStatusLabel(row.status)
                }}
              </el-tag>
              <div
                v-if="row.status === 'running' && row._progress"
                class="run-progress"
              >
                <el-progress
                  :percentage="Math.min(100, Math.max(0, Number(row._progress.percentage) || 0))"
                  :stroke-width="14"
                  striped
                  striped-flow
                  :show-text="false"
                  :color="progressBarColor(row._progress.percentage)"
                />
                <div class="run-progress-meta">
                  <span class="run-progress-text">{{ row._progress.text }}</span>
                  <span class="run-progress-pct">{{ Math.min(100, Math.round(Number(row._progress.percentage) || 0)) }}%</span>
                </div>
              </div>
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
  <!-- 生成增强报告 -->
  <el-dialog
    v-model="createReportVisible"
    title="生成增强报告"
    width="640px"
    destroy-on-close
    @closed="resetCreateReportForm"
  >
    <el-form label-width="100px" label-position="left">
      <el-form-item label="报告模式">
        <el-radio-group v-model="createForm.kind">
          <el-radio value="compare">对比</el-radio>
          <el-radio value="merge">汇总</el-radio>
          <el-radio value="hybrid">合并+对比</el-radio>
        </el-radio-group>
        <div class="form-hint">
          <template v-if="createForm.kind === 'compare'">同场景多轮对照，选基准后算变化率与用例对齐。</template>
          <template v-else-if="createForm.kind === 'merge'">分章并排展示，不设基准、不算变化率。</template>
          <template v-else>同场景峰值 vs 持续：分章 + 基准对照。跨场景时仅分章并排，不做基准对照。</template>
        </div>
        <el-alert
          v-if="createForm.kind === 'compare' && selectedIsMerge"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 8px"
          title="当前为跨场景选择：对比变化率仅供参考，更建议改用「汇总」。"
        />
      </el-form-item>
      <el-form-item label="报告标题">
        <el-input v-model="createForm.title" placeholder="可空，自动生成" maxlength="200" clearable />
      </el-form-item>
      <el-form-item v-if="createForm.kind !== 'merge'" label="基准记录">
        <el-select v-model="createForm.referenceId" style="width: 100%">
          <el-option
            v-for="r in selectedRecords"
            :key="r.id"
            :label="`#${r.id} ${createForm.displayNames[r.id] || r.scene_name || ''}`"
            :value="r.id"
          />
        </el-select>
        <div v-if="createForm.kind === 'hybrid' && selectedIsMerge" class="form-hint">
          当前为跨场景选择：生成后不会启用基准变化率（等同分章并排）。如需基准对照请选同场景记录，或改用「对比」。
        </div>
      </el-form-item>
      <el-form-item label="显示名称">
        <div class="rename-list">
          <div v-for="r in selectedRecords" :key="'dn-' + r.id" class="rename-row">
            <span class="rename-id">#{{ r.id }}</span>
            <el-input
              v-model="createForm.displayNames[r.id]"
              :placeholder="r.scene_name || `执行#${r.id}`"
              maxlength="80"
              clearable
            />
          </div>
        </div>
        <div class="form-hint">仅改报告内展示名，不修改执行记录本身。例：瞬间峰值、常规持续。</div>
      </el-form-item>
      <el-form-item label="AI 补充提示">
        <el-input
          v-model="createForm.userExtraPrompt"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          placeholder="可选。整份汇总一份报告即可。例：上传四档(500KB/1MB/5MB/10MB)组内对照；textin 四档组内对照；问答与状态查询单独画像；组间不要硬比。请在同一结论里写清各组数字与规格退化"
        />
        <div class="form-hint">
          是否自动分析取决于项目「压测 AI」开关；所用模型在
          AI 配置 → 场景绑定 →「性能测试报告分析」。
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createReportVisible = false">取消</el-button>
      <el-button type="primary" :loading="compareLoading" @click="submitCreateReport">生成</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="compareDialogVisible" title="报告对比" width="800px" destroy-on-close>
    <div v-if="compareData" v-loading="compareLoading">
      <el-alert
        v-for="(msg, idx) in (compareData.trust?.warnings || [])"
        :key="'trust-' + idx"
        :title="msg"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
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
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Document, VideoPause, Delete, TrendCharts, Top, Bottom, Minus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfRecordApi, perfExecApi, perfComparisonApi } from '@/api'
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

const selectedIsMerge = computed(() => {
  const scenes = new Set(selectedRecords.value.map((r) => r.scene_id))
  return scenes.size > 1
})
const selectedReportActionLabel = computed(() => {
  const n = selectedRecords.value.length
  return `生成增强报告(${n})`
})

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

const progressBarColor = (pct) => {
  const p = Number(pct) || 0
  if (p >= 90) return '#67c23a'
  if (p >= 60) return '#409eff'
  return '#e6a23c'
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
          } else if (
            progress.phase === 'wind_down'
            || Number(progress.current) >= Number(progress.total)
          ) {
            text = `收尾等待 ${progress.current}s/${progress.total}s`
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

// 生成持久化增强报告（2–20 条）
const compareDialogVisible = ref(false)
const compareData = ref(null)
const compareLoading = ref(false)
const createReportVisible = ref(false)
const createForm = ref({
  kind: 'compare',
  title: '',
  referenceId: null,
  displayNames: {},
  userExtraPrompt: ''
})

const openCreateReportDialog = () => {
  const n = selectedRecords.value.length
  if (n < 2 || n > 20) {
    ElMessage.warning('请选择 2–20 条记录生成增强报告')
    return
  }
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先选择项目')
    return
  }
  const names = {}
  for (const r of selectedRecords.value) {
    names[r.id] = ''
  }
  createForm.value = {
    kind: selectedIsMerge.value ? 'merge' : 'compare',
    title: '',
    referenceId: selectedRecords.value[0]?.id ?? null,
    displayNames: names,
    userExtraPrompt: ''
  }
  createReportVisible.value = true
}

const resetCreateReportForm = () => {
  createForm.value = {
    kind: 'compare',
    title: '',
    referenceId: null,
    displayNames: {},
    userExtraPrompt: ''
  }
}

const submitCreateReport = async () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先选择项目')
    return
  }
  const ids = selectedRecords.value.map((r) => r.id)
  if (ids.length < 2) return
  compareLoading.value = true
  try {
    let aiAnalyze = undefined
    try {
      const settings = proStore.projectInfo?.global_vars?.ai_settings
      if (settings?.perf_ai_analysis_enabled) {
        aiAnalyze = settings.perf_ai_analysis_default_on_run === true
      } else {
        aiAnalyze = false
      }
    } catch {
      /* ignore */
    }
    const displayNames = {}
    for (const [k, v] of Object.entries(createForm.value.displayNames || {})) {
      const label = String(v || '').trim()
      if (label) displayNames[k] = label
    }
    const res = await perfComparisonApi.create({
      project_id: proStore.projectInfo.id,
      record_ids: ids,
      reference_record_id: createForm.value.referenceId || ids[0],
      kind: createForm.value.kind,
      title: (createForm.value.title || '').trim() || undefined,
      ...(Object.keys(displayNames).length ? { display_names: displayNames } : {}),
      ...(createForm.value.userExtraPrompt?.trim()
        ? { user_extra_prompt: createForm.value.userExtraPrompt.trim() }
        : {}),
      ...(aiAnalyze !== undefined ? { ai_analyze: aiAnalyze } : {})
    })
    const created = res.data || res
    const reportId = created.id
    if (!reportId) {
      ElMessage.error('创建报告失败：未返回 ID')
      return
    }
    const kind = created.kind || created.snapshot?.kind
    const msg =
      kind === 'merge' ? '汇总报告已生成' : kind === 'hybrid' ? '合并+对比报告已生成' : '对比报告已生成'
    ElMessage.success(msg)
    createReportVisible.value = false
    router.push(`/perf-comparisons/${reportId}`)
  } catch (err) {
    console.error(err)
    const detail = err?.data?.detail || err?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '生成报告失败')
  } finally {
    compareLoading.value = false
  }
}

/** @deprecated 保留即时 2 条预览能力 */
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
    const detail = err?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '对比失败')
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
.status-cell {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  padding: 2px 0;
}
.run-progress {
  width: 100%;
  min-width: 132px;
}
.run-progress :deep(.el-progress-bar__outer) {
  background: #ebeef5;
  border-radius: 999px;
  overflow: hidden;
}
.run-progress :deep(.el-progress-bar__inner) {
  border-radius: 999px;
  transition: width 0.45s ease;
}
.run-progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 3px;
  line-height: 1.2;
  gap: 6px;
}
.run-progress-text {
  font-size: 11px;
  color: #606266;
  font-variant-numeric: tabular-nums;
}
.run-progress-pct {
  font-size: 11px;
  font-weight: 600;
  color: #409eff;
  font-variant-numeric: tabular-nums;
}
.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
.rename-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rename-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rename-id {
  width: 48px;
  flex-shrink: 0;
  font-size: 13px;
  color: #606266;
}
</style>
