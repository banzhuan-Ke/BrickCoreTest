<template>
  <div class="run-records">
    <!-- 头部工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-select v-model="filter.record_type" placeholder="记录类型" clearable style="width: 120px; margin-right: 10px">
          <el-option label="全部" value="" />
          <el-option label="套件" value="suite" />
          <el-option label="计划" value="plan" />
        </el-select>
        <el-input v-model="filter.keyword" placeholder="搜索套件/计划名称" clearable style="width: 200px; margin-right: 10px" />
        <el-select v-model="filter.status" placeholder="筛选状态" clearable style="width: 120px; margin-right: 10px">
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="执行中" value="running" />
        </el-select>
        <el-button @click="handleSearch">查询</el-button>
        <el-button
          v-if="selectedRecords.length > 0"
          type="danger"
          @click="handleBatchDelete"
        >批量删除({{ selectedRecords.length }})</el-button>
      </div>
    </div>
    
    <!-- 记录列表 -->
    <el-table 
      :data="recordList" 
      v-loading="loading" 
      border
      height="calc(100vh - 240px)"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column type="index" width="50" />
      <el-table-column prop="record_type" label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.record_type === 'plan' ? 'warning' : 'primary'" size="small">
            {{ row.record_type === 'plan' ? '计划' : '套件' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column prop="status" label="执行状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="trigger_type" label="触发方式" width="100">
        <template #default="{ row }">
          {{ getTriggerText(row.trigger_type) }}
        </template>
      </el-table-column>
      <el-table-column label="用例统计" width="200">
        <template #default="{ row }">
          <div class="stats">
            <span>共{{ row.total_cases }}</span>
            <span class="success">成{{ row.success_cases }}</span>
            <span class="failed">败{{ row.failed_cases }}</span>
            <span v-if="row.skipped_cases !== null && row.skipped_cases !== undefined" class="skipped">跳{{ row.skipped_cases }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="env_name" label="执行环境" width="120" />
      <el-table-column prop="start_time" label="开始时间" width="160">
        <template #default="{ row }">
          {{ formatDate(row.start_time) }}
        </template>
      </el-table-column>
      <el-table-column prop="duration" label="执行总耗时(ms)" width="120">
        <template #default="{ row }">
          {{ row.duration ? row.duration.toFixed(0) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="http_duration" label="接口总耗时(ms)" width="120">
        <template #default="{ row }">
          <span v-if="row.http_duration != null" class="http-duration-cell">
            {{ row.http_duration.toFixed(0) }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="run_by" label="执行人" width="100" />
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="{ row }">
          <div class="table-row-actions">
            <el-button link type="primary" @click="viewDetail(row)">查看详情</el-button>
            <el-button link type="info" @click="openReportPage(row)">报告页</el-button>
            <el-button link type="success" @click="exportReport(row)">导出报告</el-button>
            <el-button link type="warning" @click="sendReport(row)">发送报告</el-button>
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
    
    <!-- 详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="执行详情" width="1000px" destroy-on-close>
      <div style="max-height: 70vh; overflow-y: auto; padding-right: 4px;">
        <ApiRunDetail
          v-if="detailDialogVisible"
          :record-id="currentRecordId"
          :record-type="currentRecordType"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/index'
import ApiRunDetail from './components/ApiRunDetail.vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const projectId = computed(() => Number(route.params.projectId) || proStore.projectInfo.id)

const loading = ref(false)
const recordList = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(10)

const filter = reactive({
  record_type: '',
  keyword: '',
  status: null
})

const selectedRecords = ref([])

const detailDialogVisible = ref(false)
const currentRecordId = ref(null)
const currentRecordType = ref('suite')

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString()
}

const getStatusType = (status) => {
  const types = {
    success: 'success',
    failed: 'danger',
    running: 'info',
    partial: 'warning'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    success: '成功',
    failed: '失败',
    running: '执行中',
    partial: '部分失败'
  }
  return texts[status] || status
}

const getTriggerText = (type) => {
  const texts = {
    manual: '手动',
    cron: '定时任务',
    ci: 'CI触发',
    plan: '计划执行',
    assistant: '小测'
  }
  return texts[type] || type
}

const fetchRecords = async () => {
  loading.value = true
  try {
    const params = {
      project_id: projectId.value,
      page: page.value,
      size: size.value
    }
    if (filter.record_type) params.record_type = filter.record_type
    if (filter.keyword) params.keyword = filter.keyword
    if (filter.status) params.status = filter.status
    
    const res = await http.apiModuleApi.getRunRecords(params)
    recordList.value = res.data?.data || []
    total.value = res.data?.total || 0
  } catch (error) {
    console.error('获取执行记录失败:', error)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  fetchRecords()
}

const handleSizeChange = (val) => {
  size.value = val
  fetchRecords()
}

const handlePageChange = (val) => {
  page.value = val
  fetchRecords()
}

const viewDetail = (row) => {
  currentRecordId.value = Number(row.id)
  currentRecordType.value = row.record_type || 'suite'
  detailDialogVisible.value = true
}

const openReportPage = (row) => {
  const type = row.record_type || 'suite'
  router.push(`/api-module/report/${row.id}?type=${type}`)
}

const exportReport = async (row) => {
  try {
    if (row.record_type === 'plan') {
      const res = await http.apiModuleApi.exportPlanReport(row.id)
      const blob = new Blob([res.data], { type: 'text/html' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `api_plan_report_${row.id}_${new Date().getTime()}.html`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } else {
      const res = await http.apiModuleApi.exportApiSuiteReport(row.id)
      const blob = new Blob([res.data], { type: 'text/html' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `api_report_${row.id}_${new Date().getTime()}.html`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    }
  } catch (error) {
    console.error('导出报告失败:', error)
    ElMessage.error(error?.response?.data?.detail || '导出报告失败')
  }
}

const sendReport = async (row) => {
  try {
    if (row.record_type === 'plan') {
      const res = await http.apiModuleApi.sendPlanReport(row.id)
      if (res.status === 200) {
        ElMessage.success(res.data.detail || '报告邮件已发送')
      }
    } else {
      const res = await http.apiModuleApi.sendSuiteReport(row.id)
      if (res.status === 200) {
        ElMessage.success(res.data.detail || '报告邮件已发送')
      }
    }
  } catch (error) {
    console.error('发送报告失败:', error)
    ElMessage.error(error?.response?.data?.detail || '发送报告失败')
  }
}

const handleSelectionChange = (selection) => {
  selectedRecords.value = selection
}

const handleBatchDelete = async () => {
  if (selectedRecords.value.length === 0) {
    ElMessage.warning('请选择要删除的记录')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedRecords.value.length} 条记录吗？此操作不可恢复！`,
      '警告',
      { type: 'warning' }
    )
    // 按类型分组
    const suiteIds = selectedRecords.value.filter(r => r.record_type === 'suite').map(r => r.id)
    const planIds = selectedRecords.value.filter(r => r.record_type === 'plan').map(r => r.id)
    
    if (suiteIds.length > 0) {
      await http.apiModuleApi.batchDeleteSuiteRecords(suiteIds)
    }
    if (planIds.length > 0) {
      await http.apiModuleApi.batchDeletePlanRecords(planIds)
    }
    
    ElMessage.success('批量删除成功')
    selectedRecords.value = []
    fetchRecords()
  } catch (err) {
    if (err !== 'cancel') {
      console.error(err)
      ElMessage.error('批量删除失败')
    }
  }
}

onMounted(() => {
  fetchRecords()
})
</script>

<style lang="scss" scoped>
.run-records {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.stats {
  display: flex;
  gap: 12px;
  font-size: 13px;
  
  .success {
    color: #67c23a;
  }
  
  .failed {
    color: #f56c6c;
  }
  
  .skipped {
    color: #909399;
  }
}

.http-duration-cell {
  color: #67c23a;
  font-weight: 600;
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
