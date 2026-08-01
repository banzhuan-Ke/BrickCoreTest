<template>
  <PageCard>
    <template #title>
      <el-button v-if="canEdit" type="primary" size="small" icon="Plus" @click="router.push({ name: 'appSuiteAdd' })">套件</el-button>
    </template>
    <template #main>
      <CatalogListLayout
        :project-id="proStore.projectInfo.id"
        v-model="searchForm.catalog_id"
        all-node-label="全部套件"
        @change="() => { page.page = 1; loadList() }"
      >
      <div style="margin-bottom: 15px; display: flex; gap: 10px;">
        <el-input v-model="searchForm.name" placeholder="搜索套件名称" clearable style="width: 180px;" @keyup.enter="loadList" />
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
      </div>
      <el-table :data="suiteList" stripe :header-cell-style="{ 'text-align': 'center' }" :cell-style="{ 'text-align': 'center' }">
        <el-table-column type="index" label="序号" width="70" />
        <el-table-column prop="name" label="套件名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="case_count" label="用例数" width="90" />
        <el-table-column prop="status" label="最近状态" width="110" />
        <el-table-column prop="username" label="创建人" width="110" />
        <el-table-column label="操作" width="340">
          <template #default="{ row }">
            <el-button v-if="canExecute" type="warning" plain size="small" icon="Promotion" @click="openRun(row.id)">运行</el-button>
            <el-button type="success" plain size="small" icon="View" @click="openRecords(row)">报告</el-button>
            <el-button v-if="canEdit" type="primary" plain size="small" icon="Edit" @click="router.push({ name: 'appSuiteEdit', params: { id: row.id } })">编辑</el-button>
            <el-button v-if="canEdit" type="danger" plain size="small" icon="Delete" @click="removeSuite(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      </CatalogListLayout>
    </template>
    <template #bottom>
      <el-pagination v-model:current-page="page.page" v-model:page-size="page.size" :total="page.total" layout="total, prev, pager, next" @current-change="loadList" @size-change="loadList" />
    </template>
  </PageCard>
  <AppRunDialog v-model="runDlg" :loading="running" @submit="runSuite" />

  <el-dialog v-model="recordDlg" width="90%" destroy-on-close title="套件执行报告">
    <AppSuiteRecord v-if="recordSuite.id" :suite-id="recordSuite.id" :project-id="proStore.projectInfo.id" />
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import AppRunDialog from '@/components/AppRunDialog.vue'
import AppSuiteRecord from '@/views/App/components/AppSuiteRecord.vue'
import { appSuiteApi, appExecApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const canEdit = computed(() => uStore.hasPermission('app_suite:edit'))
const canExecute = computed(() => uStore.hasPermission('app_suite:execute'))

const suiteList = ref([])
const page = reactive({ page: 1, size: 10, total: 0 })
const searchForm = reactive({ name: '', catalog_id: null })
const runDlg = ref(false)
const running = ref(false)
const runSuiteId = ref(null)
const recordDlg = ref(false)
const recordSuite = ref({ id: null })

async function loadList() {
  const catalogId = searchForm.catalog_id && searchForm.catalog_id !== 'all' ? searchForm.catalog_id : undefined
  const res = await appSuiteApi.list({
    project_id: proStore.projectInfo.id,
    page: page.page,
    size: page.size,
    name: searchForm.name || undefined,
    catalog_id: catalogId
  })
  suiteList.value = res.data?.data || []
  page.total = res.data?.total || 0
}

function openRun(id) {
  runSuiteId.value = id
  runDlg.value = true
}

function openRecords(row) {
  recordSuite.value = row
  recordDlg.value = true
}

async function runSuite(payload) {
  running.value = true
  try {
    const res = await appExecApi.runSuite(runSuiteId.value, payload)
    runDlg.value = false
    const dispatched = res.data?.dispatched !== false
    ElNotification({ title: dispatched ? '已提交运行' : '记录已创建', message: res.data?.msg, type: dispatched ? 'success' : 'warning' })
  } finally {
    running.value = false
  }
}

async function removeSuite(row) {
  try {
    await ElMessageBox.confirm(`确定删除套件「${row.name}」？`, '提示', { type: 'warning' })
    await appSuiteApi.remove(row.id)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
  }
}

loadList()
</script>
