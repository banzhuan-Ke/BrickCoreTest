<template>
  <PageCard>
    <template #title>
      <el-button @click="router.push({name: 'addCase'})" size="small" type="primary" icon="Plus">用例</el-button>
    </template>
    <template #main>
      <CatalogListLayout
        :project-id="proStore.projectInfo.id"
        v-model="searchForm.catalog_id"
        all-node-label="全部用例"
        @change="handleSearch"
      >
      <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
        <el-input
          v-model="searchForm.name"
          placeholder="搜索用例名称"
          clearable
          style="width: 180px;"
          @keyup.enter="handleSearch"
        />
        <el-select v-model="searchForm.status" placeholder="运行状态" clearable style="width: 130px;">
          <el-option label="未运行" value="no_run"/>
          <el-option label="运行中" value="running"/>
          <el-option label="运行成功" value="success"/>
          <el-option label="运行失败" value="fail"/>
          <el-option label="跳过运行" value="skip"/>
          <el-option label="运行错误" value="error"/>
        </el-select>
        <el-select v-model="searchForm.level" placeholder="优先级" clearable style="width: 110px;">
          <el-option label="P0" value="P0"/>
          <el-option label="P1" value="P1"/>
          <el-option label="P2" value="P2"/>
          <el-option label="P3" value="P3"/>
        </el-select>
        <el-button type="primary" @click="handleSearch" icon="Search">搜索</el-button>
        <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
        <el-button
          v-if="selectedCases.length > 0"
          type="warning"
          plain
          icon="FolderOpened"
          @click="batchCatalogDialog.visible = true"
        >修改目录({{ selectedCases.length }})</el-button>
        <el-button
          v-if="selectedCases.length > 0"
          type="primary"
          plain
          icon="Download"
          @click="handleBatchExport"
        >导出选中({{ selectedCases.length }})</el-button>
        <el-upload
          accept=".json"
          :show-file-list="false"
          :before-upload="handleImport"
          style="display:inline-block; margin-left:4px"
        >
          <el-button type="success" plain icon="Upload">导入用例</el-button>
        </el-upload>
      </div>
      <el-table :data="caseList" :header-cell-style="{'text-align':'center'}" :cell-style="{'text-align':'center'}"
                stripe @selection-change="handleSelectionChange">
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><DocumentChecked /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="name" label="用例名称" show-overflow-tooltip width="150"/>
        <el-table-column prop="run_count" label="运行次数"/>
        <el-table-column prop="status" label="最近运行结果" width="120px">
          <template #default="scope">
            <el-tag v-if='scope.row.status==="no_run"' type="info">未运行</el-tag>
            <el-tag v-else-if='scope.row.status==="running"' type="primary">运行中</el-tag>
            <el-tag v-else-if='scope.row.status==="success"' type="success">运行成功</el-tag>
            <el-tag v-else-if='scope.row.status==="fail" || scope.row.status==="failed"' type="danger">运行失败</el-tag>
            <el-tag v-else-if='scope.row.status==="skip"' type="warning">跳过运行</el-tag>
            <el-tag v-else-if='scope.row.status==="error"' type="danger">运行错误</el-tag>
            <el-tag v-else type="info">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="steps_count" label="步骤数"/>
        <el-table-column prop="username" label="创建人"/>
        <el-table-column prop="level" label="用例级别" width="100">
          <template #default="scope">
            <el-tag v-if='scope.row.level==="P0"' type="danger">P0</el-tag>
            <el-tag v-else-if='scope.row.level==="P1"' type="warning">P1</el-tag>
            <el-tag v-else-if='scope.row.level==="P2"' type="primary">P2</el-tag>
            <el-tag v-else-if='scope.row.level==="P3"' type="info">P3</el-tag>
            <span v-else>{{ scope.row.level }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源功能用例" min-width="160" show-overflow-tooltip>
          <template #default="scope">
            <el-link
              v-if="scope.row.source_functional_case_id"
              type="primary"
              @click="goFunctionalCase(scope.row.source_functional_case_id)"
            >
              {{ scope.row.source_functional_case_title || `#${scope.row.source_functional_case_id}` }}
            </el-link>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="创建时间" width="180px">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="180">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300px">
          <template #default="scope">
            <el-button @click="clickRun(scope.row.id)" plain icon="Promotion" type="warning">运行</el-button>
            <el-button @click="clickRecord(scope.row.id)" plain type="success" icon="View">报告</el-button>
            <el-dropdown>
              <el-button type="primary" plain icon="MoreFilled" style="margin-left:10px">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="router.push({name: 'editCase',params:{id: scope.row.id}})" icon="Edit">
                    编辑
                  </el-dropdown-item>
                  <el-dropdown-item @click="CopyCase(scope.row.id)" icon="DocumentCopy">
                    复制
                  </el-dropdown-item>
                  <el-dropdown-item @click="clickDelete(scope.row.id)" icon="Delete">
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      </CatalogListLayout>
    </template>
    <template #bottom>
      <!--  分页器-->
      <el-pagination
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @current-change="getCasesList"
          @size-change="getCasesList"
      />
    </template>
  </PageCard>
  <!--运行测试用例-->
  <!-- 运行任务的弹框-->
  <el-dialog v-model="showRunDlg" title="用例运行配置" width="520px" center destroy-on-close>
    <div class="run-config-container">
      <!-- 运行环境 -->
      <div class="config-section">
        <div class="section-title"><el-icon><OfficeBuilding /></el-icon><span>运行环境</span></div>
        <div class="env-cards">
          <div v-for="env in proStore.envList" :key="env.id"
               :class="['env-card', { active: runParams.env_id === env.id }]"
               @click="runParams.env_id = env.id">
            <div class="env-name">{{ env.name }}</div>
            <div class="env-host">{{ env.host }}</div>
          </div>
        </div>
      </div>
      <!-- 浏览器选择 -->
      <div class="config-section">
        <div class="section-title"><el-icon><Monitor /></el-icon><span>选择浏览器</span></div>
        <div class="browser-options">
          <div :class="['browser-item', { active: runParams.browser_type === 'chromium' }]"
               @click="runParams.browser_type = 'chromium'">
            <el-icon class="browser-icon" :size="28"><ChromeFilled /></el-icon>
            <span>Chrome</span>
          </div>
          <div :class="['browser-item', { active: runParams.browser_type === 'firefox' }]"
               @click="runParams.browser_type = 'firefox'">
            <el-icon class="browser-icon" :size="28"><Compass /></el-icon>
            <span>Firefox</span>
          </div>
          <div :class="['browser-item', { active: runParams.browser_type === 'webkit' }]"
               @click="runParams.browser_type = 'webkit'">
            <el-icon class="browser-icon" :size="28"><Apple /></el-icon>
            <span>Safari</span>
          </div>
        </div>
      </div>
      <!-- 运行模式 -->
      <div class="config-section">
        <div class="section-title"><el-icon><SetUp /></el-icon><span>运行模式</span></div>
        <div class="mode-options">
          <div :class="['mode-item', { active: runParams.config === 'False' }]"
               @click="runParams.config = 'False'">
            <el-icon :size="24"><View /></el-icon>
            <span>界面模式</span>
            <small>显示浏览器界面</small>
          </div>
          <div :class="['mode-item', { active: runParams.config === 'True' }]"
               @click="runParams.config = 'True'">
            <el-icon :size="24"><Hide /></el-icon>
            <span>无头模式</span>
            <small>后台运行更高效</small>
          </div>
        </div>
      </div>
      <!-- AI 自愈（受 Backend 项目配置控制） -->
      <div v-if="healRunOptions?.locator_heal_enabled" class="config-section">
        <div class="section-title"><el-icon><MagicStick /></el-icon><span>AI 定位器自愈</span></div>
        <div v-if="healRunOptions.locator_heal_allow_run_override" class="mode-options">
          <div :class="['mode-item', { active: runParams.ai_heal_enabled === true }]"
               @click="runParams.ai_heal_enabled = true">
            <el-icon :size="24"><CircleCheck /></el-icon>
            <span>开启</span>
            <small>步骤失败时自动推荐新定位器</small>
          </div>
          <div :class="['mode-item', { active: runParams.ai_heal_enabled === false }]"
               @click="runParams.ai_heal_enabled = false">
            <el-icon :size="24"><CircleClose /></el-icon>
            <span>关闭</span>
            <small>不调用 LLM，仅按原步骤执行</small>
          </div>
        </div>
        <el-alert
          v-else
          type="info"
          :closable="false"
          show-icon
          :title="`本次将按项目默认：${healRunOptions.locator_heal_default_on_execute ? '开启' : '关闭'}自愈（运行弹窗不可改）`"
        />
      </div>
      <!-- 运行设备 -->
      <div class="config-section">
        <div class="section-title"><el-icon><Cpu /></el-icon><span>执行设备</span></div>
        <el-select 
          v-model="runParams.device_id" 
          placeholder="请选择执行设备" 
          style="width: 100%"
          size="large"
        >
          <el-option
            v-for="device in deviceList"
            :key="device.id"
            :label="device.name || device.username"
            :value="device.id"
          >
            <div class="device-option">
              <span class="device-name">{{ device.name || device.username }}</span>
              <span class="device-ip">{{ device.ip }}</span>
              <el-tag v-if="device.status === 'online' || device.status === '在线'" type="success" size="small">在线</el-tag>
              <el-tag v-else type="info" size="small">离线</el-tag>
            </div>
          </el-option>
        </el-select>
      </div>
    </div>
    <div class="dialog-footer">
      <el-button type="primary" size="large" @click="runCase()" icon="Promotion" :loading="running">开始运行</el-button>
    </div>
  </el-dialog>

  <!--  显示执行设备信息-->
  <el-dialog v-model="showDeviceDlg" title="用例执行设备实时画面" width="95%" center destroy-on-close>
    <DeviceInfo :deviceId="runParams.device_id"></DeviceInfo>
  </el-dialog>

  <!--显示用例执行记录-->
  <el-dialog v-model="showRecordDlg" width="80%" center destroy-on-close>
    <template #header>
      <div style="font-size: 18px">用例运行记录</div>
    </template>
    <caseRecord :case_id="showCaseId"></caseRecord>
  </el-dialog>

  <!-- 导入结果弹窗 -->
  <el-dialog v-model="importResultDlg.visible" title="导入结果" width="500px" destroy-on-close>
    <div v-if="importResultDlg.result">
      <el-descriptions :column="2" border size="small" style="margin-bottom: 16px;">
        <el-descriptions-item label="成功">
          <el-tag type="success">{{ importResultDlg.result.success }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          <el-tag type="danger">{{ importResultDlg.result.failed }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div v-if="importResultDlg.result.created_names?.length">
        <div style="font-size:13px; font-weight:500; margin-bottom:6px;">已创建用例：</div>
        <el-tag
          v-for="name in importResultDlg.result.created_names"
          :key="name"
          size="small"
          style="margin: 2px 4px 2px 0;"
        >{{ name }}</el-tag>
      </div>
      <div v-if="importResultDlg.result.warnings?.length" style="margin-top:12px;">
        <div style="font-size:13px; font-weight:500; color:#e6a23c; margin-bottom:6px;">警告：</div>
        <div v-for="(w, i) in importResultDlg.result.warnings" :key="i" style="font-size:12px; color:#e6a23c; margin-bottom:4px;">· {{ w }}</div>
      </div>
      <div v-if="importResultDlg.result.errors?.length" style="margin-top:12px;">
        <div style="font-size:13px; font-weight:500; color:#f56c6c; margin-bottom:6px;">错误：</div>
        <div v-for="(e, i) in importResultDlg.result.errors" :key="i" style="font-size:12px; color:#f56c6c; margin-bottom:4px;">· {{ e }}</div>
      </div>
    </div>
    <template #footer>
      <el-button type="primary" @click="importResultDlg.visible = false">确定</el-button>
    </template>
  </el-dialog>

  <BatchCatalogDialog
    v-model="batchCatalogDialog.visible"
    :case-ids="selectedCases.map((item) => item.id)"
    :project-id="proStore.projectInfo.id"
    :submit-fn="uiCaseApi.batchUpdateCatalog"
    @success="handleBatchCatalogSuccess"
  />
</template>

<script setup>
import {ref, reactive} from 'vue'
import {DocumentChecked, OfficeBuilding, Monitor, SetUp, View, Hide, Cpu, ChromeFilled, Compass, Apple, Promotion, Search, RefreshRight, MagicStick, CircleCheck, CircleClose} from "@element-plus/icons-vue"
import http from '@/api/index'
import { uiCaseApi } from '@/api/modules/ui'
import { aiConfigApi } from '@/api/modules/ai.js'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {useRouter} from 'vue-router'
import DeviceInfo from "@/views/Device/DeviceInfo.vue"
import PageCard from "@/components/PageCard.vue"
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import CaseRecord from "@/views/Case/componets/CaseRecord.vue"
import BatchCatalogDialog from '@/components/BatchCatalogDialog.vue'
import {UserStore} from "@/stores/module/UserStore.js"

const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()

const goFunctionalCase = (id) => {
  router.push({ name: 'aiFunctionalCases', query: { highlight: id } })
}

// 获取用例列表数据
const caseList = ref([])
const selectedCases = ref([])
const importResultDlg = reactive({ visible: false, result: null })
const batchCatalogDialog = reactive({ visible: false })

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0,
  project_id: proStore.projectInfo.id
})

const searchForm = reactive({
  name: '',
  catalog_id: null,
  status: '',
  level: ''
})

// 获取用例数据
const getCasesList = async () => {
  const params = { ...pageConfig }
  if (searchForm.name) params.name = searchForm.name
  if (searchForm.status) params.status = searchForm.status
  if (searchForm.level) params.level = searchForm.level
  if (searchForm.catalog_id) params.catalog_id = searchForm.catalog_id
  const res = await http.caseApi.getList(params)
  caseList.value = res.data.data
  pageConfig.total = res.data.total
}
getCasesList()

const handleSearch = () => {
  pageConfig.page = 1
  getCasesList()
}

const resetSearch = () => {
  searchForm.catalog_id = null
  searchForm.name = ''
  searchForm.status = ''
  searchForm.level = ''
  pageConfig.page = 1
  getCasesList()
}

// 是否显示运行用例对话框
const showRunDlg = ref(false)
const showDeviceDlg = ref(false)
const running = ref(false)

// 设备列表
const deviceList = ref([])
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

// 获取设备列表
const getDeviceList = async () => {
  try {
    const res = await http.deviceApi.getList({ status: '在线' })
    if (res.status === 200) {
      deviceList.value = res.data || []
    }
  } catch (error) {
    console.error('获取设备列表失败:', error)
  }
}

// 运行的参数
const runParams = reactive({
  env_id: '',
  browser_type: 'chromium',
  device_id: '',
  case_id: 1,
  username: uStore.userInfo.username,
  config: 'False',
  ai_heal_enabled: true
})

const clickRun = async (case_id) => {
  // 重置运行参数
  runParams.env_id = ''
  runParams.browser_type = 'chromium'
  runParams.device_id = ''
  runParams.case_id = case_id
  runParams.username = uStore.userInfo.username
  runParams.config = 'False'
  runParams.ai_heal_enabled = true
  await loadHealRunOptions()
  // 获取设备列表
  await getDeviceList()
  showRunDlg.value = true
}

// 运行用例
async function runCase() {
  // 校验必填项
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
    const payload = { ...runParams }
    if (!healRunOptions.value?.locator_heal_allow_run_override) {
      delete payload.ai_heal_enabled
    }
    const response = await http.runnerApi.runCase(payload.case_id, payload)
    showRunDlg.value = false
    if (response.status === 201) {
      ElNotification({
        title: '用例已提交运行！',
        type: 'success',
        duration: 1500,
      })
      // 显示执行设备状态
      if (runParams.case_id) {
        showDeviceDlg.value = true
      }
      // 刷新页面数据
      await getCasesList()
    }
  } finally {
    running.value = false
  }
}

// 删除用例
const clickDelete = async (case_id) => {
  ElMessageBox.confirm(
      '此操作不可恢复，确定删除该用例吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const res = await http.caseApi.delete(case_id)
        if (res.status === 204) {
          await getCasesList()
          ElNotification({
            type: 'success',
            title: '已成功删除用例！',
            duration: 1500,
          })
        } else {
          ElNotification({
            type: 'error',
            title: '删除用例失败！',
            message: res.data.detail,
            duration: 1500,
          })
        }
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消删除操作。',
          duration: 1500,
        })
      })
}

// 复制用例
const CopyCase = async (case_id) => {
  ElMessageBox.confirm(
      '确定复制该用例吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const res = await http.caseApi.copy(case_id)
        if (res.status === 201) {
          await getCasesList()
          ElNotification({
            type: 'success',
            title: '已成功复制用例！',
            duration: 1500,
          })
        } else {
          ElNotification({
            type: 'error',
            message: res.data.detail,
            title: '复制用例失败！',
            duration: 1500,
          })
        }
      })
      .catch(() => {
        ElMessage({
          type: 'info',
          message: '已取消复制操作。',
          duration: 1500,
        })
      })
}
// 用例运行记录
const showRecordDlg = ref(false)
const showCaseId = ref(0)
const clickRecord = async (case_id) => {
  showRecordDlg.value = true
  showCaseId.value = case_id
}

const handleSelectionChange = (selection) => {
  selectedCases.value = selection
}

const handleBatchCatalogSuccess = () => {
  selectedCases.value = []
  getCasesList()
}

const handleBatchExport = async () => {
  const ids = selectedCases.value.map(r => r.id)
  try {
    const res = await uiCaseApi.exportCases({ case_ids: ids })
    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `ui_cases_${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${ids.length} 条用例`)
  } catch (err) {
    ElMessage.error('导出失败: ' + (err.response?.data?.detail || err.message))
  }
}

const handleImport = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('project_id', proStore.projectInfo.id)
  try {
    const res = await uiCaseApi.importCases(formData)
    if (res.status === 200) {
      importResultDlg.result = res.data
      importResultDlg.visible = true
      if (res.data.success > 0) {
        getCasesList()
      }
    }
  } catch (err) {
    ElMessage.error('导入失败: ' + (err.response?.data?.detail || err.message))
  }
  return false
}
</script>

<style scoped lang="scss">
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

  &.active span {
    color: #409eff;
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

// 设备选择触发器
.device-select-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  color: #606266;

  &:hover {
    border-color: #409eff;
    color: #409eff;
    background: #f5f9ff;
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
  cursor: pointer;

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
}

// 设备选择列表
.device-select-list {
  max-height: 400px;
  overflow-y: auto;
}

.device-select-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;

  &:hover {
    border-color: #c0c4cc;
    background: #f5f7fa;
  }

  &.active {
    border-color: #409eff;
    background: #f5f9ff;
  }

  .device-select-icon {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: #ecf5ff;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #409eff;
    font-size: 20px;
  }

  .device-select-info {
    flex: 1;

    .device-select-name {
      font-size: 14px;
      font-weight: 500;
      color: #303133;
      margin-bottom: 4px;
    }

    .device-select-meta {
      display: flex;
      align-items: center;
      gap: 8px;

      .device-ip {
        font-size: 12px;
        color: #909399;
      }
    }
  }

  .device-selected-check {
    color: #409eff;
    font-size: 20px;
  }
}

// 设备下拉选项样式
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

// 弹窗底部
.dialog-footer {
  text-align: center;
  padding-top: 10px;
  border-top: 1px solid #e4e7ed;
  margin-top: 10px;
}
</style>
