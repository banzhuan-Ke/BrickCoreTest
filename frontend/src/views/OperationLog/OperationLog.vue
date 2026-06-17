<template>
  <PageCard>
    <template #title>
      <b>操作日志</b>
    </template>
    <template #main>
      <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
        <el-input
          v-model="searchForm.username"
          placeholder="操作人"
          clearable
          style="width: 150px;"
          @keyup.enter="handleSearch"
        />
        <el-select v-model="searchForm.module" placeholder="所属模块" clearable style="width: 140px;">
          <el-option label="系统管理" value="系统管理"/>
          <el-option label="项目配置" value="项目配置"/>
          <el-option label="UI自动化" value="UI自动化"/>
          <el-option label="接口自动化" value="接口自动化"/>
          <el-option label="AI测试" value="AI测试"/>
          <el-option label="性能测试" value="性能测试"/>
          <el-option label="其他" value="其他"/>
        </el-select>
        <el-input
          v-model="searchForm.action"
          placeholder="操作行为"
          clearable
          style="width: 150px;"
          @keyup.enter="handleSearch"
        />
        <el-date-picker
          v-model="searchForm.dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 240px;"
        />
        <el-button type="primary" @click="handleSearch" icon="Search">搜索</el-button>
        <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
        <TableColumnPicker
          :items="pickerItems"
          @toggle="setColumnVisible"
          @reorder="setPickerOrder"
          @reset="resetColumns"
        />
        <el-button type="danger" @click="handleBatchDelete" :disabled="selectedIds.length === 0" icon="Delete">批量删除</el-button>
        <el-button type="warning" :loading="purgingNoise" @click="handlePurgeNoise" icon="Delete">
          清理机器噪音日志
        </el-button>
      </div>

      <el-table :key="tableRenderKey" :data="logList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}" stripe v-loading="loading"
                @selection-change="handleSelectionChange" ref="logTableRef">
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><Clock /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column type="selection" width="55"/>
        <template v-for="col in activeColumns" :key="col.key">
          <el-table-column
            v-if="col.key === 'index'"
            label="序号"
            type="index"
            :index="tableRowIndex"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'username'"
            prop="username"
            label="操作人"
            :width="col.width"
          >
            <template #default="{ row }">
              <el-tag v-if="isMachineUser(row.username)" size="small" type="info">{{ row.username }}</el-tag>
              <el-tag v-else-if="row.username === '未知用户'" size="small" type="warning">{{ row.username }}</el-tag>
              <span v-else>{{ row.username }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'action'"
            prop="action"
            label="操作行为"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'module'"
            prop="module"
            label="所属模块"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'path_name'"
            prop="path_name"
            label="路径名称"
            :min-width="col.minWidth || 160"
            show-overflow-tooltip
          />
          <el-table-column
            v-else-if="col.key === 'method_path'"
            label="请求方法/路径"
            :min-width="col.minWidth || 200"
            show-overflow-tooltip
          >
            <template #default="scope">
              <el-tag size="small" :type="methodType(scope.row.method)">{{ scope.row.method }}</el-tag>
              <span style="margin-left: 6px;">{{ scope.row.path }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'status_code'"
            prop="status_code"
            label="状态码"
            :width="col.width"
          >
            <template #default="scope">
              <el-tag size="small" :type="statusType(scope.row.status_code)">{{ scope.row.status_code }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column
            v-else-if="col.key === 'ip'"
            prop="ip"
            label="IP地址"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'create_time'"
            prop="create_time"
            label="操作时间"
            :width="col.width"
          />
          <el-table-column
            v-else-if="col.key === 'params'"
            label="参数"
            :width="col.width"
          >
            <template #default="scope">
              <el-button v-if="hasParams(scope.row.params)" link type="primary" @click="showParams(scope.row)">查看</el-button>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </template>
      </el-table>
    </template>
    <template #bottom>
      <el-pagination
        v-model:current-page="pageConfig.page"
        v-model:page-size="pageConfig.size"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="pageConfig.total"
        @current-change="getLogList"
        @size-change="getLogList"
      />
    </template>
  </PageCard>

  <!-- 参数详情弹窗 -->
  <el-dialog v-model="paramsDialogVisible" title="请求参数" width="500px" center destroy-on-close>
    <pre style="background: #f5f7fa; padding: 12px; border-radius: 4px; overflow-x: auto;">{{ JSON.stringify(currentParams, null, 2) }}</pre>
    <template #footer>
      <el-button @click="paramsDialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Search, RefreshRight, Delete } from '@element-plus/icons-vue'
import http from '@/api/index'
import PageCard from "@/components/PageCard.vue"
import TableColumnPicker from '@/components/TableColumnPicker.vue'
import { useTableColumns } from '@/composables/useTableColumns.js'
import { makeTableRowIndex } from '@/utils/tableIndex'

const {
  activeColumns,
  pickerItems,
  tableRenderKey,
  setColumnVisible,
  setPickerOrder,
  resetColumns
} = useTableColumns('operation.log')

const logList = ref([])
const loading = ref(false)
const pageConfig = reactive({
  page: 1,
  size: 20,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pageConfig)

const searchForm = reactive({
  username: '',
  module: '',
  action: '',
  dateRange: []
})

const paramsDialogVisible = ref(false)
const currentParams = ref({})
const selectedIds = ref([])
const logTableRef = ref(null)
const purgingNoise = ref(false)

const handleSelectionChange = (selection) => {
  selectedIds.value = selection.map(item => item.id)
}

const handleBatchDelete = () => {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要删除的日志')
    return
  }
  ElMessageBox.confirm(
    `确定要删除选中的 ${selectedIds.value.length} 条日志吗？`,
    '提示',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    const res = await http.operationLogApi.batchDelete(selectedIds.value)
    if (res.status === 204 || res.status === 200) {
      ElMessage.success('删除成功')
      selectedIds.value = []
      getLogList()
    }
  }).catch(() => {})
}

const isMachineUser = (username) => {
  if (!username) return false
  return username.startsWith('压测Worker·')
    || username.startsWith('Runner设备(')
    || username === '系统内部服务'
}

const handlePurgeNoise = () => {
  ElMessageBox.confirm(
    '将删除 Runner 屏幕/设备日志上报、压测 Worker 心跳与秒级上报等机器噪音日志（通常无人工审计价值）。数据量大时会分批删除，请耐心等待。此操作不可恢复，确定继续吗？',
    '清理机器噪音日志',
    { confirmButtonText: '确定清理', cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    purgingNoise.value = true
    let total = 0
    try {
      while (true) {
        const res = await http.operationLogApi.purgeNoiseLogs()
        const deleted = res.data?.deleted ?? 0
        total += deleted
        if (deleted === 0 || res.data?.done) {
          break
        }
      }
      ElMessage.success(total > 0 ? `已清理 ${total} 条噪音日志` : '没有需要清理的噪音日志')
      getLogList()
    } catch (error) {
      ElMessage.error(error?.response?.data?.detail || error?.message || '清理失败')
    } finally {
      purgingNoise.value = false
    }
  }).catch(() => {})
}

const getLogList = async () => {
  loading.value = true
  try {
    const params = {
      page: pageConfig.page,
      size: pageConfig.size,
    }
    if (searchForm.username) params.username = searchForm.username
    if (searchForm.module) params.module = searchForm.module
    if (searchForm.action) params.action = searchForm.action
    if (searchForm.dateRange && searchForm.dateRange.length === 2) {
      params.start_date = searchForm.dateRange[0]
      params.end_date = searchForm.dateRange[1]
    }
    const res = await http.operationLogApi.getList(params)
    if (res.status === 200) {
      logList.value = res.data.data
      pageConfig.total = res.data.total
    }
  } catch (error) {
    console.error('获取操作日志失败:', error)
  } finally {
    loading.value = false
  }
}
getLogList()

const handleSearch = () => {
  pageConfig.page = 1
  getLogList()
}

const resetSearch = () => {
  searchForm.username = ''
  searchForm.module = ''
  searchForm.action = ''
  searchForm.dateRange = []
  pageConfig.page = 1
  getLogList()
}

const methodType = (method) => {
  const map = {
    GET: 'info',
    POST: 'success',
    PUT: 'warning',
    DELETE: 'danger',
    PATCH: 'warning'
  }
  return map[method] || 'info'
}

const statusType = (code) => {
  if (code >= 200 && code < 300) return 'success'
  if (code >= 300 && code < 400) return 'warning'
  if (code >= 400 && code < 500) return 'warning'
  if (code >= 500) return 'danger'
  return 'info'
}

const hasParams = (params) => {
  return params && Object.keys(params).length > 0
}

const showParams = (row) => {
  currentParams.value = row.params
  paramsDialogVisible.value = true
}
</script>

<style scoped>
.table-empty {
  padding: 40px 0;
  text-align: center;
  color: #909399;
}
.empty-icon {
  margin-bottom: 10px;
}
pre {
  margin: 0;
  font-family: 'Courier New', Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #333;
}
</style>
