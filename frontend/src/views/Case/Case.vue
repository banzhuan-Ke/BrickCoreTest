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
        <el-checkbox v-model="showFavoritesOnly" @change="handleSearch">只看收藏</el-checkbox>
        <TableColumnPicker
          :items="pickerItems"
          @toggle="setColumnVisible"
          @reorder="setPickerOrder"
          @reset="resetColumns"
        />
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
      <el-table
        :key="tableRenderKey"
        :data="caseList"
        :header-cell-style="{'text-align':'center'}"
        :cell-style="{'text-align':'center'}"
        stripe
        @selection-change="handleSelectionChange"
      >
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><DocumentChecked /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column label="收藏" width="52" align="center">
          <template #default="{ row }">
            <el-button link :type="isFavorite(row.id) ? 'warning' : 'info'" @click.stop="toggleFavorite(row.id)">
              <el-icon><StarFilled v-if="isFavorite(row.id)" /><Star v-else /></el-icon>
            </el-button>
          </template>
        </el-table-column>
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
            label="用例名称"
            show-overflow-tooltip
            :min-width="col.minWidth || 150"
          />
          <el-table-column
            v-else-if="col.key === 'run_count'"
            prop="run_count"
            label="运行次数"
          />
          <el-table-column
            v-else-if="col.key === 'status'"
            prop="status"
            label="最近运行结果"
            :width="col.width || 120"
          >
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
          <el-table-column
            v-else-if="col.key === 'step_count'"
            prop="steps_count"
            label="步骤数"
          />
          <el-table-column
            v-else-if="col.key === 'username'"
            prop="username"
            label="创建人"
          />
          <el-table-column
            v-else-if="col.key === 'update_by'"
            prop="update_by"
            label="最后更新人"
            :width="col.width"
          >
            <template #default="scope">
              {{ scope.row.update_by || scope.row.username || '—' }}
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'level'"
            prop="level"
            label="用例级别"
            :width="col.width"
          >
            <template #default="scope">
              <el-tag v-if='scope.row.level==="P0"' type="danger">P0</el-tag>
              <el-tag v-else-if='scope.row.level==="P1"' type="warning">P1</el-tag>
              <el-tag v-else-if='scope.row.level==="P2"' type="primary">P2</el-tag>
              <el-tag v-else-if='scope.row.level==="P3"' type="info">P3</el-tag>
              <span v-else>{{ scope.row.level }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'source_functional_case'"
            label="来源功能用例"
            :min-width="col.minWidth || 160"
            show-overflow-tooltip
          >
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
          <el-table-column
            v-else-if="col.key === 'update_time'"
            label="更新时间"
            :min-width="col.minWidth || 180"
          >
            <template #default="scope">
              {{ dateTools.rTime(scope.row.update_time) }}
            </template>
          </el-table-column>
        </template>
        <el-table-column label="操作" width="300px">
          <template #default="scope">
            <el-button v-if="canExecute" @click="clickRun(scope.row.id)" plain icon="Promotion" type="warning">运行</el-button>
            <el-button @click="clickRecord(scope.row.id)" plain type="success" icon="View">报告</el-button>
            <el-dropdown>
              <el-button type="primary" plain icon="MoreFilled" style="margin-left:10px">更多</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="goEditCase(scope.row.id)" icon="Edit">
                    编辑
                  </el-dropdown-item>
                  <el-dropdown-item @click="CopyCase(scope.row.id)" icon="DocumentCopy">
                    复制到本项目
                  </el-dropdown-item>
                  <el-dropdown-item @click="openCopyDialog(scope.row)" icon="CopyDocument">
                    复制到其他项目
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
          @current-change="handlePageChange"
          @size-change="handlePageChange"
      />
    </template>
  </PageCard>
  <!--运行测试用例-->
  <!-- 运行任务的弹框-->
  <el-dialog v-model="showRunDlg" title="用例运行配置" width="560px" destroy-on-close>
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
          :title="`本次将按项目默认：${healRunOptions.locator_heal_default_on_execute ? '开启' : '关闭'}自愈（运行弹窗不可改）`"
        />
      </el-form-item>
      <el-form-item label="执行设备" required>
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
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="ui-run-dialog-footer">
        <el-button @click="showRunDlg = false">取消</el-button>
        <el-button type="primary" @click="runCase()" icon="Promotion" :loading="running">开始运行</el-button>
      </div>
    </template>
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

  <CopyToProjectDialog
    v-model="copyDialog.visible"
    title="复制 Web 用例到其他项目"
    :asset-name="copyDialog.row?.name"
    :submit-fn="submitCopyCase"
    @success="getCasesList"
  />
</template>

<script setup>
import {ref, reactive, computed, onMounted, watch} from 'vue'
import {DocumentChecked, ChromeFilled, Compass, Apple, Promotion, Search, RefreshRight, View, Hide, CircleCheck, CircleClose, Star, StarFilled} from "@element-plus/icons-vue"
import http from '@/api/index'
import { uiCaseApi } from '@/api/modules/ui'
import { aiConfigApi } from '@/api/modules/ai.js'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {useRouter, useRoute} from 'vue-router'
import DeviceInfo from "@/views/Device/DeviceInfo.vue"
import PageCard from "@/components/PageCard.vue"
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import CatalogListLayout from '@/components/CatalogListLayout.vue'
import { useTableColumns } from '@/composables/useTableColumns.js'
import CaseRecord from "@/views/Case/componets/CaseRecord.vue"
import { filterWebRunnerDevices } from '@/utils/runnerDevice'
import BatchCatalogDialog from '@/components/BatchCatalogDialog.vue'
import UiRunEnvSelect from '@/components/UiRunEnvSelect.vue'
import {UserStore} from "@/stores/module/UserStore.js"
import CopyToProjectDialog from '@/components/CopyToProjectDialog.vue'
import { useAssetFavorites } from '@/composables/useAssetFavorites'
import { makeTableRowIndex } from '@/utils/tableIndex'

const {
  activeColumns,
  pickerItems,
  tableRenderKey,
  setColumnVisible,
  setPickerOrder,
  resetColumns
} = useTableColumns('ui.cases')

const proStore = ProjectStore()
const uStore = UserStore()
const router = useRouter()
const route = useRoute()
const canExecute = computed(() => uStore.hasPermission('ui_case:execute'))

const goFunctionalCase = (id) => {
  router.push({ name: 'aiFunctionalCases', query: { highlight: id } })
}

// 获取用例列表数据
const caseList = ref([])
const selectedCases = ref([])
const importResultDlg = reactive({ visible: false, result: null })
const batchCatalogDialog = reactive({ visible: false })
const copyDialog = reactive({ visible: false, row: null })
const { loadFavorites, isFavorite, toggleFavorite, sortByFavorites } = useAssetFavorites('ui_case')
const showFavoritesOnly = ref(false)

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0,
  project_id: proStore.projectInfo.id
})

const tableRowIndex = makeTableRowIndex(pageConfig)

const searchForm = reactive({
  name: '',
  catalog_id: null,
  status: '',
  level: ''
})

const buildRouteQuery = () => {
  const query = {}
  if (searchForm.name) query.name = searchForm.name
  if (searchForm.catalog_id) query.catalog_id = String(searchForm.catalog_id)
  if (searchForm.status) query.status = searchForm.status
  if (searchForm.level) query.level = searchForm.level
  if (showFavoritesOnly.value) query.favorites = '1'
  if (pageConfig.page > 1) query.page = String(pageConfig.page)
  if (pageConfig.size !== 10) query.size = String(pageConfig.size)
  return query
}

const isSameRouteQuery = (nextQuery) => {
  const keys = new Set([...Object.keys(nextQuery), ...Object.keys(route.query)])
  for (const key of keys) {
    if (String(nextQuery[key] ?? '') !== String(route.query[key] ?? '')) {
      return false
    }
  }
  return true
}

const applyRouteQuery = (query = route.query) => {
  searchForm.name = typeof query.name === 'string' ? query.name : ''
  searchForm.catalog_id = query.catalog_id ? Number(query.catalog_id) || null : null
  searchForm.status = typeof query.status === 'string' ? query.status : ''
  searchForm.level = typeof query.level === 'string' ? query.level : ''
  showFavoritesOnly.value = query.favorites === '1'
  pageConfig.page = query.page ? Number(query.page) || 1 : 1
  pageConfig.size = query.size ? Number(query.size) || 10 : 10
}

let skipRouteWatch = false

const syncRouteQuery = async () => {
  const query = buildRouteQuery()
  if (isSameRouteQuery(query)) {
    await getCasesList()
    return
  }
  skipRouteWatch = true
  await router.replace({ name: route.name, query })
  skipRouteWatch = false
  await getCasesList()
}

const refreshListFromRoute = () => {
  applyRouteQuery()
  getCasesList()
}

const goEditCase = (id) => {
  const query = buildRouteQuery()
  if (!isSameRouteQuery(query)) {
    router.replace({ name: route.name, query })
  }
  router.push({ name: 'editCase', params: { id } })
}

// 获取用例数据
const getCasesList = async () => {
  await loadFavorites()
  const params = { ...pageConfig }
  if (searchForm.name) params.name = searchForm.name
  if (searchForm.status) params.status = searchForm.status
  if (searchForm.level) params.level = searchForm.level
  if (searchForm.catalog_id) params.catalog_id = searchForm.catalog_id
  const res = await http.caseApi.getList(params)
  let rows = res.data.data || []
  rows = sortByFavorites(rows)
  if (showFavoritesOnly.value) {
    rows = rows.filter((r) => isFavorite(r.id))
  }
  caseList.value = rows
  pageConfig.total = showFavoritesOnly.value ? rows.length : res.data.total
}

onMounted(() => {
  refreshListFromRoute()
})

watch(
  () => [
    route.query.name,
    route.query.catalog_id,
    route.query.status,
    route.query.level,
    route.query.favorites,
    route.query.page,
    route.query.size,
  ],
  () => {
    if (skipRouteWatch) return
    refreshListFromRoute()
  },
)

const openCopyDialog = (row) => {
  copyDialog.row = row
  copyDialog.visible = true
}

const submitCopyCase = (payload) => uiCaseApi.copy(copyDialog.row.id, payload)

const handleSearch = async () => {
  pageConfig.page = 1
  await syncRouteQuery()
}

const handlePageChange = async () => {
  await syncRouteQuery()
}

const resetSearch = async () => {
  searchForm.catalog_id = null
  searchForm.name = ''
  searchForm.status = ''
  searchForm.level = ''
  showFavoritesOnly.value = false
  pageConfig.page = 1
  await syncRouteQuery()
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
      deviceList.value = filterWebRunnerDevices(res.data || [])
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
  headless: false,
  ai_heal_enabled: true
})

const clickRun = async (case_id) => {
  // 重置运行参数
  runParams.env_id = ''
  runParams.browser_type = 'chromium'
  runParams.device_id = ''
  runParams.case_id = case_id
  runParams.username = uStore.userInfo.username
  runParams.headless = false
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
    const payload = {
      env_id: runParams.env_id,
      browser_type: runParams.browser_type,
      device_id: runParams.device_id,
      case_id: runParams.case_id,
      username: runParams.username,
      config: runParams.headless,
    }
    if (healRunOptions.value?.locator_heal_allow_run_override) {
      payload.ai_heal_enabled = runParams.ai_heal_enabled
    }
    const response = await http.runnerApi.runCase(payload.case_id, payload)
    showRunDlg.value = false
    if (response.status === 201) {
      const dispatched = response.data?.dispatched !== false
      ElNotification({
        title: dispatched ? '用例已提交运行！' : '记录已创建',
        message: response.data?.msg || (dispatched ? undefined : '暂无在线执行器，请稍后重试'),
        type: dispatched ? 'success' : 'warning',
        duration: 2500,
      })
      // 显示执行设备状态
      if (runParams.case_id && dispatched) {
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
@use '@/style/ui-run-config.scss';
</style>
