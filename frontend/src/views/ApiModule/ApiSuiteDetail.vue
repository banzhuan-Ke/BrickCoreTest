<template>
  <div class="suite-detail">
    <!-- 头部信息 -->
    <el-card class="info-card" shadow="hover">
      <div class="suite-header">
        <div class="left">
          <h2>{{ suiteInfo.name }}</h2>
          <p class="description">{{ suiteInfo.description || '暂无描述' }}</p>
          <div class="meta">
            <span>用例数: {{ suiteInfo.case_count }}</span>
            <span>超时: {{ suiteInfo.timeout }}s</span>
            <span>重试: {{ suiteInfo.retry_count }}次</span>
            <el-tag size="small" :type="suiteInfo.stop_on_failure ? 'danger' : 'info'">
              {{ suiteInfo.stop_on_failure ? '失败停止' : '失败继续' }}
            </el-tag>
          </div>
        </div>
        <div class="right">
          <el-button type="primary" @click="handleRun">
            <el-icon><VideoPlay /></el-icon>执行套件
          </el-button>
          <el-button @click="goBack">
            <el-icon><Back /></el-icon>返回
          </el-button>
        </div>
      </div>
    </el-card>
    
    <!-- 用例列表 -->
    <el-card class="case-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>套件用例 ({{ caseList.length }})</span>
          <el-button link type="primary" @click="showEditCases">
            <el-icon><Edit /></el-icon>编辑用例
          </el-button>
        </div>
      </template>
      
      <el-table :data="orderedCaseList" border v-loading="loading">
        <el-table-column label="执行序号" width="96" align="center">
          <template #default="{ row }">
            <span class="exec-order-badge">{{ row.exec_order }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="case_name" label="用例名称" min-width="150" />
        <el-table-column prop="api_name" label="关联接口" min-width="150" />
        <el-table-column prop="api_method" label="方法" width="80">
          <template #default="{ row }">
            <el-tag :type="getMethodType(row.api_method)" size="small">
              {{ row.api_method }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 执行记录 -->
    <el-card class="record-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>最近执行记录</span>
          <el-button link type="primary" @click="goToRecords">查看全部</el-button>
        </div>
      </template>
      
      <el-table :data="recordList" border>
        <el-table-column prop="start_time" label="执行时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.start_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_cases" label="用例数" width="80" />
        <el-table-column prop="success_cases" label="成功" width="80">
          <template #default="{ row }">
            <span style="color: #67c23a">{{ row.success_cases }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="failed_cases" label="失败" width="80">
          <template #default="{ row }">
            <span style="color: #f56c6c">{{ row.failed_cases }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="env_name" label="环境" width="120" />
        <el-table-column prop="run_by" label="执行人" width="100" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewRecord(row)">查看</el-button>
            <el-button link type="info" @click="openReportPage(row)">报告页</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 执行套件对话框 -->
    <el-dialog v-model="runDialogVisible" title="执行套件" width="400px" destroy-on-close>
      <el-form :model="runForm" label-width="100px">
        <el-form-item label="执行环境" required>
          <el-select v-model="runForm.env_id" placeholder="选择环境" style="width: 100%">
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
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmRun" :loading="running">执行</el-button>
      </template>
    </el-dialog>
    
    <!-- 编辑用例对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑套件用例" width="960px" destroy-on-close>
      <ApiSuiteCasePicker v-model="selectedCaseIds" :case-options="allCases" />
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCases" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
    
    <!-- 执行详情对话框 -->
    <el-dialog v-model="recordDialogVisible" title="执行详情" width="900px" destroy-on-close>
      <ApiRunDetail :record-id="currentRecordId" v-if="recordDialogVisible" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { VideoPlay, Back, Edit } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import ApiRunDetail from './components/ApiRunDetail.vue'
import ApiSuiteCasePicker from './components/ApiSuiteCasePicker.vue'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const suiteId = ref(Number(route.params.suiteId))
const projectId = ref(proStore.projectInfo.id)

const loading = ref(false)
const suiteInfo = reactive({
  name: '',
  description: '',
  case_count: 0,
  timeout: 300,
  retry_count: 0,
  stop_on_failure: false,
  env_id: null
})
const caseList = ref([])
const recordList = ref([])

const orderedCaseList = computed(() => {
  return [...caseList.value]
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((item, index) => ({
      ...item,
      exec_order: index + 1
    }))
})

// 执行对话框
const runDialogVisible = ref(false)
const runForm = reactive({ env_id: null })
const running = ref(false)

// 编辑用例
const editDialogVisible = ref(false)
const selectedCaseIds = ref([])
const allCases = ref([])
const saving = ref(false)

// 记录详情
const recordDialogVisible = ref(false)
const currentRecordId = ref(null)

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString()
}

const getMethodType = (method) => {
  const types = {
    GET: 'success',
    POST: 'primary',
    PUT: 'warning',
    DELETE: 'danger'
  }
  return types[method?.toUpperCase()] || ''
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

const fetchSuiteDetail = async () => {
  loading.value = true
  try {
    const res = await http.apiModuleApi.getSuiteDetail(suiteId.value)
    const data = res.data || res
    Object.assign(suiteInfo, data)
    caseList.value = data.cases || []
  } catch (error) {
    console.error('获取套件详情失败:', error)
    ElMessage.error('获取套件详情失败')
  } finally {
    loading.value = false
  }
}

const fetchRecords = async () => {
  try {
    const res = await http.apiModuleApi.getRunRecords({
      project_id: projectId.value,
      suite_id: suiteId.value,
      page: 1,
      size: 10
    })
    recordList.value = res.data?.data || []
  } catch (error) {
    console.error('获取执行记录失败:', error)
  }
}

const handleRun = () => {
  if (!proStore.envList?.length) {
    ElMessage.warning('请先选择测试环境')
    return
  }
  runForm.env_id = suiteInfo.env_id || proStore.envList[0]?.id
  runDialogVisible.value = true
}

const confirmRun = async () => {
  if (!runForm.env_id) {
    ElMessage.warning('请选择执行环境')
    return
  }
  running.value = true
  try {
    const res = await http.apiModuleApi.runSuiteAsync(suiteId.value, runForm)
    const data = res.data
    runDialogVisible.value = false
    ElMessage.info('套件已开始后台执行，请稍候…')
    startPolling(data.record_id)
  } catch (error) {
    console.error('执行失败:', error)
    ElMessage.error('执行失败')
  } finally {
    running.value = false
  }
}

const pollingTimer = ref(null)

const startPolling = (recordId) => {
  pollingTimer.value = setInterval(async () => {
    try {
      const res = await http.apiModuleApi.getSuiteRecordDetail(recordId)
      const data = res.data
      if (data.status !== 'running') {
        stopPolling()
        const total = data.total_cases ?? 0
        const success = data.success_cases ?? 0
        const failed = data.failed_cases ?? 0
        ElMessage({
          type: failed > 0 ? 'warning' : 'success',
          message: `套件执行完成：共 ${total} 条，通过 ${success}，失败 ${failed}`,
          duration: 5000
        })
        fetchRecords()
      }
    } catch (err) {
      console.error('轮询套件状态失败:', err)
    }
  }, 3000)
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

onUnmounted(() => stopPolling())

const showEditCases = async () => {
  try {
    // 获取所有可用用例
    const res = await http.apiModuleApi.getTestCaseList({
      project_id: projectId.value,
      page: 1,
      size: 1000
    })
    allCases.value = (res.data?.data || []).map(c => ({
      id: c.id,
      name: c.name,
      api_name: c.api_name,
      priority: c.priority || 'P2'
    }))
    
    selectedCaseIds.value = [...caseList.value]
      .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
      .map((c) => c.case_id)
    editDialogVisible.value = true
  } catch (error) {
    console.error('获取用例列表失败:', error)
  }
}

const saveCases = async () => {
  saving.value = true
  try {
    await http.apiModuleApi.updateSuite(suiteId.value, {
      name: suiteInfo.name,
      env_id: suiteInfo.env_id,
      timeout: suiteInfo.timeout,
      retry_count: suiteInfo.retry_count,
      stop_on_failure: suiteInfo.stop_on_failure,
      parallel: suiteInfo.parallel,
      description: suiteInfo.description,
      case_ids: selectedCaseIds.value
    })
    ElMessage.success('保存成功')
    editDialogVisible.value = false
    fetchSuiteDetail()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const viewRecord = (row) => {
  currentRecordId.value = row.id
  recordDialogVisible.value = true
}

const openReportPage = (row) => {
  router.push(`/api-module/report/${row.id}`)
}

const goToRecords = () => {
  router.push(`/api-run-records`)
}

const goBack = () => {
  router.back()
}

onMounted(() => {
  fetchSuiteDetail()
  fetchRecords()
})
</script>

<style lang="scss" scoped>
.suite-detail {
  padding: 20px;
}

.info-card {
  margin-bottom: 20px;
}

.suite-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  
  .left {
    h2 {
      margin: 0 0 10px;
    }
    
    .description {
      color: #666;
      margin: 0 0 15px;
    }
    
    .meta {
      display: flex;
      gap: 20px;
      align-items: center;
      font-size: 14px;
      color: #666;
    }
  }
  
  .right {
    display: flex;
    gap: 10px;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.case-card, .record-card {
  margin-bottom: 20px;
}

.exec-order-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 26px;
  padding: 0 6px;
  border-radius: 13px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
</style>
