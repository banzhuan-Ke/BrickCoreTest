<template>
  <div>
    <div class="toolbar">
      <el-input v-model="filters.keyword" placeholder="搜索任务/用例/URL" clearable style="width: 220px;" @keyup.enter="loadList" />
      <el-select v-model="filters.status" clearable placeholder="状态" style="width: 120px;" @change="loadList">
        <el-option label="完成" value="done" />
        <el-option label="失败" value="failed" />
        <el-option label="执行中" value="running" />
        <el-option label="已停止" value="stopped" />
      </el-select>
      <el-button type="primary" @click="loadList">查询</el-button>
      <el-button @click="resetFilters">重置</el-button>
      <el-button
        v-if="canExecute && selectedIds.length"
        type="danger"
        @click="removeBatch"
      >
        批量删除 ({{ selectedIds.length }})
      </el-button>
    </div>

    <el-table :data="list" v-loading="loading" stripe @selection-change="onSelectionChange">
      <el-table-column v-if="canExecute" type="selection" width="42" :selectable="rowSelectable" />
      <el-table-column prop="id" label="#" width="64" />
      <el-table-column prop="case_name" label="用例" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.case_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="88" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="task_text" label="任务描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="steps_count" label="步数" width="64" align="center" />
      <el-table-column prop="tokens_used" label="Tokens" width="88" align="right">
        <template #default="{ row }">{{ formatTokens(row.tokens_used) }}</template>
      </el-table-column>
      <el-table-column prop="duration_sec" label="耗时(s)" width="80" align="center">
        <template #default="{ row }">{{ row.duration_sec ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_by" label="执行人" width="100" show-overflow-tooltip />
      <el-table-column prop="create_time" label="执行时间" width="160">
        <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="goReport(row)">报告</el-button>
          <el-button v-if="canExecute" link type="primary" @click="rerun(row)">重跑</el-button>
          <el-button v-if="canExecute && ['pending','running'].includes(row.status)" link type="warning" @click="stop(row)">停止</el-button>
          <el-button v-if="canExecute && !['pending','running'].includes(row.status)" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadList"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { browserLabApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => ProjectStore().projectInfo?.id)
const canExecute = computed(() => UserStore().hasPermission('ai_test:execute'))

const loading = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const filters = ref({ keyword: '', status: '', case_id: null })
const selectedIds = ref([])

function rowSelectable(row) {
  return !['pending', 'running'].includes(row.status)
}

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map((r) => r.id)
}

function statusLabel(s) {
  return { done: '完成', running: '执行中', failed: '失败', stopped: '已停止', pending: '等待' }[s] || s
}
function statusTag(s) {
  return { done: 'success', running: 'warning', failed: 'danger', stopped: 'info' }[s] || 'info'
}
function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '-'
}

function formatTokens(n) {
  const v = Number(n || 0)
  if (!v) return '-'
  if (v >= 10000) return `${(v / 1000).toFixed(1)}k`
  return String(v)
}

async function loadList() {
  if (!projectId.value) return
  loading.value = true
  try {
    const params = { page: page.value, size: size.value, keyword: filters.value.keyword || undefined, status: filters.value.status || undefined }
    if (filters.value.case_id) params.case_id = filters.value.case_id
    const res = await browserLabApi.listTasks(projectId.value, params)
    if (res.data?.code === 200) {
      list.value = res.data.data?.list || []
      total.value = res.data.data?.total || 0
    }
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.value = { keyword: '', status: '', case_id: route.query.caseId ? Number(route.query.caseId) : null }
  page.value = 1
  loadList()
}

function goReport(row) {
  router.push({ name: 'browserLabReport', params: { taskId: row.id } })
}

async function rerun(row) {
  const res = await browserLabApi.rerunTask(row.id, projectId.value)
  if (res.data?.code === 200) {
    ElMessage.success('已重新执行')
    router.push({ path: '/browser-lab/run', query: { taskId: res.data.data?.id } })
  }
}

async function stop(row) {
  await browserLabApi.stopTask(row.id, projectId.value)
  ElMessage.success('已发送停止')
  loadList()
}

async function remove(row) {
  await ElMessageBox.confirm(
    `确定永久删除执行记录 #${row.id}？\n将同时删除数据库记录及步骤截图/GIF 文件，不可恢复。`,
    '永久删除',
    { type: 'warning' }
  )
  const res = await browserLabApi.deleteTask(row.id, projectId.value)
  if (res.data?.code === 200) {
    ElMessage.success(res.data.message || '已删除')
    loadList()
  }
}

async function removeBatch() {
  if (!selectedIds.value.length) return
  await ElMessageBox.confirm(
    `确定永久删除选中的 ${selectedIds.value.length} 条执行记录？\n将同时删除截图/GIF 文件，不可恢复；执行中的任务会自动跳过。`,
    '批量永久删除',
    { type: 'warning' }
  )
  const res = await browserLabApi.deleteTasks(selectedIds.value, projectId.value)
  if (res.data?.code === 200) {
    ElMessage.success(res.data.message || '已删除')
    selectedIds.value = []
    loadList()
  }
}

watch(() => route.query.caseId, (v) => {
  filters.value.case_id = v ? Number(v) : null
  loadList()
})

onMounted(() => {
  if (route.query.caseId) filters.value.case_id = Number(route.query.caseId)
  loadList()
})
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
</style>
