<template>
  <PageCard>
    <template #title>
      <el-button v-if="canEdit" type="primary" size="small" icon="Plus" @click="showAdd = true">计划</el-button>
    </template>
    <template #main>
      <el-table :data="planList" stripe :header-cell-style="{ 'text-align': 'center' }" :cell-style="{ 'text-align': 'center' }">
        <el-table-column type="index" label="序号" width="70" />
        <el-table-column prop="name" label="计划名称" min-width="160" />
        <el-table-column prop="suites_count" label="套件数" width="90" />
        <el-table-column prop="status" label="最近状态" width="110" />
        <el-table-column label="操作" width="340">
          <template #default="{ row }">
            <el-button v-if="canExecute" type="warning" plain size="small" icon="Promotion" @click="openRun(row.id)">运行</el-button>
            <el-button type="success" plain size="small" icon="View" @click="openRecords(row)">报告</el-button>
            <el-button v-if="canEdit" type="primary" plain size="small" icon="Edit" @click="router.push({ name: 'appPlanEdit', params: { id: row.id } })">编辑</el-button>
            <el-button v-if="canEdit" type="danger" plain size="small" icon="Delete" @click="removePlan(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </PageCard>

  <el-dialog v-model="showAdd" title="创建 App 计划" width="420px">
    <el-form :model="addForm" label-width="88px">
      <el-form-item label="计划名称"><el-input v-model="addForm.name" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showAdd = false">取消</el-button>
      <el-button type="primary" @click="createPlan">确定</el-button>
    </template>
  </el-dialog>

  <AppRunDialog
    v-model="runDlg"
    :loading="running"
    :default-record-video="runPlanRecordVideo"
    :parallel="runPlanParallel"
    @submit="runPlan"
  />

  <el-dialog v-model="recordDlg" width="90%" destroy-on-close title="计划执行报告">
    <AppPlanRecord v-if="recordPlan.id" :plan-id="recordPlan.id" :project-id="proStore.projectInfo.id" />
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import AppRunDialog from '@/components/AppRunDialog.vue'
import AppPlanRecord from '@/views/App/components/AppPlanRecord.vue'
import { appPlanApi, appExecApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const canEdit = computed(() => uStore.hasPermission('app_plan:edit'))
const canExecute = computed(() => uStore.hasPermission('app_plan:execute'))

const planList = ref([])
const showAdd = ref(false)
const addForm = reactive({ name: '' })
const runDlg = ref(false)
const running = ref(false)
const runPlanId = ref(null)
const runPlanRecordVideo = ref(true)
const runPlanParallel = ref(false)
const recordDlg = ref(false)
const recordPlan = ref({ id: null })

async function loadList() {
  const res = await appPlanApi.list({ project_id: proStore.projectInfo.id, page: 1, size: 100 })
  planList.value = res.data?.data || []
}

async function createPlan() {
  if (!addForm.name.trim()) {
    ElMessage.warning('请输入计划名称')
    return
  }
  const res = await appPlanApi.create({
    name: addForm.name,
    project_id: proStore.projectInfo.id,
    username: uStore.userInfo?.username,
  })
  showAdd.value = false
  addForm.name = ''
  router.push({ name: 'appPlanEdit', params: { id: res.data.id } })
}

async function openRun(id) {
  runPlanId.value = id
  try {
    const res = await appPlanApi.detail(id)
    runPlanRecordVideo.value = res.data?.record_video !== false
    runPlanParallel.value = !!res.data?.parallel
  } catch {
    runPlanRecordVideo.value = true
    runPlanParallel.value = false
  }
  runDlg.value = true
}

function openRecords(row) {
  recordPlan.value = row
  recordDlg.value = true
}

async function runPlan(payload) {
  running.value = true
  try {
    const res = await appExecApi.runPlan(runPlanId.value, payload)
    runDlg.value = false
    const dispatched = res.data?.dispatched !== false
    ElNotification({ title: dispatched ? '已提交运行' : '记录已创建', message: res.data?.msg, type: dispatched ? 'success' : 'warning' })
  } finally {
    running.value = false
  }
}

async function removePlan(row) {
  try {
    await ElMessageBox.confirm(`确定删除计划「${row.name}」？`, '提示', { type: 'warning' })
    await appPlanApi.remove(row.id)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
  }
}

loadList()
</script>
