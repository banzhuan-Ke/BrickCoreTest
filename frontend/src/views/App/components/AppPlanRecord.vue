<template>
  <div class="app-run-record">
    <el-table
      :data="records"
      stripe
      :header-cell-style="{ 'text-align': 'center' }"
      :cell-style="{ 'text-align': 'center' }"
      v-loading="loading"
    >
      <el-table-column type="index" label="序号" width="70" />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="planStatusTag(row.status).type">{{ planStatusTag(row.status).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="pass_rate" label="通过率" width="100">
        <template #default="{ row }">{{ (row.pass_rate || 0).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column prop="duration" label="耗时(s)" width="90" />
      <el-table-column prop="username" label="执行人" width="100" />
      <el-table-column prop="start_time" label="执行时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.start_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button v-if="isStoppable(row.status)" type="warning" size="small" @click="stopRun(row.id)">停止</el-button>
          <el-button type="success" size="small" @click="openReport(row.id)">查看报告</el-button>
          <el-button type="danger" size="small" plain @click="deleteRecord(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="page.total > page.size"
      v-model:current-page="page.page"
      v-model:page-size="page.size"
      :total="page.total"
      layout="total, prev, pager, next"
      class="pager"
      @current-change="loadList"
    />
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { appExecApi, appRecordApi } from '@/api'
import dateTools from '@/tools/dateTools.js'

const props = defineProps({
  planId: { type: Number, required: true },
  projectId: { type: Number, required: true },
})

const router = useRouter()
const records = ref([])
const loading = ref(false)
const page = reactive({ page: 1, size: 10, total: 0 })

function formatTime(v) {
  return v ? dateTools.rTime(v) : '-'
}

function planStatusTag(status) {
  if (status === '执行完成') return { text: '执行完成', type: 'success' }
  if (status === '执行中') return { text: '执行中', type: 'primary' }
  if (status === '等待执行') return { text: '等待执行', type: 'info' }
  if (status === '已停止') return { text: '已停止', type: 'warning' }
  return { text: status || '-', type: 'info' }
}

function isStoppable(status) {
  return status === '执行中' || status === '等待执行'
}

async function loadList() {
  if (!props.planId || !props.projectId) return
  loading.value = true
  try {
    const res = await appRecordApi.listPlans({
      project_id: props.projectId,
      plan_id: props.planId,
      page: page.page,
      size: page.size,
    })
    records.value = res.data?.data || []
    page.total = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

function openReport(recordId) {
  router.push({ name: 'appPlanReport', params: { id: recordId } })
}

async function stopRun(recordId) {
  try {
    await ElMessageBox.confirm('确定停止当前计划执行吗？', '停止执行', { type: 'warning' })
    await appExecApi.stopPlan(recordId)
    ElMessage.success('停止信号已发送')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '停止失败')
  }
}

async function deleteRecord(recordId) {
  try {
    await ElMessageBox.confirm('删除后该计划执行记录及下属套件/用例记录将从列表中隐藏，确定继续吗？', '删除记录', { type: 'warning' })
    await appRecordApi.deletePlan(recordId)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

watch(() => [props.planId, props.projectId], loadList, { immediate: true })
</script>

<style scoped>
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
