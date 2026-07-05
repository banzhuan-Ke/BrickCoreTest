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
        <el-table-column label="序号" type="index" :index="tableRowIndex" width="90"/>
        <el-table-column prop="name" label="计划名称" show-overflow-tooltip width="150"/>
        <el-table-column prop="suites_count" label="套件数量"/>
        <el-table-column prop="parallel" label="执行模式" width="100">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.parallel ? 'warning' : 'info'">
              {{ scope.row.parallel ? '并行' : '串行' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="run_count" label="执行次数"/>
        <el-table-column prop="status" label="最近执行状态">
          <template #default="scope">
            <el-tag v-if='scope.row.status==="执行中"' type="primary">执行中</el-tag>
            <el-tag v-else-if='scope.row.status==="等待执行"' type="info">等待执行</el-tag>
            <el-tag v-else-if='scope.row.status==="执行完成"' type="success">执行完成</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="创建人"/>
        <el-table-column prop="update_by" label="最后更新人" width="110">
          <template #default="scope">
            {{ scope.row.update_by || scope.row.username || '—' }}
          </template>
        </el-table-column>
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
            <el-button v-if="canExecute" type="warning" plain @click="clickRun(scope.row.id)" icon="Promotion">运行</el-button>
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
  <el-dialog v-model="showRunDlg" title="计划运行配置" width="720px" destroy-on-close>
    <el-form label-width="88px" class="ui-run-config-form">
      <el-form-item label="运行环境" required>
        <UiRunEnvSelect v-model="runParams.env_id" />
      </el-form-item>
      <el-form-item label="浏览器" required>
        <div class="ui-run-segment-group">
          <div
            :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.browser_type === 'chromium' }]"
            @click="runParams.browser_type = 'chromium'"
          >
            <el-icon><ChromeFilled /></el-icon><span>Chrome</span>
          </div>
          <div
            :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.browser_type === 'firefox' }]"
            @click="runParams.browser_type = 'firefox'"
          >
            <el-icon><Compass /></el-icon><span>Firefox</span>
          </div>
          <div
            :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.browser_type === 'webkit' }]"
            @click="runParams.browser_type = 'webkit'"
          >
            <el-icon><Apple /></el-icon><span>Safari</span>
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
            <span>开启</span>
          </div>
          <div
            :class="['ui-run-segment', 'ui-run-segment--grow', { active: runParams.ai_heal_enabled === false }]"
            @click="runParams.ai_heal_enabled = false"
          >
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
      </el-form-item>
      <el-form-item label="执行设备" required>
        <template v-if="runTaskParallel">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="ui-run-parallel-hint"
            title="并行模式：按权重分配套件；同一执行器可同时跑多个 Browser（受并发数限制）。"
          />
          <el-table :data="runDeviceRows" size="small" class="ui-run-device-table" border table-layout="fixed">
            <el-table-column label="选用" width="52" align="center" fixed="left">
              <template #default="{ row }">
                <el-checkbox v-model="row.selected" />
              </template>
            </el-table-column>
            <el-table-column label="执行器" min-width="168">
              <template #default="{ row }">
                <div class="ui-run-device-table__name">{{ row.name || row.username }}</div>
                <div class="ui-run-device-table__ip">{{ row.ip }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="68" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'online' || row.status === '在线'" type="success" size="small">在线</el-tag>
                <el-tag v-else type="info" size="small">离线</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="权重" width="108" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-model="row.weight"
                  :min="1"
                  :max="100"
                  size="small"
                  :disabled="!row.selected"
                  controls-position="right"
                  class="ui-run-device-table__number"
                />
              </template>
            </el-table-column>
            <el-table-column label="并发" width="108" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-model="row.concurrency"
                  :min="1"
                  :max="20"
                  size="small"
                  :disabled="!row.selected"
                  controls-position="right"
                  class="ui-run-device-table__number"
                />
              </template>
            </el-table-column>
          </el-table>
        </template>
        <template v-else>
          <el-select v-model="runParams.device_id" placeholder="请选择执行设备" style="width: 100%">
            <el-option
              v-for="device in deviceList"
              :key="device.id"
              :label="device.name || device.username"
              :value="device.id"
            >
              <div class="ui-run-device-option">
                <span class="ui-run-device-option__name">{{ device.name || device.username }}</span>
                <span class="ui-run-device-option__ip">{{ device.ip }}</span>
                <el-tag v-if="device.status === 'online' || device.status === '在线'" type="success" size="small">在线</el-tag>
                <el-tag v-else type="info" size="small">离线</el-tag>
              </div>
            </el-option>
          </el-select>
          <div class="ui-run-concurrency-row">
            <span class="ui-run-concurrency-row__label">并发数</span>
            <el-input-number v-model="runParams.concurrency" :min="1" :max="20" size="small" controls-position="right" />
            <span class="ui-run-concurrency-row__tip">同一执行器同时运行的套件数上限</span>
          </div>
        </template>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="ui-run-dialog-footer">
        <el-button @click="showRunDlg = false">取消</el-button>
        <el-button type="primary" @click="runTask()" icon="Promotion" :loading="running">开始运行</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {ref, reactive, computed, onMounted, watch} from 'vue'
import {Calendar, ChromeFilled, Compass, Apple, Promotion, Search, RefreshRight, View, Hide} from "@element-plus/icons-vue"
import { aiConfigApi } from '@/api/modules/ai.js'
import {ProjectStore} from '@/stores/module/ProjectStore'
import http from '@/api/index'
import dateTools from '@/tools/dateTools'
import {ElMessage, ElMessageBox, ElNotification} from 'element-plus'
import TaskRunRecord from "./componets/TaskRecord.vue"
import PageCard from "@/components/PageCard.vue"
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'
import UiRunEnvSelect from '@/components/UiRunEnvSelect.vue'
import {useRouter, useRoute} from "vue-router"
import {UserStore} from "@/stores/module/UserStore.js"
import { makeTableRowIndex } from '@/utils/tableIndex'
import { filterWebRunnerDevices } from '@/utils/runnerDevice'

const router = useRouter()
const route = useRoute()

const proStore = ProjectStore()
const uStore = UserStore()
const canExecute = computed(() => uStore.hasPermission('ui_task:execute'))
const healRunOptions = ref(null)

// 本地任务列表和分页
const taskList = ref([])
const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0
})
const tableRowIndex = makeTableRowIndex(pageConfig)
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
onMounted(() => {
  const qName = route.query.name
  if (qName && typeof qName === 'string') {
    searchForm.name = qName
  }
  getTaskList()
})

watch(
  () => route.query.name,
  (qName) => {
    if (qName && typeof qName === 'string') {
      searchForm.name = qName
      pageConfig.page = 1
      getTaskList()
    }
  },
)

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
const runTaskParallel = ref(false)
const runDeviceRows = ref([])

const syncRunDeviceRows = () => {
  runDeviceRows.value = (deviceList.value || []).map((d) => ({
    ...d,
    selected: true,
    weight: 1,
    concurrency: 3,
  }))
}

// 获取设备列表
const getDeviceList = async () => {
  try {
    const res = await http.deviceApi.getList({ status: '在线' })
    if (res.status === 200) {
      deviceList.value = filterWebRunnerDevices(res.data || [])
      syncRunDeviceRows()
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
  headless: false,
  ai_heal_enabled: true,
  concurrency: 3,
})

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

// 点击运行计划
const clickRun = async (task_id) => {
  runParams.env_id = ''
  runParams.browser_type = 'chromium'
  runParams.device_id = ''
  runParams.task_id = task_id
  runParams.username = uStore.userInfo.username
  runParams.headless = false
  runParams.ai_heal_enabled = true
  runParams.concurrency = 3
  runTaskParallel.value = false
  await loadHealRunOptions()
  try {
    const detail = await http.taskApi.getTaskDetail(task_id)
    runTaskParallel.value = !!detail.data?.parallel
  } catch {
    const row = taskList.value.find((t) => t.id === task_id)
    runTaskParallel.value = !!row?.parallel
  }
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
  let payload = { ...runParams }
    if (runTaskParallel.value) {
    const selected = runDeviceRows.value.filter((r) => r.selected && (r.status === '在线' || r.status === 'online'))
    if (!selected.length) {
      ElMessage.warning('请至少选择一个在线执行器')
      return
    }
    payload = {
      ...payload,
      device_id: null,
      config: runParams.headless,
      devices: selected.map((r) => ({
        device_id: r.id,
        weight: r.weight || 1,
        concurrency: r.concurrency || 1,
      })),
    }
  } else if (!runParams.device_id) {
    ElMessage.warning('请选择执行设备')
    return
  } else {
    payload.config = runParams.headless
    payload.concurrency = runParams.concurrency || 1
  }
  if (healRunOptions.value?.locator_heal_allow_run_override) {
    payload.ai_heal_enabled = runParams.ai_heal_enabled
  }

  running.value = true
  try {
    const response = await http.runnerApi.runTask(runParams.task_id, payload)
    showRunDlg.value = false
    if (response.status === 201) {
      const dispatched = response.data?.dispatched !== false
      ElNotification({
        title: dispatched ? '计划已提交运行！' : '记录已创建',
        message: response.data?.msg || (dispatched ? undefined : '暂无在线执行器，请稍后重试'),
        type: dispatched ? 'success' : 'warning',
        duration: 2500
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
@use '@/style/ui-run-config.scss';
</style>
