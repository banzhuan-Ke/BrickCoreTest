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
      <el-button type="primary" @click="router.push('/suite/add')">
        <el-icon><Plus /></el-icon>
        新增套件
      </el-button>
    </div>

    <!-- 数据表格 -->
    <el-card class="table-card">
      <el-table 
        :data="suiteList" 
        :header-cell-style="{'text-align':'center'}" 
        :cell-style="{'text-align':'center'}"
        stripe
        v-loading="loading"
      >
        <template #empty>
          <el-empty description="暂无数据" />
        </template>
        
        <el-table-column label="序号" type="index" width="80"/>
        <el-table-column prop="name" show-overflow-tooltip label="套件名称"/>
        <el-table-column prop="suite_type" label="套件类型" width="100">
          <template #default="scope">
            <el-tag v-if='scope.row.suite_type==="1"' type="success">功能</el-tag>
            <el-tag v-else-if='scope.row.suite_type==="2"' type="warning">场景</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="catalog_name" show-overflow-tooltip label="所属目录">
          <template #default="scope">{{ scope.row.catalog_name || scope.row.module || '—' }}</template>
        </el-table-column>
        <el-table-column prop="suite_step_count" label="前置步骤" width="100"/>
        <el-table-column prop="case_count" label="用例数" width="100"/>
        <el-table-column prop="run_count" label="执行次数" width="100"/>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="scope">
            <el-tag v-if='scope.row.status==="执行中"' type="primary">执行中</el-tag>
            <el-tag v-else-if='scope.row.status==="等待执行"' type="info">等待执行</el-tag>
            <el-tag v-else-if='scope.row.status==="执行完成"' type="success">执行完成</el-tag>
            <el-tag v-else type="info">未执行</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="创建人" width="100"/>
        <el-table-column prop="create_time" label="创建时间" width="160">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="scope">
            <el-button @click="clickRun(scope.row.id)" type="warning" plain icon="Promotion" size="small">运行</el-button>
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

    <!-- 运行套件的弹框 - 卡片式布局 -->
    <el-dialog v-model="showRunDlg" title="套件运行配置" width="520px" center destroy-on-close>
      <div class="run-config-container">
        <!-- 运行环境卡片 -->
        <div class="config-section">
          <div class="section-title">
            <el-icon><OfficeBuilding /></el-icon>
            <span>运行环境</span>
            <span class="required">*</span>
          </div>
          <div class="env-cards">
            <div 
              v-for="env in proStore.envList" 
              :key="env.id"
              :class="['env-card', { active: runParams.env_id === env.id }]"
              @click="runParams.env_id = env.id"
            >
              <div class="env-name">{{ env.name }}</div>
              <div class="env-host">{{ env.host }}</div>
              <el-icon v-if="runParams.env_id === env.id" class="check-icon"><Check /></el-icon>
            </div>
            <el-empty v-if="proStore.envList.length === 0" description="暂无环境" :image-size="60" />
          </div>
        </div>

        <!-- 浏览器选择 -->
        <div class="config-section">
          <div class="section-title">
            <el-icon><Monitor /></el-icon>
            <span>浏览器</span>
            <span class="required">*</span>
          </div>
          <div class="browser-options">
            <div 
              v-for="browser in browserOptions" 
              :key="browser.value"
              :class="['browser-item', { active: runParams.browser_type === browser.value }]"
              @click="runParams.browser_type = browser.value"
            >
              <el-icon class="browser-icon" :size="28">
                <ChromeFilled v-if="browser.icon === 'ChromeFilled'" />
                <Compass v-else-if="browser.icon === 'Compass'" />
                <Apple v-else />
              </el-icon>
              <span>{{ browser.label }}</span>
            </div>
          </div>
        </div>

        <!-- 运行方式 -->
        <div class="config-section">
          <div class="section-title">
            <el-icon><SetUp /></el-icon>
            <span>运行方式</span>
            <span class="required">*</span>
          </div>
          <div class="mode-options">
            <el-tooltip content="显示浏览器界面，可实时查看执行过程" placement="top">
              <div 
                :class="['mode-item', { active: !runParams.headless }]"
                @click="runParams.headless = false"
              >
                <el-icon><View /></el-icon>
                <span>界面模式</span>
                <small>可视化执行</small>
              </div>
            </el-tooltip>
            <el-tooltip content="后台静默执行，不显示浏览器界面" placement="top">
              <div 
                :class="['mode-item', { active: runParams.headless }]"
                @click="runParams.headless = true"
              >
                <el-icon><Hide /></el-icon>
                <span>无头模式</span>
                <small>后台执行</small>
              </div>
            </el-tooltip>
          </div>
        </div>

        <!-- AI 自愈 -->
        <div v-if="healRunOptions?.locator_heal_enabled" class="config-section">
          <div class="section-title">
            <el-icon><MagicStick /></el-icon>
            <span>AI 定位器自愈</span>
          </div>
          <div v-if="healRunOptions.locator_heal_allow_run_override" class="mode-options">
            <div
              :class="['mode-item', { active: runParams.ai_heal_enabled === true }]"
              @click="runParams.ai_heal_enabled = true"
            >
              <el-icon><CircleCheck /></el-icon>
              <span>开启</span>
              <small>失败时自动推荐定位器</small>
            </div>
            <div
              :class="['mode-item', { active: runParams.ai_heal_enabled === false }]"
              @click="runParams.ai_heal_enabled = false"
            >
              <el-icon><CircleClose /></el-icon>
              <span>关闭</span>
            </div>
          </div>
          <el-alert
            v-else
            type="info"
            :closable="false"
            show-icon
            :title="`本次将按项目默认：${healRunOptions.locator_heal_default_on_execute ? '开启' : '关闭'}自愈`"
          />
        </div>

        <!-- 运行设备 -->
        <div class="config-section">
          <div class="section-title">
            <el-icon><Cpu /></el-icon>
            <span>执行设备</span>
            <span class="required">*</span>
          </div>
          <el-select 
            v-model="runParams.device_id" 
            placeholder="请选择执行设备" 
            style="width: 100%"
            size="large"
          >
            <el-option
              v-for="device in deviceList"
              :key="device.id"
              :label="device.name"
              :value="device.id"
            >
              <div class="device-option">
                <span class="device-name">{{ device.name }}</span>
                <span class="device-ip">{{ device.ip }}</span>
                <el-tag 
                  v-if="device.status === '在线' || device.status === 'online'" 
                  type="success" 
                  size="small"
                >在线</el-tag>
                <el-tag 
                  v-else 
                  type="info" 
                  size="small"
                >离线</el-tag>
              </div>
            </el-option>
          </el-select>
          <div v-if="deviceList.length === 0" class="device-empty">
            <el-icon><Warning /></el-icon>
            <span>暂无在线设备，请先注册设备</span>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showRunDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmRun" :loading="running" size="large">
          <el-icon><VideoPlay /></el-icon>
          开始执行
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, OfficeBuilding, Monitor, SetUp, View, Hide, Cpu, Warning, Check, VideoPlay, ChromeFilled, Compass, Apple, Close, Search, RefreshRight, MagicStick, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'
import http from '@/api/index'
import { aiConfigApi } from '@/api/modules/ai.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import dateTools from '@/tools/dateTools'
import SuiteRunRecord from './componets/SuiteRecord.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'

const router = useRouter()
const proStore = ProjectStore()
const userStore = UserStore()

// 列表数据
const suiteList = ref([])
const loading = ref(false)

// 分页配置
const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})

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
      ElMessage.success('套件已提交执行')
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
  getSuiteList()
})
</script>

<style scoped lang="scss">
.suite-list-container {
  padding: 20px;
}

.search-bar {
  margin-bottom: 20px;
}

.table-card {
  .pagination-wrapper {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
  }
}

// 运行配置弹窗样式
.run-config-container {
  padding: 10px 0;
}

.config-section {
  margin-bottom: 24px;

  &:last-child {
    margin-bottom: 0;
  }
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;

  .el-icon {
    font-size: 16px;
    color: #409eff;
  }

  .required {
    color: #f56c6c;
    margin-left: 2px;
  }
}

// 环境卡片
.env-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  max-height: 160px;
  overflow-y: auto;
}

.env-card {
  position: relative;
  width: calc(50% - 5px);
  padding: 12px;
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: #fff;

  &:hover {
    border-color: #c0c4cc;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }

  &.active {
    border-color: #409eff;
    background: #f5f9ff;

    .check-icon {
      position: absolute;
      top: 6px;
      right: 6px;
      color: #409eff;
      font-size: 16px;
    }
  }

  .env-name {
    font-size: 14px;
    font-weight: 500;
    color: #303133;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .env-host {
    font-size: 12px;
    color: #909399;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

// 浏览器选项
.browser-options {
  display: flex;
  gap: 12px;
}

.browser-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: #fff;

  &:hover {
    border-color: #c0c4cc;
  }

  &.active {
    border-color: #409eff;
    background: #f5f9ff;
  }

  .browser-icon {
    margin-bottom: 6px;
    color: #606266;
  }

  &.active .browser-icon {
    color: #409eff;
  }

  span {
    font-size: 13px;
    color: #606266;
  }
}

// 运行方式选项
.mode-options {
  display: flex;
  gap: 12px;
}

.mode-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 12px;
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: #fff;

  &:hover {
    border-color: #c0c4cc;
  }

  &.active {
    border-color: #409eff;
    background: #f5f9ff;

    .el-icon {
      color: #409eff;
    }

    span {
      color: #409eff;
    }
  }

  .el-icon {
    font-size: 24px;
    color: #909399;
    margin-bottom: 6px;
  }

  span {
    font-size: 14px;
    font-weight: 500;
    color: #303133;
  }

  small {
    font-size: 12px;
    color: #909399;
    margin-top: 2px;
  }
}

// 设备选项
.device-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;

  .device-name {
    flex: 1;
    font-size: 14px;
  }

  .device-ip {
    font-size: 12px;
    color: #909399;
  }
}

// 已选择设备卡片
.device-selected-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border: 2px solid #409eff;
  border-radius: 8px;
  background: #f5f9ff;

  .device-info {
    flex: 1;

    .device-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;

      .device-name {
        font-size: 15px;
        font-weight: 500;
        color: #303133;
      }
    }

    .device-ip {
      font-size: 13px;
      color: #606266;
    }
  }

  .el-button {
    color: #f56c6c;
  }
}

.device-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 10px;
  background: #fef0f0;
  border-radius: 4px;
  color: #f56c6c;
  font-size: 13px;

  .el-icon {
    font-size: 16px;
  }
}
</style>
