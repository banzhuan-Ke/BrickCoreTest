<template>
  <PageCard style="margin-left: 3px;margin-top: 3px">
    <template #title>
      <b>执行记录</b>
    </template>
    <template #main>
      <div style="margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
        <el-input
          v-model="searchForm.name"
          placeholder="搜索任务名称"
          clearable
          style="width: 180px;"
          @keyup.enter="handleSearch"
        />
        <el-select v-model="searchForm.status" placeholder="执行状态" clearable style="width: 130px;">
          <el-option label="等待执行" value="等待执行"/>
          <el-option label="执行中" value="执行中"/>
          <el-option label="执行成功" value="执行完成"/>
          <el-option label="失败" value="失败"/>
          <el-option label="错误" value="错误"/>
        </el-select>
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
      </div>
      <el-table :data="RunRecordList" :header-cell-style="{'text-align':'center'}" :cell-style="{'text-align':'center'}"
                stripe>
        <template #empty>
          <div class="table-empty">
            <div class="empty-icon">
              <el-icon :size="40" color="#909399"><List /></el-icon>
            </div>
            <div>暂无数据</div>
          </div>
        </template>
        <el-table-column label="序号" type="index" width="90"/>
        <el-table-column prop="task_name" show-overflow-tooltip label="任务名称"/>
        <el-table-column label="浏览器" prop="browser_type">
          <template #default="scope">
            <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
            <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
            <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="Base_url" show-overflow-tooltip min-width='100'>
          <template #default="scope">
            {{ scope.row.env?.target_host || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="执行状态" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.status === '执行完成' || scope.row.status === 'success'" type="success">执行成功</el-tag>
            <el-tag v-else-if="scope.row.status === '执行中' || scope.row.status === 'running'" type="primary">执行中</el-tag>
            <el-tag v-else-if="scope.row.status === '等待执行' || scope.row.status === 'pending'" type="info">等待执行</el-tag>
            <el-tag v-else-if="scope.row.status === '失败' || scope.row.status === 'fail' || scope.row.status === 'failed'" type="danger">失败</el-tag>
            <el-tag v-else-if="scope.row.status === '错误' || scope.row.status === 'error'" type="warning">错误</el-tag>
            <span v-else>{{ scope.row.status }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="case_count" label="用例总数"/>
        <el-table-column prop="success" label="成功"/>
        <el-table-column prop="fail" label="失败"/>
        <el-table-column prop="error" label="错误"/>
        <el-table-column prop="skip" label="跳过"/>
        <el-table-column prop="no_run" label="未运行"/>
        <el-table-column label="通过率" min-width='100'>
          <template #default="scope">
            {{ (scope.row.pass_rate || 0).toFixed(2) + '%' }}
          </template>
        </el-table-column>
        <el-table-column prop="username" label="执行人"/>
        <el-table-column prop="create_time" label="执行时间" min-width='150'>
          <template #default="scope">
            {{ dateTools.rTime(scope.row.start_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="duration" label="执行耗时">
          <template #default="scope">
            <!-- 保留两位小数-->
            {{ scope.row.duration.toFixed(2) }}秒
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250px">
          <template #default="scope">
            <el-button-group>
              <el-button @click="showReport(scope.row.id)" type="success" size="small" title="查看报告">
                <el-icon><View /></el-icon>
              </el-button>
              <el-button @click="exportReport(scope.row)" type="primary" size="small" title="导出报告">
                <el-icon><Download /></el-icon>
              </el-button>
              <el-button @click="clickDelete(scope.row.id)" type="danger" size="small" title="删除记录">
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

    </template>
    <template #bottom>
      <el-pagination
          v-model:current-page="pageConfig.page"
          v-model:page-size="pageConfig.size"
          :page-sizes="[10, 20, 30, 40]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="pageConfig.total"
          @current-change="getRunRecordList"
          @size-change="getRunRecordList"
      />
    </template>
  </PageCard>
  
  <!-- 导出选项弹窗 -->
  <el-dialog
    v-model="exportDialogVisible"
    title="导出报告选项"
    width="400px"
    :close-on-click-modal="false"
  >
    <el-form :model="exportOptions" label-width="120px">
      <el-form-item label="包含图片">
        <el-switch v-model="exportOptions.include_images" />
      </el-form-item>
      
      <el-form-item label="图片范围" v-if="exportOptions.include_images">
        <el-radio-group v-model="exportOptions.image_mode">
          <el-radio label="all">全部</el-radio>
          <el-radio label="failed">仅失败</el-radio>
        </el-radio-group>
      </el-form-item>
      

      
      <el-form-item label="包含视频">
        <el-switch v-model="exportOptions.include_video" />
      </el-form-item>
    </el-form>
    
    <template #footer>
      <el-button @click="exportDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmExport" :loading="exportLoading">
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import {ref, reactive} from 'vue'
import {List, Search, RefreshRight} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {useRouter} from 'vue-router'
import PageCard from "@/components/PageCard.vue"
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'

// 导出选项弹窗
const exportDialogVisible = ref(false)
const exportLoading = ref(false)
const currentExportRow = ref(null)
const exportOptions = reactive({
  include_images: true,
  image_mode: 'failed',  // 默认只导出失败截图
  include_video: false,  // 默认不导出视频
  compress_images: true
})

const proStore = ProjectStore()
const router = useRouter()
// 获取运行记录列表数据
const RunRecordList = ref([])

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0,
  project_id: proStore.projectInfo.id
})

const searchForm = reactive({
  name: '',
  status: '',
  dateRange: []
})

// 获取运行记录数据
const getRunRecordList = async () => {
  const params = { ...pageConfig }
  if (searchForm.name) params.name = searchForm.name
  if (searchForm.status) params.status = searchForm.status
  if (searchForm.dateRange && searchForm.dateRange.length === 2) {
    params.start_date = searchForm.dateRange[0]
    params.end_date = searchForm.dateRange[1]
  }
  const res = await http.resultApi.getTaskRecord(params)
  RunRecordList.value = res.data.data
  pageConfig.total = res.data.total
}
getRunRecordList()

const handleSearch = () => {
  pageConfig.page = 1
  getRunRecordList()
}

const resetSearch = () => {
  searchForm.name = ''
  searchForm.status = ''
  searchForm.dateRange = []
  pageConfig.page = 1
  getRunRecordList()
}

// 删除任务运行记录
const clickDelete = async (record_id) => {
  ElMessageBox.confirm(
      '此操作不可恢复，确定删除该任务运行记录吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const res = await http.resultApi.deleteTaskRecord(record_id)
        if (res.status === 204) {
          await getRunRecordList()
          ElNotification({
            type: 'success',
            title: '已成功删除任务运行记录！',
            duration: 1500,
          })
        } else {
          ElMessage({
            type: 'error',
            title: '删除任务运行记录失败！',
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

// 显示报告详情
const reportDialog = ref(false)
const selectedRecordId = ref(null)

// 修改后的查看报告方法
// 路由跳转到报告页面（默认图表模式）
const showReport = (id) => {
  router.push({
    name: 'taskReport',
    params: {id},
    query: {mode: 'chart'}
  })
}

// 导出测试报告 - 显示选项弹窗
const exportReport = (row) => {
  currentExportRow.value = row
  exportDialogVisible.value = true
}

// 确认导出
const confirmExport = async () => {
  if (!currentExportRow.value) return
  
  exportLoading.value = true
  try {
    const row = currentExportRow.value
    const { data } = await http.resultApi.exportReportAsync(row.id, 'task', {
      include_images: exportOptions.include_images,
      image_mode: exportOptions.image_mode,
      include_video: exportOptions.include_video
    })
    const taskId = data.task_id
    exportDialogVisible.value = false
    ElNotification({
      type: 'info',
      title: '报告生成中',
      message: '系统正在后台生成报告，请稍候...',
      duration: 2000
    })
    
    const timer = setInterval(async () => {
      try {
        const { data: statusData } = await http.resultApi.getExportStatus(taskId)
        if (statusData.status === 'completed') {
          clearInterval(timer)
          exportLoading.value = false
          const link = document.createElement('a')
          link.href = statusData.download_url
          link.download = statusData.filename || `测试报告-${row.task_name}-${row.id}.html`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          ElNotification({
            type: 'success',
            title: '报告导出成功！',
            duration: 1500
          })
        } else if (statusData.status === 'failed') {
          clearInterval(timer)
          exportLoading.value = false
          ElNotification({
            type: 'error',
            title: '报告导出失败',
            message: statusData.error || '未知错误',
            duration: 3000
          })
        }
      } catch (e) {
        clearInterval(timer)
        exportLoading.value = false
        ElNotification({
          type: 'error',
          title: '查询导出状态失败',
          duration: 3000
        })
      }
    }, 2000)
  } catch (error) {
    exportLoading.value = false
    ElNotification({
      type: 'error',
      title: '提交导出任务失败',
      message: error.response?.data?.detail || '请稍后重试',
      duration: 3000
    })
  }
}
</script>

<style scoped>
</style>
