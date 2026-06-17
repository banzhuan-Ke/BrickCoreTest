<template>
  <div class="suite-list">
    <CatalogListLayout
      :project-id="projectId"
      v-model="catalogId"
      all-node-label="全部套件"
      @change="handleSearch"
    >
    <!-- 头部工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>新建套件
        </el-button>
      </div>
      <div class="right">
        <el-button
          v-if="selectedSuites.length > 0"
          type="danger"
          @click="handleBatchDelete"
          icon="Delete"
          style="margin-right: 10px"
        >批量删除({{ selectedSuites.length }})</el-button>
        <el-input
          v-model="keyword"
          placeholder="搜索套件名称"
          style="width: 200px"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #suffix>
            <el-icon @click="handleSearch"><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </div>
    
    <!-- 套件列表 -->
    <el-table :data="suiteList" v-loading="loading" border @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column type="index" :index="tableRowIndex" width="50" />
      <el-table-column prop="name" label="套件名称" min-width="150" show-overflow-tooltip />
      <el-table-column prop="catalog_name" label="所属目录" width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.catalog_name || row.module_name || '—' }}</template>
      </el-table-column>
      <el-table-column prop="case_count" label="用例数" width="80" align="center" />
      <el-table-column label="执行模式" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.parallel ? 'warning' : 'info'" size="small">
            {{ row.parallel ? '并行' : '串行' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
      <el-table-column prop="create_by" label="创建人" width="100" />
      <el-table-column label="修改人" width="100">
        <template #default="{ row }">{{ row.update_by || row.create_by || '—' }}</template>
      </el-table-column>
      <el-table-column prop="create_time" label="创建时间" width="160">
        <template #default="{ row }">
          {{ formatDate(row.create_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleRun(row)">
            <el-icon><VideoPlay /></el-icon>执行
          </el-button>
          <el-button link type="primary" @click="handleEdit(row)">编辑</el-button>
          <el-button link type="primary" @click="handleDetail(row)">详情</el-button>
          <el-popconfirm title="确定删除吗?" @confirm="handleDelete(row)">
            <template #reference>
              <el-button link type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    
    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>
    </CatalogListLayout>
    
    <!-- 新建/编辑套件对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="960px"
      :close-on-click-modal="false"
      destroy-on-close
      @closed="handleDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="套件名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入套件名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属目录" prop="catalog_id">
              <CatalogTreeSelect
                v-model="form.catalog_id"
                :project-id="projectId"
                placeholder="选择目录"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="默认环境" prop="env_id">
              <el-select v-model="form.env_id" placeholder="选择默认环境" clearable style="width: 100%">
                <el-option
                  v-for="env in proStore.envList"
                  :key="env.id"
                  :label="env.name"
                  :value="env.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="超时时间(秒)">
              <el-input-number v-model="form.timeout" :min="10" :max="3600" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="失败重试">
              <el-input-number v-model="form.retry_count" :min="0" :max="5" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item>
              <el-checkbox v-model="form.stop_on_failure">失败时停止</el-checkbox>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="执行模式">
          <el-switch
            v-model="form.parallel"
            active-text="并行执行"
            inactive-text="串行执行"
          />
          <span class="hint-text" style="margin-left:12px;color:var(--el-text-color-secondary);font-size:12px">
            串行模式下用例按序执行且提取变量可传递；并行模式下用例同时执行，变量不传递
          </span>
        </el-form-item>
        
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-collapse class="suite-hooks-collapse">
          <el-collapse-item title="数据工厂（前置/后置 SQL）" name="sql">
            <el-form-item label="前置 SQL">
              <el-select v-model="form.setup_sql_ids" multiple filterable placeholder="选择 setup 模板" style="width: 100%">
                <el-option v-for="t in setupTemplates" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="后置 SQL">
              <el-select v-model="form.teardown_sql_ids" multiple filterable placeholder="选择 teardown 模板" style="width: 100%">
                <el-option v-for="t in teardownTemplates" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
            </el-form-item>
          </el-collapse-item>
          <el-collapse-item title="套件级数据库断言" name="db">
            <DbAssertionsEditor v-model="form.db_assertions" :datasources="datasources" />
          </el-collapse-item>
        </el-collapse>
        
        <el-form-item label="套件用例" prop="case_ids">
          <ApiSuiteCasePicker v-model="form.case_ids" :case-options="caseOptions" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
    
    <!-- 执行套件对话框 -->
    <el-dialog
      v-model="runDialogVisible"
      title="执行套件"
      width="500px"
      destroy-on-close
    >
      <el-form :model="runForm" label-width="100px">
        <el-form-item label="执行环境">
          <el-select v-model="runForm.env_id" placeholder="选择执行环境（默认使用套件配置）" clearable style="width: 100%">
            <el-option
              v-for="env in proStore.envList"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
          <div v-if="currentSuite?.env_id" class="env-tip">
            套件默认环境: {{ proStore.envList.find(e => e.id === currentSuite.env_id)?.name || '未知' }}
          </div>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="runDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmRun" :loading="running">开始执行</el-button>
      </template>
    </el-dialog>
    
    <!-- 执行中状态提示（后台执行期间显示） -->
    <el-dialog
      v-model="polling"
      title="套件执行中"
      width="400px"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <div style="text-align: center; padding: 20px 0;">
        <el-icon class="is-loading" style="font-size: 40px; color: #409eff;"><Loading /></el-icon>
        <p style="margin-top: 16px; color: #606266;">正在后台执行测试套件，请稍候…</p>
        <p style="font-size: 12px; color: #909399;">每隔 3 秒自动检查执行状态</p>
      </div>
      <template #footer>
        <el-button @click="stopPollingAndClose">后台运行（不等待）</el-button>
      </template>
    </el-dialog>

    <!-- 执行结果对话框 -->
    <el-dialog
      v-model="resultDialogVisible"
      title="执行结果"
      width="900px"
      destroy-on-close
    >
      <el-result
        v-if="runResult"
        :icon="runResult.failed === 0 ? 'success' : 'warning'"
        :title="runResult.failed === 0 ? '执行成功' : '部分失败'"
        :sub-title="`共 ${runResult.total} 个用例，成功 ${runResult.success} 个，失败 ${runResult.failed} 个`"
      />

      <el-table v-if="runResult" :data="runResult.results" border>
        <el-table-column label="执行序号" width="88" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="case_name" label="用例名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'">
              {{ row.status === 'success' ? '通过' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="response_status" label="HTTP状态" width="100" />
        <el-table-column label="接口耗时(ms)" width="110">
          <template #default="{ row }">
            <span v-if="getHttpResponseMs(row) != null" style="color:#67c23a;font-weight:600">
              {{ getHttpResponseMs(row).toFixed(2) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="用例总耗时(ms)" width="110">
          <template #default="{ row }">
            {{ row.response_time ? row.response_time.toFixed(2) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误信息" show-overflow-tooltip />
      </el-table>

      <template #footer>
        <el-button @click="resultDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="goToRecord">查看详细报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, VideoPlay, Loading } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import ApiSuiteCasePicker from './components/ApiSuiteCasePicker.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import { getHttpResponseMs } from './utils/runTiming'
import DbAssertionsEditor from './components/DbAssertionsEditor.vue'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import { makeTableRowIndexRefs } from '@/utils/tableIndex'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()

const projectId = computed(() => Number(route.params.projectId) || proStore.projectInfo.id)

// 列表相关
const loading = ref(false)
const suiteList = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const tableRowIndex = makeTableRowIndexRefs(page, size)
const keyword = ref('')
const catalogId = ref(null)
const selectedSuites = ref([])

// 对话框
const dialogVisible = ref(false)
const dialogTitle = ref('新建套件')
const formRef = ref()
const submitting = ref(false)
const isEdit = ref(false)
const currentId = ref(null)

// 执行相关
const runDialogVisible = ref(false)
const runForm = reactive({ env_id: null })
const running = ref(false)
const currentSuite = ref(null)
const resultDialogVisible = ref(false)
const runResult = ref(null)

// 轮询相关
const polling = ref(false)
const pollingRecordId = ref(null)
const pollingTimer = ref(null)
const pollingStatus = ref('')  // 'running' | 'done'

// 用例选项
const caseOptions = ref([])
const datasources = ref([])
const sqlTemplates = ref([])
const setupTemplates = computed(() => sqlTemplates.value.filter(t => t.template_type === 'setup'))
const teardownTemplates = computed(() => sqlTemplates.value.filter(t => t.template_type === 'teardown'))

const loadFactoryMeta = async () => {
  try {
    const [dsRes, tplRes] = await Promise.all([
      dataFactoryApi.listDatasources({ project_id: projectId.value, size: 100 }),
      dataFactoryApi.listSqlTemplates({ project_id: projectId.value, size: 200 }),
    ])
    datasources.value = dsRes.data?.list || []
    sqlTemplates.value = tplRes.data?.list || []
  } catch {
    datasources.value = []
    sqlTemplates.value = []
  }
}

const form = reactive({
  name: '',
  catalog_id: null,
  env_id: null,
  timeout: 300,
  retry_count: 0,
  stop_on_failure: false,
  parallel: false,
  description: '',
  case_ids: [],
  setup_sql_ids: [],
  teardown_sql_ids: [],
  db_assertions: [],
})

const rules = {
  name: [{ required: true, message: '请输入套件名称', trigger: 'blur' }],
  case_ids: [{ required: true, message: '请至少选择一个用例', trigger: 'change', type: 'array' }]
}

const sortCaseIdsByOrder = (cases) => {
  if (!cases?.length) return []
  return [...cases]
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((c) => c.case_id)
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString()
}

const fetchSuites = async () => {
  loading.value = true
  try {
    const res = await http.apiModuleApi.getSuiteList({
      project_id: projectId.value,
      keyword: keyword.value,
      catalog_id: catalogId.value,
      page: page.value,
      size: size.value
    })
    suiteList.value = res.data?.data || []
    total.value = res.data?.total || 0
  } catch (error) {
    console.error('获取套件列表失败:', error)
  } finally {
    loading.value = false
  }
}

const fetchCases = async () => {
  try {
    const res = await http.apiModuleApi.getTestCaseList({
      project_id: projectId.value,
      page: 1,
      size: 1000
    })
    caseOptions.value = (res.data?.data || []).map(c => ({
      id: c.id,
      name: c.name,
      api_name: c.api_name,
      priority: c.priority || 'P2'
    }))
  } catch (error) {
    console.error('获取用例列表失败:', error)
  }
}

const handleSearch = () => {
  page.value = 1
  fetchSuites()
}

const handleSizeChange = (val) => {
  size.value = val
  fetchSuites()
}

const handlePageChange = (val) => {
  page.value = val
  fetchSuites()
}

const resetForm = () => {
  Object.assign(form, {
    name: '',
    catalog_id: null,
    env_id: null,
    timeout: 300,
    retry_count: 0,
    stop_on_failure: false,
    parallel: false,
    description: '',
    case_ids: [],
    setup_sql_ids: [],
    teardown_sql_ids: [],
    db_assertions: [],
  })
  isEdit.value = false
  currentId.value = null
}

// 弹窗关闭后重置
const handleDialogClosed = () => {
  resetForm()
}

const handleCreate = () => {
  resetForm()
  dialogTitle.value = '新建套件'
  dialogVisible.value = true
  fetchCases()
  loadFactoryMeta()
}

const handleEdit = async (row) => {
  resetForm()
  dialogTitle.value = '编辑套件'
  isEdit.value = true
  currentId.value = row.id
  await fetchCases()
  await loadFactoryMeta()
  
  try {
    const res = await http.apiModuleApi.getSuiteDetail(row.id)
    const data = res.data || res
    Object.assign(form, {
      name: data.name,
      catalog_id: data.catalog_id ?? data.module_id,
      env_id: data.env_id,
      timeout: data.timeout,
      retry_count: data.retry_count,
      stop_on_failure: data.stop_on_failure,
      parallel: data.parallel,
      description: data.description,
      case_ids: sortCaseIdsByOrder(data.cases),
      setup_sql_ids: data.setup_sql_ids || [],
      teardown_sql_ids: data.teardown_sql_ids || [],
      db_assertions: data.db_assertions || [],
    })
    dialogVisible.value = true
  } catch (error) {
    console.error('获取套件详情失败:', error)
  }
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  
  submitting.value = true
  try {
    const data = {
      project_id: projectId.value,
      ...form,
    }
    
    if (isEdit.value) {
      await http.apiModuleApi.updateSuite(currentId.value, data)
    } else {
      await http.apiModuleApi.createSuite(data)
    }
    
    ElMessage.success(isEdit.value ? '更新成功' : '创建成功')
    dialogVisible.value = false
    fetchSuites()
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error('保存失败')
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row) => {
  try {
    const res = await http.apiModuleApi.deleteSuite(row.id)
    if (res.status === 200 || res.status === 204) {
      ElMessage.success('删除成功')
      fetchSuites()
    }
  } catch (error) {
    console.error('删除失败:', error)
    ElMessage.error('删除失败')
  }
}

const handleSelectionChange = (selection) => {
  selectedSuites.value = selection
}

const handleBatchDelete = async () => {
  if (selectedSuites.value.length === 0) {
    ElMessage.warning('请选择要删除的套件')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedSuites.value.length} 个套件吗？`,
      '警告',
      { type: 'warning' }
    )
    const ids = selectedSuites.value.map(r => r.id)
    await http.apiModuleApi.batchDeleteSuites(ids)
    ElMessage.success('批量删除成功')
    selectedSuites.value = []
    fetchSuites()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('批量删除失败')
    }
  }
}

const handleRun = (row) => {
  if (!proStore.envList || proStore.envList.length === 0) {
    ElMessage.warning('请先创建测试环境')
    return
  }
  currentSuite.value = row
  // 优先使用套件的默认环境
  runForm.env_id = row.env_id || null
  runDialogVisible.value = true
}

const confirmRun = async () => {
  if (!runForm.env_id) {
    ElMessage.warning('请选择执行环境')
    return
  }

  running.value = true
  try {
    // 调用异步接口，立即拿到 record_id
    const res = await http.apiModuleApi.runSuiteAsync(currentSuite.value.id, runForm)
    const data = res.data || res
    pollingRecordId.value = data.record_id
    pollingStatus.value = 'running'
    runDialogVisible.value = false
    ElMessage.info('套件已开始后台执行，请稍候…')
    startPolling()
  } catch (error) {
    console.error('执行失败:', error)
    ElMessage.error('执行失败')
  } finally {
    running.value = false
  }
}

const startPolling = () => {
  polling.value = true
  pollingTimer.value = setInterval(async () => {
    try {
      const res = await http.apiModuleApi.getSuiteRecordDetail(pollingRecordId.value)
      const data = res.data || res
      if (data.status !== 'running') {
        stopPolling()
        pollingStatus.value = 'done'
        runResult.value = {
          total: data.total_cases || 0,
          success: data.success_cases || 0,
          failed: data.failed_cases || 0,
          record_id: data.id,
          results: (data.case_results || []).map(cr => ({
            status: cr.status,
            response_status: cr.response_status,
            response_time: cr.response_time,
            http_response_time: cr.http_response_time,
            request_detail: cr.request_detail,
            error: cr.error_msg,
            case_name: cr.case_name
          }))
        }
        resultDialogVisible.value = true
        ElMessage.success(data.status === 'success' ? '套件执行完成' : '套件执行完成（部分失败）')
      }
    } catch (err) {
      console.error('轮询执行状态失败:', err)
    }
  }, 3000)
}

const stopPolling = () => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
  polling.value = false
}

const handleDetail = (row) => {
  router.push(`/api-suite/${row.id}`)
}

const goToRecord = () => {
  resultDialogVisible.value = false
  router.push(`/api-run-records`)
}

const stopPollingAndClose = () => {
  stopPolling()
  ElMessage.info('套件仍在后台执行，可在执行记录页面查看结果')
}

onMounted(async () => {
  // 等待项目信息加载完成
  if (!proStore.projectInfo.id) {
    await proStore.getProjectList()
  }
  fetchSuites()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.suite-list {
  padding: 20px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.env-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 5px;
}
</style>
