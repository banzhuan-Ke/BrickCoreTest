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
        <el-button type="danger" @click="handleBatchDelete" :disabled="selectedIds.length === 0" icon="Delete">批量删除</el-button>
      </div>

      <el-table :data="logList" style="width: 100%" :header-cell-style="{'text-align':'center'}"
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
        <el-table-column label="序号" type="index" width="70"/>
        <el-table-column prop="username" label="操作人" width="120"/>
        <el-table-column prop="action" label="操作行为" width="140"/>
        <el-table-column prop="module" label="所属模块" width="110"/>
        <el-table-column prop="path_name" label="路径名称" min-width="160" show-overflow-tooltip/>
        <el-table-column label="请求方法/路径" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            <el-tag size="small" :type="methodType(scope.row.method)">{{ scope.row.method }}</el-tag>
            <span style="margin-left: 6px;">{{ scope.row.path }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status_code" label="状态码" width="90">
          <template #default="scope">
            <el-tag size="small" :type="statusType(scope.row.status_code)">{{ scope.row.status_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="IP地址" width="130"/>
        <el-table-column prop="create_time" label="操作时间" width="170"/>
        <el-table-column label="参数" width="80">
          <template #default="scope">
            <el-button v-if="hasParams(scope.row.params)" link type="primary" @click="showParams(scope.row)">查看</el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
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

const logList = ref([])
const loading = ref(false)
const pageConfig = reactive({
  page: 1,
  size: 20,
  total: 0
})
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
