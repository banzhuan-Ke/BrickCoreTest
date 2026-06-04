<template>
  <div class="cron-jobs">
    <!-- 头部工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>新建定时任务
        </el-button>
      </div>
      <div class="right">
        <el-button
          v-if="selectedJobs.length > 0"
          type="danger"
          @click="handleBatchDelete"
          icon="Delete"
          style="margin-right: 10px"
        >批量删除({{ selectedJobs.length }})</el-button>
        <el-select v-model="filter.state" placeholder="状态筛选" clearable style="width: 120px; margin-right: 10px">
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button @click="handleSearch">查询</el-button>
      </div>
    </div>

    <!-- 任务列表 -->
    <el-table :data="jobList" v-loading="loading" border @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column type="index" width="50" />
      <el-table-column prop="name" label="任务名称" min-width="150" />
      <el-table-column label="执行目标" min-width="160">
        <template #default="{ row }">
          <el-tag size="small" :type="row.target_type === 'plan' ? 'warning' : 'primary'" style="margin-right:4px">
            {{ row.target_type === 'plan' ? '计划' : '套件' }}
          </el-tag>
          <span>{{ row.target_type === 'plan' ? row.plan_name : row.suite_name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="run_type" label="执行类型" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ getRunTypeText(row.run_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="执行计划" min-width="150">
        <template #default="{ row }">{{ formatSchedule(row) }}</template>
      </el-table-column>
      <el-table-column prop="state" label="状态" width="80">
        <template #default="{ row }">
          <el-switch
            v-model="row.state"
            @change="handleToggle(row)"
            inline-prompt
            active-text="启"
            inactive-text="禁"
          />
        </template>
      </el-table-column>
      <el-table-column label="最近执行" width="130">
        <template #default="{ row }">
          <div v-if="row.last_run_status" class="last-run">
            <el-tag :type="getRunStatusType(row.last_run_status)" size="small">
              {{ getRunStatusText(row.last_run_status) }}
            </el-tag>
            <div class="run-time">{{ formatDate(row.last_run_time) }}</div>
          </div>
          <span v-else style="color: #999">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="create_by" label="创建人" width="100" />
      <el-table-column label="修改人" width="100">
        <template #default="{ row }">{{ row.update_by || row.create_by || '—' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ formatDate(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <div class="table-row-actions">
            <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="handleRunNow(row)">立即执行</el-button>
            <el-button
              v-if="row.last_run_record_id && row.target_type !== 'plan'"
              link
              type="success"
              @click="viewReport(row)"
            >查看报告</el-button>
            <el-popconfirm title="确定删除吗?" @confirm="handleDelete(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
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
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑定时任务' : '新建定时任务'"
      width="620px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="currentRules" label-width="100px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入任务名称" />
        </el-form-item>

        <!-- 目标类型切换 -->
        <el-form-item label="目标类型">
          <el-radio-group v-model="form.target_type" @change="onTargetTypeChange">
            <el-radio-button value="suite">测试套件</el-radio-button>
            <el-radio-button value="plan">测试计划</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 套件选择 -->
        <el-form-item v-if="form.target_type === 'suite'" label="关联套件" prop="suite_id">
          <el-select v-model="form.suite_id" placeholder="选择测试套件" style="width: 100%" filterable>
            <el-option
              v-for="suite in suiteList"
              :key="suite.id"
              :label="suite.name"
              :value="suite.id"
            />
          </el-select>
        </el-form-item>

        <!-- 计划选择 -->
        <el-form-item v-else label="关联计划" prop="plan_id">
          <el-select v-model="form.plan_id" placeholder="选择测试计划" style="width: 100%" filterable>
            <el-option
              v-for="plan in planList"
              :key="plan.id"
              :label="plan.name"
              :value="plan.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="执行环境" prop="env_id">
          <el-select v-model="form.env_id" placeholder="选择执行环境" style="width: 100%">
            <el-option
              v-for="env in proStore.envList"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="执行类型" prop="run_type">
          <el-radio-group v-model="form.run_type">
            <el-radio-button value="Interval">间隔执行</el-radio-button>
            <el-radio-button value="date">固定时间</el-radio-button>
            <el-radio-button value="crontab">Cron表达式</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 间隔执行配置 -->
        <template v-if="form.run_type === 'Interval'">
          <el-form-item label="间隔时间" prop="interval">
            <el-input-number v-model="form.interval" :min="60" :max="86400" style="width: 200px" />
            <span style="margin-left: 10px; color: #666">秒 ({{ formatDuration(form.interval) }})</span>
          </el-form-item>
        </template>

        <!-- 固定时间配置 -->
        <template v-else-if="form.run_type === 'date'">
          <el-form-item label="执行时间" prop="run_date">
            <el-date-picker
              v-model="form.run_date"
              type="datetime"
              placeholder="选择执行时间"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </template>

        <!-- Cron表达式配置 -->
        <template v-else-if="form.run_type === 'crontab'">
          <el-form-item label="分" prop="crontab.minute">
            <el-input v-model="form.crontab.minute" placeholder="*" style="width: 120px" />
          </el-form-item>
          <el-form-item label="时" prop="crontab.hour">
            <el-input v-model="form.crontab.hour" placeholder="*" style="width: 120px" />
          </el-form-item>
          <el-form-item label="日" prop="crontab.day">
            <el-input v-model="form.crontab.day" placeholder="*" style="width: 120px" />
          </el-form-item>
          <el-form-item label="月" prop="crontab.month">
            <el-input v-model="form.crontab.month" placeholder="*" style="width: 120px" />
          </el-form-item>
          <el-form-item label="周" prop="crontab.day_of_week">
            <el-input v-model="form.crontab.day_of_week" placeholder="*" style="width: 120px" />
          </el-form-item>
          <el-form-item>
            <el-alert title="Cron 表达式说明" type="info" :closable="false">
              <template #default>
                <div style="font-size: 13px; line-height: 1.8;">
                  <div><strong>* * * * *</strong> 分别表示：分、时、日、月、周</div>
                  <div style="margin-top: 8px;">
                    <div><strong>分(minute)：</strong>0-59</div>
                    <div><strong>时(hour)：</strong>0-23</div>
                    <div><strong>日(day)：</strong>1-31</div>
                    <div><strong>月(month)：</strong>1-12</div>
                    <div><strong>周(day_of_week)：</strong>0-7（0或7代表星期日）</div>
                  </div>
                  <div style="margin-top: 8px;">
                    <div><code>30 9 * * *</code> 每天上午9:30 &nbsp; <code>*/5 * * * *</code> 每5分钟</div>
                  </div>
                </div>
              </template>
            </el-alert>
          </el-form-item>
        </template>

        <el-form-item label="是否启用">
          <el-switch v-model="form.state" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 执行详情弹窗 -->
    <el-dialog v-model="recordDialogVisible" title="执行详情" width="900px" destroy-on-close>
      <ApiRunDetail :record-id="currentRecordId" v-if="recordDialogVisible" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import { httpPlanApi } from '@/api/modules/http'
import ApiRunDetail from './components/ApiRunDetail.vue'

const route = useRoute()
const proStore = ProjectStore()

const projectId = computed(() => Number(route.params.projectId) || proStore.projectInfo.id)

const loading = ref(false)
const jobList = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)

const filter = reactive({ state: null })

const suiteList = ref([])
const planList = ref([])
const selectedJobs = ref([])

const dialogVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const isEdit = ref(false)
const currentId = ref(null)

const recordDialogVisible = ref(false)
const currentRecordId = ref(null)

const form = reactive({
  name: '',
  target_type: 'suite',  // suite | plan
  suite_id: null,
  plan_id: null,
  env_id: null,
  run_type: 'Interval',
  interval: 3600,
  run_date: '',
  crontab: { minute: '*', hour: '*', day: '*', month: '*', day_of_week: '*' },
  state: false
})

// 动态校验规则，根据 target_type 切换必填项
const currentRules = computed(() => ({
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  suite_id: form.target_type === 'suite'
    ? [{ required: true, message: '请选择套件', trigger: 'change' }]
    : [],
  plan_id: form.target_type === 'plan'
    ? [{ required: true, message: '请选择测试计划', trigger: 'change' }]
    : [],
  env_id: [{ required: true, message: '请选择环境', trigger: 'change' }],
  run_type: [{ required: true, message: '请选择执行类型', trigger: 'change' }]
}))

const onTargetTypeChange = () => {
  form.suite_id = null
  form.plan_id = null
}

// ---- 格式化工具 ----
const formatDate = (date) => date ? new Date(date).toLocaleString() : '-'

const formatDuration = (seconds) => {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时`
  return `${Math.floor(seconds / 86400)}天`
}

const formatSchedule = (row) => {
  if (row.run_type === 'Interval') return `每${formatDuration(row.interval)}`
  if (row.run_type === 'date') return row.run_date || '未设置'
  const c = row.crontab || {}
  return `${c.minute} ${c.hour} ${c.day} ${c.month} ${c.day_of_week}`
}

const getRunTypeText = (runType) => ({ Interval: '间隔执行', date: '固定时间', crontab: 'Cron' }[runType] || runType)
const getRunStatusType = (s) => ({ success: 'success', failed: 'danger', running: 'info' }[s] || 'info')
const getRunStatusText = (s) => ({ success: '成功', failed: '失败', running: '执行中' }[s] || s)

const viewReport = (row) => {
  if (row.last_run_record_id) {
    currentRecordId.value = Number(row.last_run_record_id)
    recordDialogVisible.value = true
  }
}

// ---- 数据加载 ----
const fetchJobs = async () => {
  loading.value = true
  try {
    const params = { project_id: projectId.value, page: page.value, size: size.value }
    if (filter.state !== null) params.state = filter.state
    const res = await http.apiModuleApi.getCronJobList(params)
    jobList.value = res.data?.data || []
    total.value = res.data?.total || 0
  } catch (error) {
    console.error('获取定时任务失败:', error)
  } finally {
    loading.value = false
  }
}

const fetchSuites = async () => {
  try {
    const res = await http.apiModuleApi.getSuiteList({ project_id: projectId.value, page: 1, size: 1000 })
    suiteList.value = res.data?.data || []
  } catch (error) {
    console.error('获取套件列表失败:', error)
  }
}

const fetchPlans = async () => {
  try {
    const res = await httpPlanApi.getList({ project_id: projectId.value, page: 1, size: 1000 })
    planList.value = res.data?.data || []
  } catch (error) {
    console.error('获取计划列表失败:', error)
  }
}

const handleSearch = () => { page.value = 1; fetchJobs() }
const handleSizeChange = (val) => { size.value = val; fetchJobs() }
const handlePageChange = (val) => { page.value = val; fetchJobs() }

const resetForm = () => {
  Object.assign(form, {
    name: '', target_type: 'suite', suite_id: null, plan_id: null,
    env_id: null, run_type: 'Interval', run_date: '', interval: 3600,
    crontab: { minute: '*', hour: '*', day: '*', month: '*', day_of_week: '*' },
    state: false
  })
  isEdit.value = false
  currentId.value = null
}

const handleCreate = () => { resetForm(); dialogVisible.value = true }

const handleEdit = (row) => {
  resetForm()
  isEdit.value = true
  currentId.value = row.id
  Object.assign(form, {
    name: row.name,
    target_type: row.target_type || (row.plan_id ? 'plan' : 'suite'),
    suite_id: row.suite_id || null,
    plan_id: row.plan_id || null,
    env_id: row.env_id,
    run_type: row.run_type,
    interval: row.interval,
    run_date: row.run_date,
    crontab: { ...row.crontab },
    state: row.state
  })
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const data = {
      project_id: projectId.value,
      name: form.name,
      suite_id: form.target_type === 'suite' ? form.suite_id : null,
      plan_id: form.target_type === 'plan' ? form.plan_id : null,
      env_id: form.env_id,
      run_type: form.run_type,
      interval: form.interval,
      run_date: form.run_date || null,
      crontab: form.crontab,
      state: form.state,
    }

    if (isEdit.value) {
      await http.apiModuleApi.updateCronJob(currentId.value, data)
    } else {
      await http.apiModuleApi.createCronJob(data)
    }

    ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
    dialogVisible.value = false
    fetchJobs()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    submitting.value = false
  }
}

const handleToggle = async (row) => {
  try {
    await http.apiModuleApi.toggleCronJob(row.id)
    ElMessage.success('状态更新成功')
  } catch (error) {
    row.state = !row.state
    ElMessage.error('状态更新失败')
  }
}

const handleRunNow = async (row) => {
  try {
    if (row.target_type === 'plan') {
      await httpPlanApi.runPlanAsync(row.plan_id, { env_id: row.env_id })
      ElMessage.success('计划已开始后台执行')
    } else {
      await http.apiModuleApi.runSuiteAsync(row.suite_id, { env_id: row.env_id })
      ElMessage.success('套件已开始后台执行')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '执行失败')
  }
}

const handleDelete = async (row) => {
  try {
    const res = await http.apiModuleApi.deleteCronJob(row.id)
    if (res.status === 200 || res.status === 204) {
      ElMessage.success('删除成功')
      fetchJobs()
    }
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const handleSelectionChange = (selection) => { selectedJobs.value = selection }

const handleBatchDelete = async () => {
  if (selectedJobs.value.length === 0) { ElMessage.warning('请选择要删除的定时任务'); return }
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedJobs.value.length} 个定时任务吗？`, '警告', { type: 'warning' })
    const ids = selectedJobs.value.map(r => r.id)
    await http.apiModuleApi.batchDeleteCronJobs(ids)
    ElMessage.success('批量删除成功')
    selectedJobs.value = []
    fetchJobs()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error('批量删除失败')
  }
}

onMounted(() => {
  fetchJobs()
  fetchSuites()
  fetchPlans()
})
</script>

<style lang="scss" scoped>
.cron-jobs {
  padding: 20px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
.last-run {
  .run-time {
    font-size: 12px;
    color: #999;
    margin-top: 4px;
  }
}

.table-row-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  white-space: nowrap;
  gap: 2px;
}

.table-row-actions :deep(.el-button) {
  margin-left: 0;
  padding: 4px 6px;
}

.table-row-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
