<template>
  <PageCard>
    <template #title>
      <el-button v-if="canEdit" @click="router.push({ name: 'appCaseAdd' })" size="small" type="primary" icon="Plus">用例</el-button>
    </template>
    <template #main>
      <CatalogListLayout
        :project-id="proStore.projectInfo.id"
        v-model="searchForm.catalog_id"
        all-node-label="全部用例"
        @change="loadList"
      >
        <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
          <el-input v-model="searchForm.name" placeholder="搜索用例名称" clearable style="width: 180px;" @keyup.enter="loadList" />
          <el-button type="primary" @click="loadList" icon="Search">搜索</el-button>
        </div>
        <el-table :data="caseList" stripe :header-cell-style="{ 'text-align': 'center' }" :cell-style="{ 'text-align': 'center' }">
          <el-table-column label="序号" type="index" width="70" />
          <el-table-column prop="name" label="用例名称" show-overflow-tooltip min-width="160" />
          <el-table-column prop="level" label="优先级" width="90" />
          <el-table-column prop="driver_mode" label="驱动模式" width="120">
            <template #default="{ row }">{{ driverModeLabel(row.driver_mode) }}</template>
          </el-table-column>
          <el-table-column prop="platform_scope" label="平台" width="100" />
          <el-table-column prop="username" label="创建人" width="110" />
          <el-table-column label="操作" width="420">
            <template #default="{ row }">
              <el-button v-if="canExecute" type="warning" plain size="small" icon="Promotion" @click="openRun(row.id)">运行</el-button>
              <el-button type="success" plain size="small" icon="View" @click="openRecords(row)">报告</el-button>
              <el-button v-if="canEdit" type="primary" plain size="small" icon="Edit" @click="router.push({ name: 'appCaseEdit', params: { id: row.id } })">编辑</el-button>
              <el-button v-if="canEdit" type="info" plain size="small" icon="CopyDocument" @click="copyCase(row)">复制</el-button>
              <el-button v-if="canEdit" type="danger" plain size="small" icon="Delete" @click="removeCase(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </CatalogListLayout>
    </template>
    <template #bottom>
      <el-pagination
        v-model:current-page="page.page"
        v-model:page-size="page.size"
        :total="page.total"
        layout="total, sizes, prev, pager, next"
        @current-change="loadList"
        @size-change="loadList"
      />
    </template>
  </PageCard>
  <AppRunDialog v-model="runDlg" :loading="running" @submit="runCase" />

  <el-dialog v-model="recordDlg" width="90%" destroy-on-close title="用例执行报告">
    <AppCaseRecord v-if="recordCase.id" :case-id="recordCase.id" :project-id="proStore.projectInfo.id" />
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import AppRunDialog from '@/components/AppRunDialog.vue'
import AppCaseRecord from '@/views/App/components/AppCaseRecord.vue'
import { appCaseApi, appExecApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

import { appDriverModeLabel } from '@/utils/appStepMeta.js'

const driverModeLabel = appDriverModeLabel
const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const canEdit = computed(() => uStore.hasPermission('app_case:edit'))
const canExecute = computed(() => uStore.hasPermission('app_case:execute'))

const caseList = ref([])
const page = reactive({ page: 1, size: 10, total: 0 })
const searchForm = reactive({ name: '', catalog_id: null })
const runDlg = ref(false)
const running = ref(false)
const runCaseId = ref(null)
const recordDlg = ref(false)
const recordCase = ref({ id: null })

async function loadList() {
  const res = await appCaseApi.list({
    project_id: proStore.projectInfo.id,
    page: page.page,
    size: page.size,
    name: searchForm.name || undefined,
    catalog_id: searchForm.catalog_id ?? undefined,
  })
  caseList.value = res.data?.data || []
  page.total = res.data?.total || 0
}

function openRun(id) {
  runCaseId.value = id
  runDlg.value = true
}

function openRecords(row) {
  recordCase.value = row
  recordDlg.value = true
}

async function runCase(payload) {
  running.value = true
  try {
    const res = await appExecApi.runCase(runCaseId.value, payload)
    runDlg.value = false
    const dispatched = res.data?.dispatched !== false
    ElNotification({
      title: dispatched ? '已提交运行' : '记录已创建',
      message: res.data?.msg,
      type: dispatched ? 'success' : 'warning',
    })
  } finally {
    running.value = false
  }
}

async function copyCase(row) {
  try {
    await ElMessageBox.confirm(`确定复制用例「${row.name}」？`, '提示', { type: 'warning' })
    const res = await appCaseApi.copy(row.id)
    const created = res.data?.data || res.data
    ElMessage.success(`已复制为「${created?.name || `${row.name}_副本`}」`)
    loadList()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.data?.detail || '复制失败')
  }
}

async function removeCase(row) {
  try {
    await ElMessageBox.confirm(`确定删除用例「${row.name}」？`, '提示', { type: 'warning' })
    await appCaseApi.remove(row.id)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
  }
}

loadList()
</script>
