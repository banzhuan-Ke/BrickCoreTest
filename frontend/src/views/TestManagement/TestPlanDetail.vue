<template>
  <div class="tm-plan-detail" v-loading="loading">
    <div class="header" v-if="plan">
      <TmBackButton label="返回版本" @click="$router.push(`/test-releases/${plan.release_id}`)" />
      <h2>{{ plan.name }}</h2>
      <el-tag>{{ planStatusLabel(plan.status) }}</el-tag>
      <el-tag type="info">{{ planTypeLabel(plan.plan_type) }}</el-tag>
      <el-tag v-if="planEnvironmentLabel" type="warning">{{ planEnvironmentLabel }}</el-tag>
      <div class="actions" v-if="canEdit || canRun">
        <el-button v-if="canEdit" @click="openEnvDialog">设置环境</el-button>
        <el-button v-if="canEdit" @click="genManual">从范围补齐手工项</el-button>
        <el-button v-if="canEdit" @click="genAutomation">从范围补齐自动化项</el-button>
        <el-button v-if="canRun" type="primary" @click="openRunDialog">创建运行</el-button>
      </div>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="计划项" name="items">
        <el-table :data="items" border stripe>
          <el-table-column prop="order_no" label="#" width="60" />
          <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="functional_case_id" label="用例ID" width="90" />
          <el-table-column prop="execution_mode" label="模式" width="90">
            <template #default="{ row }">{{ row.execution_mode === 'automation' ? '自动' : '手工' }}</template>
          </el-table-column>
          <el-table-column prop="item_type" label="类型" width="110">
            <template #default="{ row }">{{ planItemTypeLabel(row.item_type) }}</template>
          </el-table-column>
          <el-table-column prop="required" label="必测" width="70">
            <template #default="{ row }">{{ row.required ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column
            v-if="canEdit && planEditable"
            label="操作"
            width="90"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button link type="danger" @click="removeItem(row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="运行历史" name="runs">
        <el-table :data="runs" border stripe>
          <el-table-column prop="id" label="运行ID" width="90" />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">{{ runStatusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column prop="create_by" label="触发人" width="100" />
          <el-table-column prop="started_at" label="开始" width="170">
            <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/test-plan-runs/${row.id}`)">
                打开
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="envDialogVisible" title="设置执行环境" width="460px" destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="环境">
          <el-select v-model="envForm.environment_id" clearable placeholder="未设置" style="width: 280px">
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
        <el-button @click="envDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="envSaving" @click="saveEnvironment">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runDialogVisible" title="创建计划运行" width="460px" destroy-on-close>
      <el-form label-width="120px">
        <el-form-item label="立即派发自动化">
          <el-switch v-model="runForm.dispatch_automation" />
        </el-form-item>
        <el-form-item v-if="runForm.dispatch_automation" label="Runner 设备">
          <RunnerDeviceSelect
            v-model="runForm.device_id"
            :project-id="projectId"
            engine="any"
            placeholder="Web/App 自动化请选择在线设备"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="runSaving" @click="startRun">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { testPlanApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import { planItemTypeLabel } from '@/utils/testPlanDisplay'
import TmBackButton from './components/TmBackButton.vue'
import RunnerDeviceSelect from '@/components/RunnerDeviceSelect.vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const projectId = computed(() => proStore.projectInfo?.id)
const planId = computed(() => Number(route.params.id))
const canEdit = computed(() => uStore.hasPermission('test_plan:edit'))
const canRun = computed(() => uStore.hasPermission('test_plan:run'))
const planEditable = computed(() => plan.value && !['running', 'completed'].includes(plan.value.status))

const loading = ref(false)
const runSaving = ref(false)
const envSaving = ref(false)
const tab = ref('items')
const plan = ref(null)
const items = ref([])
const runs = ref([])
const runDialogVisible = ref(false)
const envDialogVisible = ref(false)
const runForm = reactive({ dispatch_automation: false, device_id: '' })
const envForm = reactive({ environment_id: null })

const planEnvironmentLabel = computed(() => {
  const envId = plan.value?.environment_id
  if (!envId) return ''
  const env = proStore.envList.find((e) => e.id === envId)
  return env ? `环境：${env.name}` : `环境 #${envId}`
})

const planStatusLabel = (s) =>
  ({ draft: '草稿', ready: '就绪', running: '运行中', completed: '已完成', cancelled: '已取消' }[s] || s)
const planTypeLabel = (s) =>
  ({ smoke: '冒烟', regression: '回归', acceptance: '验收', performance: '性能', custom: '自定义' }[s] || s)
const runStatusLabel = (s) =>
  ({ running: '运行中', completed: '已完成', cancelled: '已取消' }[s] || s)
const formatTime = (v) => (v ? String(v).replace('T', ' ').slice(0, 19) : '—')

const load = async () => {
  if (!projectId.value || !planId.value) return
  loading.value = true
  try {
    if (!proStore.envList?.length) {
      await proStore.getEnvList(projectId.value)
    }
    const res = await testPlanApi.get(planId.value, projectId.value)
    const data = res.data?.data || {}
    plan.value = data.plan || null
    items.value = data.items || []
    runs.value = data.runs || []
  } finally {
    loading.value = false
  }
}

const openEnvDialog = () => {
  envForm.environment_id = plan.value?.environment_id ?? null
  envDialogVisible.value = true
}

const saveEnvironment = async () => {
  envSaving.value = true
  try {
    await testPlanApi.update(planId.value, projectId.value, {
      environment_id: envForm.environment_id || null
    })
    ElMessage.success('环境已更新')
    envDialogVisible.value = false
    await load()
  } finally {
    envSaving.value = false
  }
}

const genManual = async () => {
  const res = await testPlanApi.generateFromScope(planId.value, projectId.value)
  ElMessage.success(`新增手工项 ${res.data?.data?.created || 0} 个`)
  await load()
}

const genAutomation = async () => {
  const res = await testPlanApi.generateAutomationFromScope(planId.value, projectId.value)
  ElMessage.success(`新增自动化项 ${res.data?.data?.created || 0} 个`)
  await load()
}

const openRunDialog = () => {
  runForm.dispatch_automation = items.value.some((i) => i.execution_mode === 'automation')
  runForm.device_id = ''
  runDialogVisible.value = true
}

const startRun = async () => {
  runSaving.value = true
  try {
    const res = await testPlanApi.createRun(planId.value, projectId.value, {
      environment_id: plan.value?.environment_id || null,
      dispatch_automation: runForm.dispatch_automation,
      device_id: runForm.device_id ? String(runForm.device_id).trim() || null : null
    })
    const runId = res.data?.data?.id
    ElMessage.success('已创建运行')
    runDialogVisible.value = false
    if (runId) router.push(`/test-plan-runs/${runId}`)
    else await load()
  } finally {
    runSaving.value = false
  }
}

const removeItem = async (row) => {
  await ElMessageBox.confirm(`从计划中移除「${row.title || row.functional_case_id}」？`, '确认')
  await testPlanApi.removeItem(planId.value, row.id, projectId.value)
  ElMessage.success('已移除')
  await load()
}

watch([projectId, planId], () => load())
onMounted(load)
</script>

<style scoped>
.tm-plan-detail { padding: 16px; }
.header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.header h2 { margin: 0; font-size: 20px; }
.actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
</style>
