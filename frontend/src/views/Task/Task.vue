<template>
  <PageCard>
    <template #title>
      <el-button type="primary" size="small" @click="ClickAdd" icon="Plus">计划</el-button>
    </template>
    <template #main>
      <CatalogListLayout
        :project-id="proStore.projectInfo.id"
        v-model="searchForm.catalog_id"
        all-node-label="全部计划"
        @change="handleSearch"
      >
      <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
        <el-input
          v-model="searchForm.name"
          placeholder="搜索计划名称"
          clearable
          style="width: 180px;"
          @keyup.enter="handleSearch"
        />
        <el-select v-model="searchForm.status" placeholder="执行状态" clearable style="width: 130px;">
          <el-option label="等待执行" value="等待执行"/>
          <el-option label="执行中" value="执行中"/>
          <el-option label="执行完成" value="执行完成"/>
        </el-select>
        <el-button type="primary" @click="handleSearch" icon="Search">搜索</el-button>
        <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
      </div>
      <el-table :data="taskList" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><Calendar /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="name" label="计划名称" show-overflow-tooltip width="150"/>
        <el-table-column prop="suites_count" label="套件数量"/>
        <el-table-column prop="run_count" label="执行次数"/>
        <el-table-column prop="status" label="最近执行状态">
          <template #default="scope">
            <el-tag v-if='scope.row.status==="执行中"' type="primary">执行中</el-tag>
            <el-tag v-else-if='scope.row.status==="等待执行"' type="info">等待执行</el-tag>
            <el-tag v-else-if='scope.row.status==="执行完成"' type="success">执行完成</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="创建人"/>
        <el-table-column prop="create_time" label="创建时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="150">
          <template #default="scope">
            {{ dateTools.rTime(scope.row.update_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="400">
          <template #default="scope">
            <el-button type="warning" plain @click="clickRun(scope.row.id)" icon="Promotion">运行</el-button>
            <el-button type="success" plain @click="showRunRecord(scope.row)" icon="View">报告</el-button>
            <el-button type="primary" plain @click="router.push({name: 'editTask',params:{id: scope.row.id}})"
                       icon="Edit">编辑
            </el-button>
            <el-button type="danger" plain @click="handleDelete(scope.row)" icon="Delete">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      </CatalogListLayout>
    </template>
    <template #bottom>
      <el-pagination
        v-model:current-page="pageConfig.page"
        v-model:page-size="pageConfig.size"
        :page-sizes="[10, 20, 30, 40]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="pageConfig.total"
        @current-change="getTaskList"
        @size-change="getTaskList"
      />
    </template>
  </PageCard>

  <!--添加测试计划的弹框-->
  <el-dialog v-model="addDlg" title="创建测试计划" width="30%" center destroy-on-close>
    <el-form :model="addTaskForm" label-width="auto" :rules="formDataRules" ref="formDataRef">
      <el-form-item label="计划名称：" prop="name">
        <el-input v-model="addTaskForm.name"/>
      </el-form-item>
      <el-form-item label="所属目录">
        <CatalogTreeSelect
          v-model="addTaskForm.catalog_id"
          :project-id="proStore.projectInfo.id"
          placeholder="请选择所属目录"
        />
      </el-form-item>
      <el-form-item label="创建人：" prop="username">
        <el-input v-model="addTaskForm.username" placeholder="请输入创建人" disabled/>
      </el-form-item>
    </el-form>
    <template #footer>
			<span class="dialog-footer">
        <el-button type="primary" @click="addTask(formDataRef)">确定</el-button>
        <el-button @click="addDlg = false">取消</el-button>
      </span>
    </template>
  </el-dialog>

  <!--编辑测试计划-->
  <el-dialog v-model="editDlg" title="编辑测试计划" width="30%" center destroy-on-close></el-dialog>

  <!--计划运行记录窗口-->
  <el-dialog v-model="runDlg" width="90%" center destroy-on-close>
    <template #header>
      <div style="font-size: 18px">计划执行记录</div>
    </template>
    <TaskRunRecord :task_id="showTask.id"></TaskRunRecord>
  </el-dialog>

  <!-- 运行计划的弹框-->
  <el-dialog v-model="showRunDlg" title="计划运行配置" width="520px" center destroy-on-close>
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
      <el-button type="primary" size="large" @click="runTask()" icon="Promotion" :loading="running">开始运行</el-button>
    </div>
  </el-dialog>
</template>

<script setup>
import {ref, reactive} from 'vue'
import {Calendar, OfficeBuilding, Monitor, SetUp, View, Hide, Cpu, ChromeFilled, Compass, Apple, Promotion, Search, RefreshRight} from "@element-plus/icons-vue"
import {ProjectStore} from '@/stores/module/ProjectStore'
import http from '@/api/index'
import dateTools from '@/tools/dateTools'
import {ElMessage, ElMessageBox, ElNotification} from 'element-plus'
import TaskRunRecord from "./componets/TaskRecord.vue"
import PageCard from "@/components/PageCard.vue"
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import {useRouter} from "vue-router"
import {UserStore} from "@/stores/module/UserStore.js"

const router = useRouter()

const proStore = ProjectStore()
const uStore = UserStore()

// 本地任务列表和分页
const taskList = ref([])
const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})
const searchForm = reactive({
  name: '',
  catalog_id: null,
  status: ''
})

// 获取项目测试计划列表
const getTaskList = async () => {
  const params = {
    project_id: proStore.projectInfo.id,
    page: pageConfig.page,
    size: pageConfig.size,
  }
  if (searchForm.name) params.name = searchForm.name
  if (searchForm.catalog_id) params.catalog_id = searchForm.catalog_id
  if (searchForm.status) params.status = searchForm.status
  const res = await http.taskApi.getTaskList(params)
  if (res.status === 200) {
    taskList.value = res.data.data
    pageConfig.total = res.data.total
  }
}
getTaskList()

const handleSearch = () => {
  pageConfig.page = 1
  getTaskList()
}

const resetSearch = () => {
  searchForm.name = ''
  searchForm.catalog_id = null
  searchForm.status = ''
  pageConfig.page = 1
  getTaskList()
}

// 删除测试计划
const handleDelete = (row) => {
  // 提示是否确认删除
  ElMessageBox.confirm(
      '此操作不可恢复，确认删除该测试计划吗？',
      '提示', {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const res = await http.taskApi.deleteTask(row.id)
        if (res.status === 204) {
          await getTaskList()
          ElNotification({
            type: 'success',
            title: '已成功删除该计划！',
            duration: 1500
          })
        } else {
          ElNotification({
            type: 'error',
            title: '计划删除失败！',
            duration: 1500,
            message: res.data.detail
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

// 新增测试测试计划
const addDlg = ref(false)
let addTaskForm = reactive({
  project_id: proStore.projectInfo.id,
  name: '',
  catalog_id: null,
  username: uStore.userInfo.username
})
const ClickAdd = () => {
  // 重置表单数据
  Object.assign(addTaskForm, {
    project_id: proStore.projectInfo.id,
    name: '',
    catalog_id: null,
    username: uStore.userInfo.username
  })
  addDlg.value = true
}
// 校验计划名称
const formDataRules = reactive({
  name: [{required: true, message: '计划名称不能为空！', trigger: 'blur'}]
})
// 表单引用对象
const formDataRef = ref()

// 添加测试计划
async function addTask(elForm) {
  elForm.validate(async function (res) {
    if (!res) return
    // 请求参数
    const data = {...addTaskForm}
    const response = await http.taskApi.createTask(data)
    if (response.status === 201) {
      ElNotification({
        type: 'success',
        title: '已成功创建测试计划！',
        duration: 1500
      })
      await getTaskList()
      addDlg.value = false
    } else {
      ElNotification({
        type: 'error',
        title: '计划创建失败！',
        duration: 1500,
        message: response.data.detail
      })
    }
  })
}

// 查看计划执行记录
const runDlg = ref(false)
const showTask = ref({
  id: 0,
  name: '计划名称'
})
const showRunRecord = async (row) => {
  runDlg.value = true
  showTask.value = row
}

// 是否显示运行套件对话框
const showRunDlg = ref(false)
const running = ref(false)

// 设备列表
const deviceList = ref([])

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
  task_id: 1,
  username: uStore.userInfo.username,
  config: 'False'
})

// 点击运行计划
const clickRun = async (task_id) => {
  // 重置运行参数
  runParams.env_id = ''
  runParams.browser_type = 'chromium'
  runParams.device_id = ''
  runParams.task_id = task_id
  runParams.username = uStore.userInfo.username
  runParams.config = 'False'
  // 获取设备列表
  await getDeviceList()
  showRunDlg.value = true
}

// 运行测试计划
async function runTask() {
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
    const response = await http.runnerApi.runTask(runParams.task_id, runParams)
    showRunDlg.value = false
    if (response.status === 201) {
      ElNotification({
        title: '计划已提交运行！',
        type: 'success',
        duration: 1500
      })
      // 刷新页面数据
      await getTaskList()
    } else {
      ElNotification({
        title: '运行失败！',
        message: response.data.detail,
        type: 'error',
        duration: 1500
      })
    }
  } finally {
    running.value = false
  }
}

// 编辑测试计划
const editDlg = ref(false)
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
