<template>
  <div class="plan-list">
    <CatalogListLayout
      :project-id="proStore.projectInfo.id"
      v-model="catalogId"
      all-node-label="全部计划"
      @change="handleSearch"
    >
    <!-- 汇总统计 -->
    <div class="plan-stats" v-if="summary">
      <div class="stat-card">
        <div class="stat-value">{{ summary.plan_count }}</div>
        <div class="stat-label">计划数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.total_items }}</div>
        <div class="stat-label">计划条目</div>
        <div class="stat-sub">套件 {{ summary.suite_items }} · 用例 {{ summary.case_items }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.parallel_plans }} / {{ summary.serial_plans }}</div>
        <div class="stat-label">并行 / 串行</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.total_runs }}</div>
        <div class="stat-label">累计执行</div>
        <div class="stat-sub">近7天 {{ summary.runs_7d }} 次</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" :class="successRateClass(summary.run_success_rate)">
          {{ formatSuccessRate(summary.run_success_rate) }}
        </div>
        <div class="stat-label">执行成功率</div>
        <div class="stat-sub" v-if="summary.run_finished_count">
          {{ summary.run_success_count }}/{{ summary.run_finished_count }} 次完成
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ summary.cron_enabled_count }} / {{ summary.cron_job_count }}</div>
        <div class="stat-label">定时任务(启用/总数)</div>
      </div>
      <div class="stat-card" v-if="summary.uncataloged_plans > 0">
        <div class="stat-value warn">{{ summary.uncataloged_plans }}</div>
        <div class="stat-label">未归类计划</div>
      </div>
    </div>

    <!-- 头部工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>新建计划
        </el-button>
        <el-button @click="openFromTemplateDialog">
          <el-icon><DocumentCopy /></el-icon>从模板创建
        </el-button>
      </div>
      <div class="right">
        <el-button
          v-if="selectedPlans.length > 0"
          type="danger"
          @click="handleBatchDelete"
          style="margin-right: 10px"
        >
          <el-icon><Delete /></el-icon>批量删除({{ selectedPlans.length }})
        </el-button>
        <el-input
          v-model="keyword"
          placeholder="搜索计划名称"
          style="width: 200px"
          clearable
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #suffix>
            <el-icon style="cursor: pointer" @click="handleSearch"><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </div>

    <!-- 计划列表 -->
    <el-table
      :data="planList"
      v-loading="loading"
      border
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column type="index" width="60" align="center" />
      <el-table-column label="计划名称" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link type="primary" @click="handleEdit(row)">{{ row.name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="所属目录" width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.catalog_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="条目" width="110" align="center">
        <template #default="{ row }">
          <span>{{ row.item_count ?? 0 }}</span>
          <span class="item-breakdown" v-if="row.item_count">
            (套{{ row.suite_item_count ?? 0 }}/例{{ row.case_item_count ?? 0 }})
          </span>
        </template>
      </el-table-column>
      <el-table-column label="执行模式" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.parallel ? 'warning' : 'info'">
            {{ row.parallel ? '并行' : '串行' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认环境" width="130" show-overflow-tooltip>
        <template #default="{ row }">{{ getEnvName(row.env_id) || '—' }}</template>
      </el-table-column>
      <el-table-column label="最近执行" width="150" align="center">
        <template #default="{ row }">
          <template v-if="row.last_run_time">
            <el-tag size="small" :type="row.last_run_status === 'success' ? 'success' : row.last_run_status === 'running' ? 'warning' : 'danger'">
              {{ lastRunStatusLabel(row.last_run_status) }}
            </el-tag>
            <div class="last-run-time">{{ formatDate(row.last_run_time) }}</div>
          </template>
          <span v-else class="text-muted">未执行</span>
        </template>
      </el-table-column>
      <el-table-column label="执行次数" width="88" align="center" prop="run_count" />
      <el-table-column label="定时任务" width="88" align="center">
        <template #default="{ row }">
          <span v-if="row.cron_job_count">{{ row.cron_enabled_count }}/{{ row.cron_job_count }}</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '—' }}</template>
      </el-table-column>
      <el-table-column prop="create_by" label="创建人" width="100" />
      <el-table-column label="修改人" width="100">
        <template #default="{ row }">{{ row.update_by || row.create_by || '—' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ formatDate(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <div class="plan-actions">
            <el-button link type="warning" :loading="runningId === row.id" @click="handleRun(row)">
              <el-icon><VideoPlay /></el-icon>执行
            </el-button>
            <el-button link type="primary" @click="handleEdit(row)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button link type="success" @click="handleViewRecords(row)">
              <el-icon><Document /></el-icon>报告
            </el-button>
            <el-button link type="info" @click="handleSaveAsTemplate(row)">存模板</el-button>
            <el-popconfirm title="确定删除该计划吗?" @confirm="handleDelete(row)">
              <template #reference>
                <el-button link type="danger">
                  <el-icon><Delete /></el-icon>删除
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>
    </CatalogListLayout>

    <!-- 执行历史记录弹窗 -->
    <!-- 执行确认弹窗 -->
    <el-dialog v-model="runDialogVisible" title="执行测试计划" width="400px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="执行计划">
          <span style="font-weight:500">{{ runTarget?.name }}</span>
        </el-form-item>
        <el-form-item label="选择环境">
          <el-select v-model="runEnvId" placeholder="请选择环境" style="width:100%">
            <el-option
              v-for="env in proStore.envList"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="runningId !== null" :disabled="!runEnvId" @click="confirmRun">
          开始执行
        </el-button>
      </template>
    </el-dialog>

    <!-- 从模板创建 -->
    <el-dialog v-model="templateDialogVisible" title="从模板创建计划" width="480px">
      <el-form label-width="90px">
        <el-form-item label="选择模板">
          <el-select v-model="templateForm.templateId" placeholder="请选择模板" style="width:100%" filterable>
            <el-option v-for="t in templateList" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划名称">
          <el-input v-model="templateForm.name" placeholder="新计划名称" />
        </el-form-item>
        <el-form-item label="默认环境">
          <el-select v-model="templateForm.envId" placeholder="可选" style="width:100%" clearable>
            <el-option v-for="env in proStore.envList" :key="env.id" :label="env.name" :value="env.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="templateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="templateCreating" @click="confirmCreateFromTemplate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 轮询执行状态提示弹窗 -->
    <el-dialog
      v-model="pollingDialogVisible"
      title="计划执行中"
      width="400px"
      :close-on-click-modal="false"
      :show-close="false"
    >
      <div style="text-align:center; padding: 20px 0">
        <el-icon class="is-loading" style="font-size:40px; color:#409eff; margin-bottom:16px"><Loading /></el-icon>
        <div style="font-size:15px; color:#333; margin-bottom:8px">「{{ pollingPlanName }}」执行中，请稍候…</div>
        <div style="font-size:12px; color:#999">计划已在后台运行，关闭页面不影响执行</div>
      </div>
      <template #footer>
        <el-button @click="stopPollingAndClose">后台继续，关闭此窗口</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="recordsDialogVisible"
      :title="`执行报告 — ${currentPlanName}`"
      width="900px"
      destroy-on-close
    >
      <div class="records-toolbar">
        <el-radio-group v-model="recordFilter" @change="fetchRecords">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="success">成功</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
      </div>

      <el-table :data="recordList" v-loading="recordsLoading" border size="small" style="margin-top:12px">
        <el-table-column type="index" width="50" align="center" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '通过' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发方式" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.trigger_type === 'cron' ? 'warning' : row.trigger_type === 'assistant' ? 'success' : 'info'"
              size="small"
            >
              {{ row.trigger_type === 'cron' ? '定时' : row.trigger_type === 'assistant' ? '小测' : '手动' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="通过/总计" width="100" align="center">
          <template #default="{ row }">
            <span :style="row.failed_cases > 0 ? 'color:#f56c6c' : 'color:#67c23a'">
              {{ row.success_cases }}/{{ row.total_cases }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="耗时(ms)" prop="duration" width="90" align="center" />
        <el-table-column label="环境" prop="env_name" width="110" show-overflow-tooltip />
        <el-table-column label="执行人" prop="run_by" width="90" />
        <el-table-column label="执行时间" width="160">
          <template #default="{ row }">{{ formatDate(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleViewRecordDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination" style="margin-top:12px">
        <el-pagination
          v-model:current-page="recordPage"
          v-model:page-size="recordSize"
          :total="recordTotal"
          :page-sizes="[10, 20]"
          layout="total, sizes, prev, pager, next"
          small
          @size-change="fetchRecords"
          @current-change="fetchRecords"
        />
      </div>
    </el-dialog>

    <!-- 执行记录详情弹窗 -->
    <el-dialog
      v-model="recordDetailVisible"
      title="执行详情"
      width="800px"
      destroy-on-close
    >
      <div v-if="currentRecord" class="record-detail">
        <!-- 统计行 -->
        <el-row :gutter="16" class="stat-row">
          <el-col :span="6"><el-statistic title="总用例" :value="currentRecord.total_cases" /></el-col>
          <el-col :span="6"><el-statistic title="成功" :value="currentRecord.success_cases" value-style="color:#67c23a" /></el-col>
          <el-col :span="6"><el-statistic title="失败" :value="currentRecord.failed_cases" value-style="color:#f56c6c" /></el-col>
          <el-col :span="6"><el-statistic title="耗时(ms)" :value="currentRecord.duration" /></el-col>
        </el-row>
        <el-divider />
        <!-- Item 结果表格 -->
        <el-table :data="currentRecord.item_results" border size="small">
          <el-table-column label="序号" type="index" width="55" align="center" />
          <el-table-column label="类型" width="70" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.item_type === 'suite' ? 'primary' : 'info'">
                {{ row.item_type === 'suite' ? '套件' : '用例' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="名称" prop="name" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'success' ? 'success' : row.status === 'skipped' ? 'warning' : 'danger'">
                {{ row.status === 'success' ? '通过' : row.status === 'skipped' ? '跳过' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="通过/总计" width="95" align="center">
            <template #default="{ row }">
              <span :style="row.failed > 0 ? 'color:#f56c6c' : 'color:#67c23a'">
                {{ row.success }}/{{ row.total }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="耗时(ms)" prop="duration" width="90" align="center" />
          <el-table-column label="备注" prop="error" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.error" style="color:#f56c6c">{{ row.error }}</span>
              <span v-else style="color:#999">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Edit, Search, Document, VideoPlay, Loading, DocumentCopy } from '@element-plus/icons-vue'
import { httpPlanApi } from '@/api/modules/http'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogListLayout from '@/components/CatalogListLayout.vue'

const emptySummary = () => ({
  plan_count: 0,
  total_items: 0,
  suite_items: 0,
  case_items: 0,
  parallel_plans: 0,
  serial_plans: 0,
  uncataloged_plans: 0,
  total_runs: 0,
  runs_7d: 0,
  run_success_count: 0,
  run_finished_count: 0,
  run_success_rate: null,
  cron_job_count: 0,
  cron_enabled_count: 0,
})

const router = useRouter()
const proStore = ProjectStore()

// 列表数据
const planList = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const size = ref(20)
const keyword = ref('')
const catalogId = ref(null)
const selectedPlans = ref([])
const summary = ref(emptySummary())

const formatSuccessRate = (rate) => {
  if (rate == null || summary.value.run_finished_count === 0) return '—'
  return `${rate}%`
}

const successRateClass = (rate) => {
  if (rate == null) return ''
  if (rate >= 90) return 'rate-good'
  if (rate >= 70) return 'rate-warn'
  return 'rate-bad'
}

const lastRunStatusLabel = (status) => {
  const map = { success: '通过', failed: '失败', running: '执行中' }
  return map[status] || status || '—'
}

// 获取环境名称
const getEnvName = (env_id) => {
  if (!env_id) return ''
  const env = proStore.envList.find(e => e.id === env_id)
  return env ? env.name : `环境${env_id}`
}

// 格式化时间
const formatDate = (dateStr) => {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-')
}

// 获取计划列表
const fetchPlans = async () => {
  if (!proStore.projectInfo?.id) return
  loading.value = true
  try {
    const res = await httpPlanApi.getList({
      project_id: proStore.projectInfo.id,
      keyword: keyword.value || undefined,
      catalog_id: catalogId.value || undefined,
      page: page.value,
      size: size.value,
    })
    if (res.data) {
      planList.value = res.data.data || []
      total.value = res.data.total || 0
      summary.value = res.data.summary ? { ...emptySummary(), ...res.data.summary } : emptySummary()
    }
  } catch (e) {
    ElMessage.error('获取计划列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => { page.value = 1; fetchPlans() }
const handleSizeChange = (val) => { size.value = val; page.value = 1; fetchPlans() }
const handlePageChange = (val) => { page.value = val; fetchPlans() }
const handleSelectionChange = (val) => { selectedPlans.value = val }

const handleCreate = () => router.push('/api-plan/new')
const handleEdit = (row) => router.push(`/api-plan/${row.id}`)

const templateDialogVisible = ref(false)
const templateCreating = ref(false)
const templateList = ref([])
const templateForm = reactive({ templateId: null, name: '', envId: null })

const loadTemplates = async () => {
  if (!proStore.projectInfo?.id) return
  const res = await httpPlanApi.getTemplates({
    project_id: proStore.projectInfo.id,
    page: 1,
    size: 200,
  })
  templateList.value = res.data?.data || []
}

const openFromTemplateDialog = async () => {
  templateForm.templateId = null
  templateForm.name = ''
  templateForm.envId = null
  await loadTemplates()
  if (!templateList.value.length) {
    ElMessage.info('暂无计划模板，可先在计划操作列点击「存模板」')
    return
  }
  templateDialogVisible.value = true
}

const confirmCreateFromTemplate = async () => {
  if (!templateForm.templateId || !templateForm.name?.trim()) {
    ElMessage.warning('请选择模板并填写计划名称')
    return
  }
  templateCreating.value = true
  try {
    const res = await httpPlanApi.createFromTemplate(templateForm.templateId, {
      name: templateForm.name.trim(),
      project_id: proStore.projectInfo.id,
      env_id: templateForm.envId || undefined,
    })
    ElMessage.success('已从模板创建计划')
    templateDialogVisible.value = false
    if (res.data?.id) router.push(`/api-plan/${res.data.id}`)
    else fetchPlans()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    templateCreating.value = false
  }
}

const handleSaveAsTemplate = async (row) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入模板名称', '另存为模板', {
      inputValue: `${row.name}-模板`,
      confirmButtonText: '保存',
    })
    if (!value?.trim()) return
    await httpPlanApi.saveAsTemplate(row.id, { name: value.trim() })
    ElMessage.success('模板已保存')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

const handleDelete = async (row) => {
  try {
    await httpPlanApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchPlans()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

const handleBatchDelete = async () => {
  if (selectedPlans.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedPlans.value.length} 个计划吗？`, '批量删除', { type: 'warning' })
    const ids = selectedPlans.value.map(p => p.id)
    await httpPlanApi.batchDelete(ids)
    ElMessage.success(`已删除 ${ids.length} 个计划`)
    selectedPlans.value = []
    fetchPlans()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('批量删除失败')
  }
}

// ====== 执行计划（异步后台执行 + 轮询）======
const runDialogVisible = ref(false)
const runTarget = ref(null)
const runEnvId = ref(null)
const runningId = ref(null)

// 轮询相关
const pollingDialogVisible = ref(false)
const pollingPlanName = ref('')
const pollingRecordId = ref(null)
const pollingTimer = ref(null)

const handleRun = (row) => {
  runTarget.value = row
  runEnvId.value = row.env_id || (proStore.envList[0]?.id ?? null)
  runDialogVisible.value = true
}

const confirmRun = async () => {
  if (!runEnvId.value) { ElMessage.warning('请选择执行环境'); return }
  runningId.value = runTarget.value.id
  try {
    // 调用异步接口，立即拿到 record_id
    const res = await httpPlanApi.runPlanAsync(runTarget.value.id, { env_id: runEnvId.value })
    const data = res.data
    runDialogVisible.value = false
    pollingRecordId.value = data.record_id
    pollingPlanName.value = runTarget.value.name
    pollingDialogVisible.value = true
    ElMessage.info('计划已开始后台执行，请稍候…')
    startPolling()
  } catch (e) {
    ElMessage.error('执行失败：' + (e.response?.data?.detail || e.message))
  } finally {
    runningId.value = null
  }
}

const startPolling = () => {
  pollingTimer.value = setInterval(async () => {
    try {
      // 复用 getPlanRecordDetail 接口轮询状态
      const planId = runTarget.value?.id
      if (!planId || !pollingRecordId.value) return
      const res = await httpPlanApi.getPlanRecordDetail(planId, pollingRecordId.value)
      const data = res.data
      if (data.status !== 'running') {
        stopPolling()
        pollingDialogVisible.value = false
        const total = data.total_cases ?? 0
        const success = data.success_cases ?? 0
        const failed = data.failed_cases ?? 0
        ElMessage({
          type: failed > 0 ? 'warning' : 'success',
          message: `「${pollingPlanName.value}」执行完成：共 ${total} 条，通过 ${success}，失败 ${failed}`,
          duration: 5000
        })
        fetchPlans()
      }
    } catch (err) {
      console.error('轮询计划状态失败:', err)
    }
  }, 3000)
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

const stopPollingAndClose = () => {
  stopPolling()
  pollingDialogVisible.value = false
  ElMessage.info('计划仍在后台执行，可在"报告"中查看结果')
}

onUnmounted(() => stopPolling())

// ====== 执行报告 ======
const recordsDialogVisible = ref(false)
const recordsLoading = ref(false)
const recordList = ref([])
const recordTotal = ref(0)
const recordPage = ref(1)
const recordSize = ref(10)
const recordFilter = ref('')
const currentPlanId = ref(null)
const currentPlanName = ref('')

const handleViewRecords = (row) => {
  currentPlanId.value = row.id
  currentPlanName.value = row.name
  recordPage.value = 1
  recordFilter.value = ''
  recordsDialogVisible.value = true
  fetchRecords()
}

const fetchRecords = async () => {
  if (!currentPlanId.value) return
  recordsLoading.value = true
  try {
    const params = { page: recordPage.value, size: recordSize.value }
    if (recordFilter.value) params.status = recordFilter.value
    const res = await httpPlanApi.getPlanRecords(currentPlanId.value, params)
    if (res.data) {
      recordList.value = res.data.data || []
      recordTotal.value = res.data.total || 0
    }
  } catch (e) {
    ElMessage.error('获取执行记录失败')
  } finally {
    recordsLoading.value = false
  }
}

// 执行记录详情
const recordDetailVisible = ref(false)
const currentRecord = ref(null)

const handleViewRecordDetail = async (row) => {
  try {
    const res = await httpPlanApi.getPlanRecordDetail(currentPlanId.value, row.id)
    currentRecord.value = res.data
    recordDetailVisible.value = true
  } catch (e) {
    ElMessage.error('获取详情失败')
  }
}

onMounted(() => {
  proStore.getCatalogList()
  fetchPlans()
})
</script>

<style scoped>
.plan-list {
  padding: 16px;
}

.plan-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.stat-card {
  flex: 1;
  min-width: 118px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  text-align: center;

  .stat-value {
    font-size: 20px;
    font-weight: 600;
    color: var(--el-color-primary);
    line-height: 1.2;

    &.rate-good { color: var(--el-color-success); }
    &.rate-warn { color: var(--el-color-warning); }
    &.rate-bad { color: var(--el-color-danger); }
    &.warn { color: var(--el-color-warning); }
  }

  .stat-label {
    margin-top: 4px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .stat-sub {
    margin-top: 2px;
    font-size: 11px;
    color: var(--el-text-color-placeholder);
  }
}

.item-breakdown {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.last-run-time {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.2;
}

.text-muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar .left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar .right {
  display: flex;
  align-items: center;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.records-toolbar {
  display: flex;
  justify-content: flex-end;
}
.stat-row {
  margin-bottom: 8px;
}
.record-detail {
  padding: 4px 0;
}

.plan-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  white-space: nowrap;
  gap: 2px;
}

.plan-actions :deep(.el-button) {
  margin-left: 0;
  padding: 4px 6px;
}

.plan-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
