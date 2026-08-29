<template>
  <PageCard>
    <template #title>
      <el-button v-if="canEdit" type="primary" size="small" icon="Plus" @click="openDialog()">定时任务</el-button>
    </template>
    <template #main>
      <el-table :data="jobList" stripe v-loading="loading">
        <el-table-column prop="name" label="任务名称" min-width="140" />
        <el-table-column label="目标" min-width="160">
          <template #default="{ row }">
            <el-tag size="small" :type="row.target_type === 'plan' ? 'warning' : 'primary'">
              {{ row.target_type === 'plan' ? '计划' : '套件' }}
            </el-tag>
            {{ row.target_type === 'plan' ? row.plan_name : row.suite_name }}
          </template>
        </el-table-column>
        <el-table-column label="策略" min-width="180">
          <template #default="{ row }">{{ formatSchedule(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch v-model="row.state" :disabled="!canEdit" @change="toggleJob(row)" />
          </template>
        </el-table-column>
        <el-table-column label="上次执行" min-width="160">
          <template #default="{ row }">
            <div v-if="row.last_run_time">{{ formatTime(row.last_run_time) }}</div>
            <el-tag v-if="row.last_run_status" size="small" :type="row.last_run_status === 'success' ? 'success' : 'danger'">
              {{ row.last_run_status === 'success' ? '成功' : '失败' }}
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300">
          <template #default="{ row }">
            <el-button link type="success" @click="showRecords(row)">记录</el-button>
            <el-button v-if="row.last_run_record_id" link type="primary" @click="openLastReport(row)">最近报告</el-button>
            <el-button v-if="canEdit" link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button v-if="canExecute" link type="warning" @click="runNow(row)">立即执行</el-button>
            <el-button v-if="canEdit" link type="danger" @click="removeJob(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </PageCard>

  <el-dialog v-model="dlgVisible" :title="form.id ? '编辑定时任务' : '新建定时任务'" width="560px" destroy-on-close class="bc-dialog">
    <el-form :model="form" label-width="100px" class="bc-dialog-form">
      <el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="目标类型">
        <el-radio-group v-model="form.target_type">
          <el-radio value="plan">计划</el-radio>
          <el-radio value="suite">套件</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.target_type === 'plan'" label="App 计划">
        <el-select v-model="form.plan_id" filterable style="width: 100%">
          <el-option v-for="p in plans" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-else label="App 套件">
        <el-select v-model="form.suite_id" filterable style="width: 100%">
          <el-option v-for="s in suites" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="运行环境">
        <UiRunEnvSelect v-model="form.env_id" />
      </el-form-item>
      <el-form-item label="执行设备">
        <el-select v-model="form.device_id" clearable filterable placeholder="留空则自动选择在线 App Runner" style="width: 100%">
          <el-option v-for="d in appDevices" :key="d.id" :label="`${d.name || d.username} (${d.app_udid || d.id})`" :value="d.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="调度类型">
        <el-select v-model="form.run_type">
          <el-option label="间隔" value="Interval" />
          <el-option label="固定时间" value="date" />
          <el-option label="Cron 表达式" value="crontab" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.run_type === 'Interval'" label="间隔(秒)">
        <el-input-number v-model="form.interval" :min="60" />
      </el-form-item>
      <el-form-item v-if="form.run_type === 'date'" label="执行时间">
        <el-date-picker v-model="form.run_date" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
      </el-form-item>
      <template v-if="form.run_type === 'crontab'">
        <el-form-item label="分"><el-input v-model="form.crontab.minute" placeholder="*" /></el-form-item>
        <el-form-item label="时"><el-input v-model="form.crontab.hour" placeholder="*" /></el-form-item>
        <el-form-item label="日"><el-input v-model="form.crontab.day" placeholder="*" /></el-form-item>
        <el-form-item label="月"><el-input v-model="form.crontab.month" placeholder="*" /></el-form-item>
        <el-form-item label="周"><el-input v-model="form.crontab.day_of_week" placeholder="*" /></el-form-item>
      </template>
      <el-form-item label="启用"><el-switch v-model="form.state" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dlgVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveJob">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="recordDialogVisible" :title="`执行记录 - ${selectedJob?.name || ''}`" width="85%" destroy-on-close>
    <el-table :data="recordList" stripe v-loading="recordLoading">
      <el-table-column type="index" label="#" width="60" />
      <el-table-column prop="name" label="目标" min-width="140" />
      <el-table-column prop="status" label="状态" width="110" />
      <el-table-column prop="pass_rate" label="通过率" width="90">
        <template #default="{ row }">{{ (row.pass_rate || 0).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column prop="username" label="执行人" width="100" />
      <el-table-column prop="start_time" label="开始时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="openRecordReport(row)">查看报告</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import UiRunEnvSelect from '@/components/UiRunEnvSelect.vue'
import { appCronApi, appPlanApi, appSuiteApi, deviceApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import dateTools from '@/tools/dateTools'

const router = useRouter()

const proStore = ProjectStore()
const uStore = UserStore()
const canEdit = computed(() => uStore.hasPermission('app_plan:edit'))
const canExecute = computed(() => uStore.hasPermission('app_plan:execute'))

const loading = ref(false)
const saving = ref(false)
const dlgVisible = ref(false)
const jobList = ref([])
const plans = ref([])
const suites = ref([])
const devices = ref([])
const recordDialogVisible = ref(false)
const recordLoading = ref(false)
const recordList = ref([])
const selectedJob = ref(null)

function formatTime(v) {
  return v ? dateTools.rTime(v) : '-'
}

const appDevices = computed(() =>
  (devices.value || []).filter((d) => (d.runner_engine_types || ['web']).includes('app'))
)

const form = reactive({
  id: '',
  name: '',
  target_type: 'plan',
  plan_id: null,
  suite_id: null,
  env_id: '',
  device_id: '',
  run_type: 'Interval',
  interval: 3600,
  run_date: '',
  crontab: { minute: '0', hour: '8', day: '*', month: '*', day_of_week: '*' },
  state: false,
})

function formatSchedule(row) {
  if (row.run_type === 'Interval') return `每 ${row.interval} 秒`
  if (row.run_type === 'date') return row.run_date || '-'
  if (row.run_type === 'crontab') {
    const c = row.crontab || {}
    return `${c.minute} ${c.hour} ${c.day} ${c.month} ${c.day_of_week}`
  }
  return '-'
}

async function loadMeta() {
  const pid = proStore.projectInfo.id
  const [planRes, suiteRes, devRes] = await Promise.all([
    appPlanApi.list({ project_id: pid, page: 1, size: 200 }),
    appSuiteApi.list({ project_id: pid, page: 1, size: 200 }),
    deviceApi.getList({ page: 1, size: 200 }),
  ])
  plans.value = planRes.data?.data || []
  suites.value = suiteRes.data?.data || []
  devices.value = devRes.data?.data || devRes.data || []
}

async function loadList() {
  loading.value = true
  try {
    const res = await appCronApi.list({ project_id: proStore.projectInfo.id, page: 1, size: 100 })
    jobList.value = res.data?.data || []
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      name: row.name,
      target_type: row.target_type || (row.plan_id ? 'plan' : 'suite'),
      plan_id: row.plan_id,
      suite_id: row.suite_id,
      env_id: row.env_id,
      device_id: row.device_id || '',
      run_type: row.run_type,
      interval: row.interval,
      run_date: row.run_date || '',
      crontab: { ...(row.crontab || form.crontab) },
      state: row.state,
    })
  } else {
    Object.assign(form, {
      id: '',
      name: '',
      target_type: 'plan',
      plan_id: null,
      suite_id: null,
      env_id: '',
      device_id: '',
      run_type: 'Interval',
      interval: 3600,
      run_date: '',
      crontab: { minute: '0', hour: '8', day: '*', month: '*', day_of_week: '*' },
      state: false,
    })
  }
  dlgVisible.value = true
}

async function saveJob() {
  if (!form.name.trim() || !form.env_id) {
    ElMessage.warning('请填写任务名称和环境')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name,
      project_id: proStore.projectInfo.id,
      env_id: form.env_id,
      device_id: form.device_id || null,
      run_type: form.run_type,
      interval: form.interval,
      run_date: form.run_date || null,
      crontab: form.crontab,
      state: form.state,
      plan_id: form.target_type === 'plan' ? form.plan_id : null,
      suite_id: form.target_type === 'suite' ? form.suite_id : null,
    }
    if (form.id) {
      await appCronApi.update(form.id, payload)
    } else {
      await appCronApi.create(payload)
    }
    dlgVisible.value = false
    ElMessage.success('已保存')
    loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleJob(row) {
  try {
    await appCronApi.toggle(row.id)
  } catch {
    row.state = !row.state
  }
}

async function runNow(row) {
  const res = await appCronApi.runNow(row.id)
  ElMessage.success(res.data?.msg || '已触发')
  loadList()
}

async function showRecords(row) {
  selectedJob.value = row
  recordDialogVisible.value = true
  recordLoading.value = true
  try {
    const res = await appCronApi.records(row.id, { page: 1, size: 50 })
    recordList.value = res.data?.data || []
  } finally {
    recordLoading.value = false
  }
}

function openRecordReport(row) {
  if (row.record_type === 'plan') {
    router.push({ name: 'appPlanReport', params: { id: row.id } })
  } else {
    router.push({ name: 'appSuiteReport', params: { id: row.id } })
  }
}

function openLastReport(row) {
  if (!row.last_run_record_id) return
  if (row.target_type === 'plan') {
    router.push({ name: 'appPlanReport', params: { id: row.last_run_record_id } })
  } else {
    router.push({ name: 'appSuiteReport', params: { id: row.last_run_record_id } })
  }
}

async function removeJob(row) {
  await ElMessageBox.confirm(`删除定时任务「${row.name}」？`, '提示', { type: 'warning' })
  await appCronApi.remove(row.id)
  ElMessage.success('已删除')
  loadList()
}

onMounted(async () => {
  await loadMeta()
  await loadList()
})
</script>
