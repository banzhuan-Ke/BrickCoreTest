<template>
  <div class="perf-cron-jobs">
    <!-- 头部工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>新建定时压测
        </el-button>
      </div>
      <div class="right">
        <el-select v-model="filter.run_type" placeholder="任务类型" clearable style="width: 130px; margin-right: 10px">
          <el-option label="间隔执行" value="Interval" />
          <el-option label="固定时间" value="date" />
          <el-option label="Cron表达式" value="crontab" />
        </el-select>
        <el-select v-model="filter.state" placeholder="状态筛选" clearable style="width: 120px; margin-right: 10px">
          <el-option label="启用" :value="true" />
          <el-option label="禁用" :value="false" />
        </el-select>
        <el-button @click="handleSearch">查询</el-button>
      </div>
    </div>
    
    <!-- 任务列表 -->
    <el-table :data="jobList" v-loading="loading" border>
      <el-table-column type="index" :index="tableRowIndex" width="50" />
      <el-table-column prop="name" label="任务名称" min-width="150" />
      <el-table-column prop="scene_name" label="关联场景" min-width="150" />
      <el-table-column prop="env_name" label="执行环境" width="120" />
      <el-table-column label="执行方式" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.use_workers !== false" type="warning" size="small">Worker</el-tag>
          <el-tag v-else type="info" size="small">历史·本机</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="任务类型" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.run_type === 'Interval'" type="primary">间隔执行</el-tag>
          <el-tag v-else-if="row.run_type === 'date'" type="info">固定时间</el-tag>
          <el-tag v-else-if="row.run_type === 'crontab'" type="success">Cron表达式</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="执行策略" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.run_type === 'Interval'">每 {{ row.interval }} 秒执行一次</span>
          <span v-else-if="row.run_type === 'date'">固定执行时间：{{ formatDate(row.run_date) }}</span>
          <span v-else-if="row.run_type === 'crontab'">
            <code>{{ formatCron(row.crontab) }}</code>
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="state" label="状态" width="90">
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
      <el-table-column label="最近执行" width="160">
        <template #default="{ row }">
          <div v-if="row.last_run_record_id" class="last-run">
            <el-tag :type="getRunStatusType(row.last_run_status)" size="small">
              {{ getRunStatusText(row.last_run_status) }}
            </el-tag>
            <div class="run-time">{{ formatDate(row.last_run_time) }}</div>
          </div>
          <span v-else style="color: #999">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="create_by" label="创建人" width="100" />
      <el-table-column prop="create_time" label="创建时间" width="160">
        <template #default="{ row }">
          {{ formatDate(row.create_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
          <el-button 
            v-if="row.last_run_record_id" 
            link 
            type="success" 
            @click="viewReport(row)"
          >查看报告</el-button>
          <el-button link type="info" @click="handleShowRecords(row)">执行记录</el-button>
          <el-popconfirm title="确定删除吗?" @confirm="handleDelete(row)">
            <template #reference>
              <el-button link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
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
      :title="isEdit ? '编辑定时压测' : '新建定时压测'"
      width="650px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入任务名称" />
        </el-form-item>
        
        <el-form-item label="关联场景" prop="scene_id">
          <el-select v-model="form.scene_id" placeholder="选择性能场景" style="width: 100%">
            <el-option
              v-for="scene in sceneList"
              :key="scene.id"
              :label="scene.name"
              :value="scene.id"
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
        
        <!-- 执行类型 -->
        <el-form-item label="执行类型" prop="run_type">
          <el-radio-group v-model="form.run_type">
            <el-radio-button label="Interval">间隔执行</el-radio-button>
            <el-radio-button label="date">固定时间</el-radio-button>
            <el-radio-button label="crontab">Cron表达式</el-radio-button>
          </el-radio-group>
        </el-form-item>
        
        <!-- 间隔执行 -->
        <template v-if="form.run_type === 'Interval'">
          <el-form-item label="间隔时间" prop="interval">
            <el-input-number v-model="form.interval" :min="60" :step="60" style="width: 150px" />
            <span style="margin-left: 10px; color: #666;">秒</span>
            <span v-if="form.interval >= 60" style="margin-left: 10px; color: #909399;">
              ({{ Math.floor(form.interval / 60) }} 分钟)
            </span>
          </el-form-item>
        </template>
        
        <!-- 固定时间 -->
        <template v-if="form.run_type === 'date'">
          <el-form-item label="执行时间" prop="run_date">
            <el-date-picker
              v-model="form.run_date"
              type="datetime"
              placeholder="选择执行时间"
              value-format="YYYY-MM-DD HH:mm:ss"
              style="width: 220px"
            />
          </el-form-item>
        </template>
        
        <!-- Cron表达式 -->
        <template v-if="form.run_type === 'crontab'">
          <el-form-item label="表达式" prop="crontabStr">
            <el-input v-model="form.crontabStr" placeholder="分 时 日 月 周，如：0 2 * * *" style="width: 260px" />
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
                  <div style="margin-top: 10px;"><strong>配置案例：</strong></div>
                  <div style="margin-top: 5px;">
                    <div><code>0 2 * * *</code> 每天凌晨2:00执行</div>
                    <div><code>0 */6 * * *</code> 每6小时执行一次</div>
                    <div><code>0 9 * * 1</code> 每周一上午9:00执行</div>
                    <div><code>0 0 1 * *</code> 每月1号执行</div>
                  </div>
                </div>
              </template>
            </el-alert>
          </el-form-item>
        </template>
        
        <el-form-item label="是否启用">
          <el-switch v-model="form.state" />
        </el-form-item>

        <el-form-item label="压测 Worker">
          <el-switch v-model="form.use_workers" disabled />
          <div style="margin-top: 6px; color: #909399; font-size: 12px; line-height: 1.6;">
            压测施压一律由在线 Runner Worker 执行；后端不再本机直跑。请确保任务触发时有可用执行机。
          </div>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 执行记录弹窗 -->
    <el-dialog
      v-model="recordDialogVisible"
      :title="`定时任务执行记录 - ${selectedJob?.name || ''}`"
      width="85%"
      center
      destroy-on-close
    >
      <el-table :data="recordList" v-loading="recordLoading" border stripe>
        <el-table-column type="index" :index="recordTableRowIndex" width="60" />
        <el-table-column prop="scene_name" label="场景名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="getRunStatusType(row.status)" size="small">
              {{ getRunStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发方式" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.trigger_type === 'cron'" type="warning" size="small">定时</el-tag>
            <el-tag v-else type="primary" size="small">手动</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_requests" label="总请求" width="90" />
        <el-table-column prop="success_count" label="成功" width="70">
          <template #default="{ row }">
            <span style="color: var(--el-color-success); font-weight: bold;">{{ row.success_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fail_count" label="失败" width="70">
          <template #default="{ row }">
            <span style="color: var(--el-color-danger); font-weight: bold;">{{ row.fail_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="qps" label="QPS" width="90" />
        <el-table-column prop="avg_response_time" label="平均RT(ms)" width="110" />
        <el-table-column prop="error_rate" label="错误率" width="90">
          <template #default="{ row }">
            <span :style="{ color: row.error_rate > 5 ? '#f56c6c' : '#67c23a' }">{{ row.error_rate }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="run_by" label="执行人" width="90" />
        <el-table-column prop="started_at" label="开始时间" width="160">
          <template #default="{ row }">{{ formatDate(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="duration" label="耗时" width="90">
          <template #default="{ row }">{{ row.duration }} 秒</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="viewRecordReport(row)">报告</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <el-pagination
            v-model:current-page="recordPage.page"
            v-model:page-size="recordPage.size"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            :total="recordPage.total"
            @current-change="fetchJobRecords"
            @size-change="fetchJobRecords"
          />
          <el-button @click="recordDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { perfCronApi, perfSceneApi, perfRecordApi } from '@/api/modules/perf'
import { makeTableRowIndex, makeTableRowIndexRefs } from '@/utils/tableIndex'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const projectId = computed(() => Number(route.params.projectId) || proStore.projectInfo.id)

const loading = ref(false)
const jobList = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const tableRowIndex = makeTableRowIndexRefs(page, size)

const filter = reactive({
  run_type: null,
  state: null
})

const sceneList = ref([])

const dialogVisible = ref(false)
const formRef = ref()
const submitting = ref(false)
const isEdit = ref(false)
const currentId = ref(null)

const form = reactive({
  name: '',
  scene_id: null,
  env_id: null,
  run_type: 'crontab',
  interval: 3600,
  run_date: '',
  crontabStr: '0 2 * * *',
  state: true,
  use_workers: true
})

const rules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  scene_id: [{ required: true, message: '请选择场景', trigger: 'change' }],
  env_id: [{ required: true, message: '请选择环境', trigger: 'change' }],
  run_type: [{ required: true, message: '请选择执行类型', trigger: 'change' }],
  interval: [{ required: true, message: '请输入间隔时间', trigger: 'change', validator: (rule, value, callback) => {
    if (form.run_type === 'Interval' && (!value || value < 60)) return callback(new Error('间隔时间至少60秒'))
    callback()
  }}],
  run_date: [{ required: true, message: '请选择执行时间', trigger: 'change', validator: (rule, value, callback) => {
    if (form.run_type === 'date' && !value) return callback(new Error('请选择执行时间'))
    callback()
  }}],
  crontabStr: [{ required: true, message: '请输入Cron表达式', trigger: 'blur', validator: (rule, value, callback) => {
    if (form.run_type === 'crontab' && !value) return callback(new Error('请输入Cron表达式'))
    callback()
  }}]
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString()
}

const formatCron = (crontab) => {
  if (!crontab) return '-'
  if (typeof crontab === 'string') return crontab
  const c = crontab
  return `${c.minute || '*'} ${c.hour || '*'} ${c.day || '*'} ${c.month || '*'} ${c.day_of_week || '*'}`
}

const getRunStatusType = (status) => {
  const map = {
    'success': 'success',
    'failed': 'danger',
    'running': 'info',
    'stopped': 'warning',
    'pending': 'info'
  }
  return map[status] || 'info'
}

const getRunStatusText = (status) => {
  const map = {
    'success': '成功',
    'failed': '失败',
    'running': '执行中',
    'stopped': '已停止',
    'pending': '等待中'
  }
  return map[status] || status
}

const viewReport = (row) => {
  if (row.last_run_record_id) {
    router.push(`/perf-report/${row.last_run_record_id}`)
  }
}

const fetchJobs = async () => {
  loading.value = true
  try {
    const params = {
      project_id: projectId.value,
      page: page.value,
      size: size.value
    }
    if (filter.run_type) params.run_type = filter.run_type
    if (filter.state !== null) params.state = filter.state
    
    const res = await perfCronApi.getList(params)
    jobList.value = res.data?.data || []
    total.value = res.data?.total || 0
  } catch (error) {
    console.error('获取定时任务失败:', error)
  } finally {
    loading.value = false
  }
}

const fetchScenes = async () => {
  try {
    const res = await perfSceneApi.getList({
      project_id: projectId.value,
      page: 1,
      size: 1000
    })
    sceneList.value = res.data?.data || []
  } catch (error) {
    console.error('获取场景列表失败:', error)
  }
}

const handleSearch = () => {
  page.value = 1
  fetchJobs()
}

const handleSizeChange = (val) => {
  size.value = val
  fetchJobs()
}

const handlePageChange = (val) => {
  page.value = val
  fetchJobs()
}

const resetForm = () => {
  Object.assign(form, {
    name: '',
    scene_id: null,
    env_id: null,
    run_type: 'crontab',
    interval: 3600,
    run_date: '',
    crontabStr: '0 2 * * *',
    state: true,
    use_workers: true
  })
  isEdit.value = false
  currentId.value = null
}

const handleCreate = () => {
  resetForm()
  dialogVisible.value = true
}

const parseCronStr = (str) => {
  const parts = (str || '').trim().split(/\s+/)
  return {
    minute: parts[0] || '*',
    hour: parts[1] || '*',
    day: parts[2] || '*',
    month: parts[3] || '*',
    day_of_week: parts[4] || '*'
  }
}

const handleEdit = (row) => {
  resetForm()
  isEdit.value = true
  currentId.value = row.id
  
  Object.assign(form, {
    name: row.name,
    scene_id: row.scene_id,
    env_id: row.env_id,
    run_type: row.run_type || 'crontab',
    interval: row.interval || 3600,
    run_date: row.run_date || '',
    crontabStr: formatCron(row.crontab),
    state: row.state,
    use_workers: !!row.use_workers
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
      scene_id: form.scene_id,
      env_id: form.env_id,
      run_type: form.run_type,
      state: form.state,
      use_workers: form.use_workers
    }
    
    // 根据执行类型填充对应参数
    if (form.run_type === 'Interval') {
      data.interval = form.interval
    } else if (form.run_type === 'date') {
      data.run_date = form.run_date
    } else if (form.run_type === 'crontab') {
      data.crontab = parseCronStr(form.crontabStr)
    }
    
    if (isEdit.value) {
      await perfCronApi.update(currentId.value, data)
    } else {
      await perfCronApi.create(data)
    }
    
    ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
    dialogVisible.value = false
    fetchJobs()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    submitting.value = false
  }
}

const handleToggle = async (row) => {
  try {
    await perfCronApi.toggle(row.id)
    ElMessage.success('状态更新成功')
  } catch (error) {
    console.error('状态更新失败:', error)
    row.state = !row.state
    ElMessage.error('状态更新失败')
  }
}

const handleDelete = async (row) => {
  try {
    await perfCronApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchJobs()
  } catch (error) {
    console.error('删除失败:', error)
    ElMessage.error('删除失败')
  }
}

// ========== 执行记录弹窗 ==========
const recordDialogVisible = ref(false)
const recordLoading = ref(false)
const recordList = ref([])
const selectedJob = ref(null)
const recordPage = reactive({
  page: 1,
  size: 10,
  total: 0
})

const recordTableRowIndex = makeTableRowIndex(recordPage)

const handleShowRecords = async (row) => {
  selectedJob.value = row
  recordDialogVisible.value = true
  recordPage.page = 1
  await fetchJobRecords()
}

const fetchJobRecords = async () => {
  if (!selectedJob.value) return
  recordLoading.value = true
  try {
    const res = await perfCronApi.getRecords(selectedJob.value.id, {
      page: recordPage.page,
      size: recordPage.size
    })
    recordList.value = res.data?.data || []
    recordPage.total = res.data?.total || 0
  } catch (error) {
    console.error('获取执行记录失败:', error)
  } finally {
    recordLoading.value = false
  }
}

const viewRecordReport = (row) => {
  if (row.id) {
    router.push(`/perf-report/${row.id}`)
  }
}

onMounted(() => {
  fetchJobs()
  fetchScenes()
})
</script>

<style lang="scss" scoped>
.perf-cron-jobs {
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
</style>
