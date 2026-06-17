<template>
  <div class="suite-list-container">
    <CatalogListLayout
      :project-id="proStore.projectInfo.id"
      v-model="searchForm.catalog_id"
      all-node-label="全部套件"
      @change="handleSearch"
    >
    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchForm.name"
        placeholder="搜索套件名称"
        clearable
        style="width: 180px;"
        @keyup.enter="handleSearch"
      />
      <el-select v-model="searchForm.suite_type" placeholder="套件类型" clearable style="width: 120px;">
        <el-option label="功能" value="1"/>
        <el-option label="场景" value="2"/>
      </el-select>
      <el-select v-model="searchForm.status" placeholder="状态" clearable style="width: 130px;">
        <el-option label="等待执行" value="等待执行"/>
        <el-option label="执行中" value="执行中"/>
        <el-option label="执行完成" value="执行完成"/>
      </el-select>
      <el-button type="primary" @click="handleSearch" icon="Search">搜索</el-button>
      <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
      <TableColumnPicker
        :items="pickerItems"
        @toggle="setColumnVisible"
        @reorder="setPickerOrder"
        @reset="resetColumns"
      />
      <el-button type="primary" @click="router.push('/suite/add')">
        <el-icon><Plus /></el-icon>
        新增套件
      </el-button>
    </div>

    <!-- 数据表格 -->
    <el-card class="table-card">
      <el-table
        :key="tableRenderKey"
        :data="suiteList"
        :header-cell-style="{'text-align':'center'}"
        :cell-style="{'text-align':'center'}"
        stripe
        v-loading="loading"
      >
        <template #empty>
          <el-empty description="暂无数据" />
        </template>
        <template v-for="col in activeColumns" :key="col.key">
          <el-table-column
            v-if="col.key === 'index'"
            label="序号"
            type="index"
            :index="tableRowIndex"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'name'"
            prop="name"
            show-overflow-tooltip
            label="套件名称"
            :min-width="col.minWidth || 160"
          />
          <el-table-column
            v-else-if="col.key === 'suite_type'"
            prop="suite_type"
            label="套件类型"
            :width="col.width"
          >
            <template #default="scope">
              <el-tag v-if='scope.row.suite_type==="1"' type="success">功能</el-tag>
              <el-tag v-else-if='scope.row.suite_type==="2"' type="warning">场景</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'catalog_name'"
            prop="catalog_name"
            show-overflow-tooltip
            label="所属目录"
            :width="col.width"
          >
            <template #default="scope">{{ scope.row.catalog_name || scope.row.module || '—' }}</template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'suite_step_count'"
            prop="suite_step_count"
            label="前置步骤"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'case_count'"
            prop="case_count"
            label="用例数"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'run_count'"
            prop="run_count"
            label="执行次数"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'status'"
            prop="status"
            label="状态"
            :width="col.width"
          >
            <template #default="scope">
              <el-tag v-if='scope.row.status==="执行中"' type="primary">执行中</el-tag>
              <el-tag v-else-if='scope.row.status==="等待执行"' type="info">等待执行</el-tag>
              <el-tag v-else-if='scope.row.status==="执行完成"' type="success">执行完成</el-tag>
              <el-tag v-else type="info">未执行</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'username'"
            prop="username"
            label="创建人"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'create_time'"
            prop="create_time"
            label="创建时间"
            :width="col.width"
          >
            <template #default="scope">
              {{ dateTools.rTime(scope.row.create_time) }}
            </template>
          </el-table-column>
        </template>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="scope">
            <el-button v-if="canExecute" @click="clickRun(scope.row.id)" type="warning" plain icon="Promotion" size="small">运行</el-button>
            <el-button @click="showRunRecord(scope.row)" type="success" plain icon="View" size="small">报告</el-button>
            <el-dropdown>
              <el-button type="primary" plain icon="MoreFilled" size="small" style="margin-left:6px">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="router.push({name: 'editSuite', params: {id: scope.row.id}})" icon="Edit">
                    编辑
                  </el-dropdown-item>
                  <el-dropdown-item @click="clickDelete(scope.row.id)" icon="Delete">删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @current-change="getSuiteList"
          @size-change="getSuiteList"
        />
      </div>
    </el-card>
    </CatalogListLayout>

    <!-- 运行记录详情弹框 -->
    <el-dialog v-model="showRecordDlg" width="90%" center destroy-on-close>
      <template #header>
        <div style="font-size: 18px">套件执行记录</div>
      </template>
      <SuiteRunRecord :suite_id="showSuite.id"></SuiteRunRecord>
    </el-dialog>

    <el-dialog v-model="showRunDlg" title="套件运行配置" width="560px" destroy-on-close>
      <el-form label-width="88px" class="ui-run-config-form">
        <el-form-item label="运行环境" required>
          <UiRunEnvSelect v-model="runParams.env_id" />
        </el-form-item>
        <el-form-item label="浏览器" required>
          <div class="ui-run-segment-group">
            <div
              v-for="browser in browserOptions"
              :key="browser.value"
              :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.browser_type === browser.value }]"
              @click="runParams.browser_type = browser.value"
            >
              <el-icon>
                <ChromeFilled v-if="browser.icon === 'ChromeFilled'" />
                <Compass v-else-if="browser.icon === 'Compass'" />
                <Apple v-else />
              </el-icon>
              <span>{{ browser.label }}</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="运行模式" required>
          <div class="ui-run-segment-group">
            <div
              :class="['ui-run-segment', 'ui-run-segment--grow', { active: !runParams.headless }]"
              @click="runParams.headless = false"
            >
              <el-icon><View /></el-icon><span>界面模式</span>
            </div>
            <div
              :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.headless }]"
              @click="runParams.headless = true"
            >
              <el-icon><Hide /></el-icon><span>无头模式</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item v-if="healRunOptions?.locator_heal_enabled" label="AI 自愈">
          <div v-if="healRunOptions.locator_heal_allow_run_override" class="ui-run-segment-group">
            <div
              :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.ai_heal_enabled === true }]"
              @click="runParams.ai_heal_enabled = true"
            >
              <el-icon><CircleCheck /></el-icon><span>开启</span>
            </div>
            <div
              :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.ai_heal_enabled === false }]"
              @click="runParams.ai_heal_enabled = false"
            >
              <el-icon><CircleClose /></el-icon><span>关闭</span>
            </div>
          </div>
          <el-alert
            v-else
            type="info"
            :closable="false"
            show-icon
            :title="`本次将按项目默认：${healRunOptions.locator_heal_default_on_execute ? '开启' : '关闭'}自愈`"
          />
        </el-form-item>
        <el-form-item label="执行设备" required>
          <el-select v-model="runParams.device_id" placeholder="请选择执行设备" style="width: 100%">
            <el-option
              v-for="device in deviceList"
              :key="device.id"
              :label="device.name"
              :value="device.id"
            >
              <div class="ui-run-device-option">
                <span class="ui-run-device-option__name">{{ device.name }}</span>
                <span class="ui-run-device-option__ip">{{ device.ip }}</span>
                <el-tag v-if="device.status === '在线' || device.status === 'online'" type="success" size="small">在线</el-tag>
                <el-tag v-else type="info" size="small">离线</el-tag>
              </div>
            </el-option>
          </el-select>
          <div v-if="deviceList.length === 0" class="ui-run-device-empty">
            <el-icon><Warning /></el-icon>
            <span>暂无在线设备，请先注册设备</span>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="ui-run-dialog-footer">
          <el-button @click="showRunDlg = false">取消</el-button>
          <el-button type="primary" @click="confirmRun" :loading="running">
            <el-icon><VideoPlay /></el-icon>
            开始执行
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Plus, View, Hide, Warning, VideoPlay, ChromeFilled, Compass, Apple, Close, Search, RefreshRight, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import http from '@/api/index'
import { aiConfigApi } from '@/api/modules/ai.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import dateTools from '@/tools/dateTools'
import SuiteRunRecord from './componets/SuiteRecord.vue'
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import { useTableColumns } from '@/composables/useTableColumns.js'
import { makeTableRowIndex } from '@/utils/tableIndex'
import UiRunEnvSelect from '@/components/UiRunEnvSelect.vue'

const {
  activeColumns,
  pickerItems,
  tableRenderKey,
  setColumnVisible,
  setPickerOrder,
  resetColumns
} = useTableColumns('ui.suites')

const router = useRouter()
const route = useRoute()
const proStore = ProjectStore()
const userStore = UserStore()
const canExecute = computed(() => userStore.hasPermission('ui_suite:execute'))

// 列表数据
const suiteList = ref([])
const loading = ref(false)

// 分页配置
const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pageConfig)

const searchForm = reactive({
  name: '',
  catalog_id: '',
  suite_type: '',
  status: ''
})

// 获取套件列表
const getSuiteList = async () => {
  loading.value = true
  try {
    const params = {
      page: pageConfig.page,
      size: pageConfig.size,
      project: proStore.projectInfo.id,
    }
    if (searchForm.name) params.name = searchForm.name
    if (searchForm.catalog_id) params.catalog_id = searchForm.catalog_id
    if (searchForm.suite_type) params.suite_type = searchForm.suite_type
    if (searchForm.status) params.status = searchForm.status
    const res = await http.suiteApi.getList(params)
    if (res.status === 200) {
      suiteList.value = res.data.data
      pageConfig.total = res.data.total
    }
  } catch (error) {
    ElMessage.error('获取套件列表失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pageConfig.page = 1
  getSuiteList()
}

const resetSearch = () => {
  searchForm.name = ''
  searchForm.catalog_id = ''
  searchForm.suite_type = ''
  searchForm.status = ''
  pageConfig.page = 1
  getSuiteList()
}

// 删除套件
const clickDelete = async (id) => {
  try {
    await ElMessageBox.confirm('确定删除该套件吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const res = await http.suiteApi.delete(id)
    // 兼容 200 和 204 No Content
    if (res.status === 200 || res.status === 204) {
      ElMessage.success('删除成功')
      getSuiteList()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 浏览器选项
const browserOptions = [
  { value: 'chromium', label: 'Chrome', icon: 'ChromeFilled' },
  { value: 'firefox', label: 'Firefox', icon: 'Compass' },
  { value: 'webkit', label: 'Safari', icon: 'Apple' }
]

// 设备列表
const deviceList = ref([])

// 计算选中的设备
const selectedDevice = computed(() => {
  return deviceList.value.find(d => d.id === runParams.device_id)
})

// 获取设备列表
const getDeviceList = async () => {
  try {
    const res = await http.deviceApi.getDeviceList({ status: '在线' })
    if (res.status === 200) {
      deviceList.value = res.data || []
      // 如果只有一个在线设备，默认选中
      if (deviceList.value.length === 1) {
        runParams.device_id = deviceList.value[0].id
      }
    }
  } catch (error) {
    console.error('获取设备列表失败:', error)
  }
}

// 运行相关
const showRunDlg = ref(false)
const running = ref(false)
const runFormRef = ref()
const showSuite = ref({})
const runParams = reactive({
  env_id: '',
  browser_type: 'chromium',
  headless: false,
  device_id: '',
  ai_heal_enabled: true
})
const healRunOptions = ref(null)

const loadHealRunOptions = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    healRunOptions.value = null
    return
  }
  try {
    const res = await aiConfigApi.getExecutionSettings(pid)
    if (res.data?.code === 200) {
      healRunOptions.value = res.data.data || null
      runParams.ai_heal_enabled = healRunOptions.value?.locator_heal_default_on_execute ?? true
    }
  } catch {
    healRunOptions.value = null
  }
}

const clickRun = async (id) => {
  showSuite.value = { id }
  runParams.env_id = ''
  runParams.browser_type = 'chromium'
  runParams.headless = false
  runParams.device_id = ''
  runParams.ai_heal_enabled = true
  await loadHealRunOptions()
  // 获取设备列表
  await getDeviceList()
  showRunDlg.value = true
}

const confirmRun = async () => {
  // 表单验证
  if (!runParams.env_id) {
    ElMessage.warning('请选择运行环境')
    return
  }
  if (!runParams.browser_type) {
    ElMessage.warning('请选择浏览器')
    return
  }
  if (!runParams.device_id) {
    ElMessage.warning('请选择执行设备')
    return
  }
  
  running.value = true
  try {
    const payload = {
      env_id: runParams.env_id,
      browser_type: runParams.browser_type,
      device_id: runParams.device_id,
      config: runParams.headless,
      username: userStore.userInfo.username
    }
    if (healRunOptions.value?.locator_heal_allow_run_override) {
      payload.ai_heal_enabled = runParams.ai_heal_enabled
    }
    const res = await http.suiteApi.runSuite(showSuite.value.id, payload)
    if (res.status === 200 || res.status === 201) {
      const dispatched = res.data?.dispatched !== false
      if (dispatched) {
        ElMessage.success(res.data?.msg || '套件已提交执行')
      } else {
        ElMessage.warning(res.data?.msg || '记录已创建，但暂无在线执行器')
      }
      showRunDlg.value = false
      getSuiteList()
    } else {
      ElMessage.error(res.data?.detail || '运行失败')
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '运行失败')
  } finally {
    running.value = false
  }
}

// 查看运行记录
const showRecordDlg = ref(false)
const showRunRecord = (row) => {
  showSuite.value = row
  showRecordDlg.value = true
}

onMounted(() => {
  proStore.getCatalogList()
  const qName = route.query.name
  if (qName && typeof qName === 'string') {
    searchForm.name = qName
  }
  getSuiteList()
})

watch(
  () => route.query.name,
  (qName) => {
    if (qName && typeof qName === 'string') {
      searchForm.name = qName
      pageConfig.page = 1
      getSuiteList()
    }
  },
)
</script>

<style scoped lang="scss">
@use '@/style/ui-run-config.scss';

.suite-list-container {
  padding: 20px;
}

.search-bar {
  margin-bottom: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.table-card {
  .pagination-wrapper {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
  }
}

.ui-run-device-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 10px;
  background: var(--el-color-danger-light-9);
  border-radius: 4px;
  color: var(--el-color-danger);
  font-size: 13px;

  .el-icon {
    font-size: 16px;
  }
}
</style>
