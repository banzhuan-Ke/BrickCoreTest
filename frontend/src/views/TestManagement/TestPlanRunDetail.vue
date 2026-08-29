<template>
  <div class="tm-run-detail" v-loading="loading">
    <div class="header" v-if="run">
      <TmBackButton label="返回计划" @click="$router.push(`/test-plans/${run.plan_id}`)" />
      <h2>运行 #{{ run.id }}</h2>
      <el-tag>{{ runStatusLabel(run.status) }}</el-tag>
      <div class="actions" v-if="run.status === 'running'">
        <el-button
          v-if="canRun && hasAutomationPending"
          @click="syncAutomation()"
          :loading="syncing"
        >
          同步自动化结果
        </el-button>
        <span v-if="canRun && hasAutomationPending" class="poll-hint">运行中约每 8 秒自动同步</span>
        <el-button
          v-if="canRun && hasAutomationPending"
          type="primary"
          plain
          @click="openDispatch"
        >派发自动化</el-button>
        <el-button v-if="canRun" type="danger" plain @click="cancelRun">取消运行</el-button>
      </div>
    </div>

    <el-table :data="items" border stripe>
      <el-table-column prop="order_no" label="#" width="60" />
      <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
      <el-table-column prop="execution_mode" label="模式" width="80">
        <template #default="{ row }">{{ row.execution_mode === 'automation' ? '自动' : '手工' }}</template>
      </el-table-column>
      <el-table-column prop="result_status" label="结果" width="110">
        <template #default="{ row }">{{ resultLabel(row.result_status) }}</template>
      </el-table-column>
      <el-table-column prop="attempt_count" label="次数" width="70" />
      <el-table-column prop="result_message" label="说明" min-width="140" show-overflow-tooltip />
      <el-table-column label="执行人" width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ formatMemberName(row.assignee_id, memberNames) }}</template>
      </el-table-column>
      <el-table-column label="证据" width="120">
        <template #header>
          <span>证据</span>
          <el-tooltip content="自动化执行后关联的报告/记录链接；手工执行可在说明中留痕" placement="top">
            <el-icon style="margin-left: 4px; vertical-align: middle"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <router-link v-if="reportPath(row) && reportAccessible(row)" :to="reportPath(row)" class="link">
            报告
          </router-link>
          <el-tooltip
            v-else-if="reportPath(row) && !reportAccessible(row)"
            content="无对应模块查看权限"
          >
            <span class="muted">无权限</span>
          </el-tooltip>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="canRun && run?.status === 'running'"
            link
            type="primary"
            @click="openAssign(row)"
          >指派</el-button>
          <el-button
            v-if="canExecute && run?.status === 'running' && row.execution_mode === 'manual'"
            link
            type="primary"
            @click="openResult(row)"
          >填结果</el-button>
          <el-button
            v-if="canDefectEdit && defectCreatable(row)"
            link
            type="warning"
            @click="openCreateDefect(row)"
          >转缺陷</el-button>
          <el-button link @click="showAttempts(row)">历史</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="defectVisible" title="从运行项创建缺陷" width="520px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="标题" required>
          <el-input v-model="defectForm.title" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="defectForm.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="严重度">
          <el-select v-model="defectForm.severity" style="width: 160px">
            <el-option label="阻塞" value="blocker" />
            <el-option label="严重" value="critical" />
            <el-option label="一般" value="major" />
            <el-option label="轻微" value="minor" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="defectForm.priority" style="width: 160px">
            <el-option v-for="p in ['p0', 'p1', 'p2', 'p3']" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="defectVisible = false">取消</el-button>
        <el-button type="primary" :loading="defectSaving" @click="submitCreateDefect">创建并打开</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignVisible" title="指派执行人" width="420px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="执行人">
          <ProjectMemberSelect
            v-if="projectId"
            v-model="assignForm.assignee_id"
            :project-id="projectId"
            placeholder="选择执行人"
            width="240px"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button v-if="assignItem?.assignee_id" plain @click="clearAssignee">清除指派</el-button>
        <el-button type="primary" :loading="assignSaving" @click="submitAssign">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="resultVisible" title="提交手工结果" size="640px" destroy-on-close class="result-drawer">
      <FunctionalCaseBodyPanel
        v-if="resultItem?.functional_case_id"
        :case-data="resultCaseData"
        :functional-case-id="resultItem.functional_case_id"
        :project-id="projectId"
        class="case-block"
      />
      <el-form label-width="90px" class="result-form">
        <el-form-item label="结果" required>
          <el-select v-model="resultForm.result_status" style="width: 200px">
            <el-option label="通过" value="passed" />
            <el-option label="失败" value="failed" />
            <el-option label="阻塞" value="blocked" />
            <el-option label="跳过" value="skipped" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="resultForm.result_message" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="resultVisible = false">取消</el-button>
          <el-button
            v-if="canDefectEdit && ['failed', 'blocked', 'error'].includes(resultForm.result_status)"
            type="warning"
            plain
            @click="submitResultAndDefect"
          >提交并转缺陷</el-button>
          <el-button type="primary" :loading="saving" @click="submitResult">提交</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="dispatchVisible" title="派发自动化" width="440px" destroy-on-close>
      <p class="hint">Web/App 自动化需指定在线 Runner 设备；接口用例将同步执行。</p>
      <el-form label-width="100px">
        <el-form-item label="Runner 设备">
          <RunnerDeviceSelect
            v-model="dispatchDeviceId"
            :project-id="projectId"
            engine="any"
            placeholder="Web/App 自动化请选择在线设备"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dispatchVisible = false">取消</el-button>
        <el-button type="primary" :loading="dispatching" @click="doDispatch">派发</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="attemptVisible" title="执行历史" size="480px" class="attempt-drawer">
      <div v-if="attempts.length" class="attempt-list">
        <div v-for="a in attempts" :key="a.id" class="attempt-card">
          <div class="attempt-head">
            <el-tag size="small" :type="attemptTagType(a.result_status)">
              第 {{ a.attempt_no }} 次 · {{ resultLabel(a.result_status) }}
            </el-tag>
            <span class="attempt-time">{{ formatTime(a.create_time) }}</span>
          </div>
          <p v-if="a.result_message" class="attempt-msg">{{ a.result_message }}</p>
          <div class="attempt-meta">
            <span>执行人：{{ a.operator || '—' }}</span>
          </div>
        </div>
      </div>
      <el-empty v-else description="暂无执行历史" />
    </el-drawer>

    <DefectDetailDrawer
      v-if="projectId"
      ref="defectDrawerRef"
      :project-id="projectId"
      :can-edit="canDefectEdit"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { testDefectApi, testPlanApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import DefectDetailDrawer from './components/DefectDetailDrawer.vue'
import TmBackButton from './components/TmBackButton.vue'
import ProjectMemberSelect from './components/ProjectMemberSelect.vue'
import RunnerDeviceSelect from '@/components/RunnerDeviceSelect.vue'
import FunctionalCaseBodyPanel from './components/FunctionalCaseBodyPanel.vue'
import { formatMemberName, loadMemberNameMap } from '@/utils/projectMembers'
import { planRunStatusLabel, runItemResultLabel } from '@/utils/tmDisplay'

const route = useRoute()
const proStore = ProjectStore()
const uStore = UserStore()

const projectId = computed(() => proStore.projectInfo?.id)
const runId = computed(() => Number(route.params.id))
const canExecute = computed(() => uStore.hasPermission('test_manual:execute'))
const canRun = computed(() => uStore.hasPermission('test_plan:run'))
const canDefectEdit = computed(() => uStore.hasPermission('test_defect:edit'))

const loading = ref(false)
const saving = ref(false)
const syncing = ref(false)
const dispatching = ref(false)
const run = ref(null)
const items = ref([])
const resultVisible = ref(false)
const resultItem = ref(null)
const resultForm = reactive({ result_status: 'passed', result_message: '' })
const attemptVisible = ref(false)
const attempts = ref([])
const dispatchVisible = ref(false)
const dispatchDeviceId = ref('')
const defectVisible = ref(false)
const defectSaving = ref(false)
const defectItem = ref(null)
const defectDrawerRef = ref(null)
const defectForm = reactive({
  title: '',
  description: '',
  severity: 'major',
  priority: 'p2'
})
const memberNames = ref({})
const assignVisible = ref(false)
const assignSaving = ref(false)
const assignItem = ref(null)
const assignForm = reactive({ assignee_id: null })

const resultCaseData = computed(() => {
  const row = resultItem.value
  if (!row) return null
  if (!row.functional_case_id && !row.case_steps && !row.case_precondition) return null
  return {
    id: row.functional_case_id,
    title: row.title,
    module: row.case_module,
    precondition: row.case_precondition,
    steps: row.case_steps,
    source_requirement_id: row.source_requirement_id
  }
})

const DEFECT_CREATABLE = new Set(['failed', 'error', 'blocked'])

const hasAutomationPending = computed(() =>
  items.value.some(
    (i) => i.execution_mode === 'automation' && ['not_run', 'running'].includes(i.result_status)
  )
)

const runStatusLabel = planRunStatusLabel
const resultLabel = runItemResultLabel
const attemptTagType = (s) =>
  ({
    passed: 'success',
    failed: 'danger',
    blocked: 'warning',
    error: 'danger',
    skipped: 'info',
    cancelled: 'info'
  }[s] || 'info')
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')
const defectCreatable = (row) => DEFECT_CREATABLE.has(row.result_status)
const reportPath = (row) => {
  const raw = row.evidence_json?.record_url || row.evidence_json?.report_url
  if (!raw) return null
  const [path, qs] = String(raw).split('?')
  if (!qs) return path
  const query = Object.fromEntries(new URLSearchParams(qs))
  return { path, query }
}

const reportPermissionForPath = (path) => {
  const p = String(path || '')
  if (p.startsWith('/api-module/report')) return 'api_case:view'
  if (p.startsWith('/case/edit') || p.startsWith('/record')) return 'ui_case:view'
  if (p.startsWith('/app-case/edit') || p.startsWith('/app-record')) return 'app_case:view'
  if (p.startsWith('/perf-report')) return 'perf_record:view'
  return null
}

const reportAccessible = (row) => {
  const target = reportPath(row)
  if (!target) return false
  const path = typeof target === 'string' ? target : target.path
  const perm = reportPermissionForPath(path)
  if (!perm) return false
  return uStore.hasPermission(perm)
}

const load = async () => {
  if (!projectId.value || !runId.value) return
  loading.value = true
  try {
    const res = await testPlanApi.getRun(runId.value, projectId.value)
    const data = res.data?.data || {}
    run.value = data.run || null
    items.value = data.items || []
    memberNames.value = await loadMemberNameMap(projectId.value)
  } catch {
    run.value = null
    items.value = []
  } finally {
    loading.value = false
  }
}

const openAssign = (row) => {
  assignItem.value = row
  assignForm.assignee_id = row.assignee_id ?? null
  assignVisible.value = true
}

const submitAssign = async () => {
  if (!assignItem.value || !assignForm.assignee_id) {
    ElMessage.warning('请选择执行人')
    return
  }
  assignSaving.value = true
  try {
    await testPlanApi.updateRunItemAssignee(
      runId.value,
      assignItem.value.id,
      projectId.value,
      { assignee_id: assignForm.assignee_id }
    )
    ElMessage.success('已指派')
    assignVisible.value = false
    await load()
  } catch {
    ElMessage.error('指派失败')
  } finally {
    assignSaving.value = false
  }
}

const clearAssignee = async () => {
  if (!assignItem.value) return
  assignSaving.value = true
  try {
    await testPlanApi.updateRunItemAssignee(
      runId.value,
      assignItem.value.id,
      projectId.value,
      { clear_assignee: true }
    )
    ElMessage.success('已清除指派')
    assignVisible.value = false
    await load()
  } catch {
    ElMessage.error('操作失败')
  } finally {
    assignSaving.value = false
  }
}

const syncAutomation = async (silent = false) => {
  if (!canRun.value) return
  syncing.value = true
  try {
    const res = await testPlanApi.syncAutomation(runId.value, projectId.value)
    const data = res.data?.data || {}
    run.value = data.run || run.value
    items.value = data.items || items.value
    if (!silent && (data.synced || 0) > 0) {
      ElMessage.success(`已同步 ${data.synced} 项`)
    }
  } catch {
    if (!silent) ElMessage.error('同步失败')
  } finally {
    syncing.value = false
  }
}

const openDispatch = () => {
  dispatchDeviceId.value = ''
  dispatchVisible.value = true
}

const doDispatch = async () => {
  dispatching.value = true
  try {
    const res = await testPlanApi.dispatchAutomation(runId.value, projectId.value, {
      device_id: dispatchDeviceId.value ? String(dispatchDeviceId.value).trim() || null : null
    })
    const data = res.data?.data || {}
    run.value = data.run || run.value
    items.value = data.items || items.value
    ElMessage.success(`已派发 ${data.dispatched || 0} 项，阻塞 ${data.blocked || 0} 项`)
    dispatchVisible.value = false
  } catch {
    ElMessage.error('派发失败')
  } finally {
    dispatching.value = false
  }
}

const openResult = (row) => {
  resultItem.value = row
  resultForm.result_status = 'passed'
  resultForm.result_message = ''
  resultVisible.value = true
}

const submitResult = async () => {
  if (['failed', 'blocked'].includes(resultForm.result_status) && !resultForm.result_message.trim()) {
    ElMessage.warning('失败/阻塞必须填写说明')
    return
  }
  saving.value = true
  try {
    await testPlanApi.submitManualResult(
      runId.value,
      resultItem.value.id,
      projectId.value,
      {
        result_status: resultForm.result_status,
        result_message: resultForm.result_message || null
      }
    )
    ElMessage.success('已提交')
    resultVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const submitResultAndDefect = async () => {
  if (['failed', 'blocked'].includes(resultForm.result_status) && !resultForm.result_message.trim()) {
    ElMessage.warning('失败/阻塞必须填写说明')
    return
  }
  saving.value = true
  try {
    await testPlanApi.submitManualResult(
      runId.value,
      resultItem.value.id,
      projectId.value,
      {
        result_status: resultForm.result_status,
        result_message: resultForm.result_message || null
      }
    )
    resultVisible.value = false
    await load()
    const row = items.value.find((i) => i.id === resultItem.value?.id) || resultItem.value
    openCreateDefect(row)
  } finally {
    saving.value = false
  }
}

const openCreateDefect = (row) => {
  defectItem.value = row
  defectForm.title = `[${runItemResultLabel(row.result_status)}] ${row.title || ''}`
  defectForm.description = row.result_message || ''
  defectForm.severity = 'major'
  defectForm.priority = 'p2'
  defectVisible.value = true
}

const submitCreateDefect = async () => {
  if (!defectItem.value) return
  if (!defectForm.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  defectSaving.value = true
  try {
    const res = await testDefectApi.createFromRunItem(
      defectItem.value.id,
      projectId.value,
      runId.value,
      {
        title: defectForm.title.trim(),
        description: defectForm.description || null,
        severity: defectForm.severity,
        priority: defectForm.priority
      }
    )
    const data = res.data?.data || {}
    if (data.warn_duplicate) {
      ElMessage.warning(
        `已创建 ${data.defect_key}；该项已有 ${data.existing_open_defects?.length || 0} 个未关闭缺陷`
      )
    } else {
      ElMessage.success(`已创建缺陷 ${data.defect_key}`)
    }
    defectVisible.value = false
    if (data.id) {
      await defectDrawerRef.value?.open(data.id)
    }
  } finally {
    defectSaving.value = false
  }
}

const showAttempts = async (row) => {
  const res = await testPlanApi.listAttempts(runId.value, row.id, projectId.value)
  attempts.value = res.data?.data || []
  attemptVisible.value = true
}

const cancelRun = async () => {
  await ElMessageBox.confirm('取消本次运行？未执行项将标记为跳过。', '确认', { type: 'warning' })
  const res = await testPlanApi.cancelRun(runId.value, projectId.value)
  const stop = res.data?.data?.automation_stop
  if (stop?.stopped) {
    ElMessage.success(`已取消，并通知 Runner 停止 ${stop.stopped} 个自动化任务`)
  } else {
    ElMessage.success('已取消')
  }
  await load()
}

let pollTimer = null
const stopPoll = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
const startPoll = () => {
  stopPoll()
  if (!canRun.value || run.value?.status !== 'running' || !hasAutomationPending.value) return
  pollTimer = setInterval(async () => {
    if (document.hidden) return
    if (run.value?.status !== 'running' || !hasAutomationPending.value) {
      stopPoll()
      return
    }
    await syncAutomation(true)
  }, 8000)
}

watch([projectId, runId], async () => {
  stopPoll()
  await load()
  startPoll()
})
watch(
  () => [run.value?.status, hasAutomationPending.value, canRun.value],
  () => startPoll()
)
onMounted(async () => {
  await load()
  startPoll()
})
onUnmounted(stopPoll)
</script>

<style scoped>
.tm-run-detail { padding: 16px; }
.header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.header h2 { margin: 0; font-size: 20px; }
.actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
.msg { margin-top: 4px; color: #606266; }
.op { margin-top: 2px; color: #909399; font-size: 12px; }
.hint { margin: 0 0 12px; color: #606266; font-size: 13px; }
.link { color: var(--el-color-primary); text-decoration: none; }
.muted { color: #909399; font-size: 12px; cursor: help; }
.poll-hint { color: #909399; font-size: 12px; align-self: center; }
.attempt-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.attempt-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 14px;
  background: #fafafa;
}
.attempt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.attempt-time {
  font-size: 12px;
  color: #909399;
}
.attempt-msg {
  margin: 0 0 6px;
  font-size: 13px;
  color: #303133;
  line-height: 1.5;
  white-space: pre-wrap;
}
.attempt-meta {
  font-size: 12px;
  color: #606266;
}
.case-block {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #ebeef5;
}
.result-form {
  margin-top: 8px;
}
.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
