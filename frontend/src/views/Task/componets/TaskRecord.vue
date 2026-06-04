<template>
  <el-table :data="RunRecordList" style="width: calc(100% - 40px)" :header-cell-style="{'text-align':'center'}"
            :cell-style="{'text-align':'center'}" stripe>
    <template #empty>
      <div class="table-empty">
        <div class="empty-icon">
          <el-icon :size="40" color="#909399"><List /></el-icon>
        </div>
        <div>暂无数据</div>
      </div>
    </template>
    <el-table-column label="序号" type="index" width="90"/>
    <el-table-column prop="task_name" label="计划名称" min-width='100' show-overflow-tooltip/>
    <el-table-column label="浏览器" prop="browser">
      <template #default="scope">
        <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
        <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
        <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
        <span v-else class="text-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="headless" label="执行模式" min-width='100'>
      <template #default="scope">
        <el-tag v-if='scope.row.env?.headless === false' type="success">界面模式</el-tag>
        <el-tag v-else-if='scope.row.env?.headless === true' type="primary">无头模式</el-tag>
        <span v-else class="text-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="status" label="执行状态" min-width='100'>
      <template #default="scope">
        <el-tag v-if="scope.row.status === '执行完成'" type="success">执行完成</el-tag>
        <el-tag v-if="scope.row.status === '执行中'" type="primary">执行中</el-tag>
        <el-tag v-if="scope.row.status === '等待执行'" type="info">等待执行</el-tag>
        <el-tag v-if="scope.row.status === '已停止'" type="warning">已停止</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="触发方式" width="90" align="center">
      <template #default="scope">
        <el-tag
          :type="scope.row.env?.trigger_source === 'assistant' ? 'success' : 'info'"
          size="small"
        >
          {{ scope.row.env?.trigger_source === 'assistant' ? '小测' : '手动' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="case_count" label="用例总数"/>
    <el-table-column prop="success" label="成功数"/>
    <el-table-column prop="fail" label="失败数"/>
    <el-table-column prop="error" label="错误数"/>
    <el-table-column prop="skip" label="跳过数"/>
    <el-table-column prop="no_run" label="未运行数"/>
    <el-table-column label="通过率" min-width='100'>
      <template #default="scope">
        {{ (scope.row.pass_rate || 0).toFixed(2) + '%' }}
      </template>
    </el-table-column>
    <el-table-column prop="username" label="执行人"/>
    <el-table-column prop="create_time" label="执行时间" min-width='200'>
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
    <el-table-column label="操作" width="260px">
      <template #default="scope">
        <el-button
          v-if="['执行中', '等待执行'].includes(scope.row.status)"
          @click="clickStop(scope.row.id)"
          type="warning"
          plain
          icon="VideoPause"
        >停止</el-button>
        <el-button @click="showReport(scope.row.id)" type="success" plain icon="View">报告</el-button>
        <el-tooltip class="box-item" effect="dark" content="将删除计划、套件、用例运行记录" placement="bottom">
          <el-button @click="clickDelete(scope.row.id)" plain type="danger" icon="Delete">删除</el-button>
        </el-tooltip>
      </template>
    </el-table-column>
  </el-table>

  <!--  分页器-->
  <el-pagination
      :hide-on-single-page="true"
      v-model:current-page="pageConfig.page"
      v-model:page-size="pageConfig.size"
      :page-sizes="[10, 20, 30, 40]"
      layout="total, sizes, prev, pager, next, jumper"
      :total="pageConfig.total"
      @current-change="getRunRecordList"
      @size-change="getRunRecordList"
  />
</template>

<script setup>
import {ref, reactive, watch} from 'vue'
import {List} from "@element-plus/icons-vue"
import http from '@/api/index'
import {ProjectStore} from "@/stores/module/ProjectStore.js"
import dateTools from '@/tools/dateTools'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import {useRouter} from 'vue-router'

const router = useRouter()
// 定义props
const props = defineProps({
  task_id: {
    type: Number,
    default: 0
  }
})

const proStore = ProjectStore()
// 获取运行记录列表数据
const RunRecordList = ref([])

const pageConfig = reactive({
  task_id: 0,
  page: 1,
  size: 10,
  total: 0,
  project_id: proStore.projectInfo.id
})

// 获取运行记录数据
const getRunRecordList = async () => {
  pageConfig.task_id = props.task_id
  const res = await http.resultApi.getTaskRecord(pageConfig)
  RunRecordList.value = res.data.data
  pageConfig.total = res.data.total
}

getRunRecordList()

// 侦听器 监听计划id
watch(() => props.task_id, (newVal, oldVal) => {
  pageConfig.task_id = newVal
  getRunRecordList()
})

// 路由跳转到报告页面（默认图表模式）
const showReport = (id) => {
  router.push({
    name: 'taskReport',
    params: {id},
    query: {mode: 'chart'}
  })
}

// 停止计划执行
const clickStop = async (record_id) => {
  try {
    await ElMessageBox.confirm('确定停止当前 UI 计划执行吗？执行器将收到中断信号。', '停止执行', { type: 'warning' })
    await http.runnerApi.stopPlan(record_id)
    ElMessage.success('停止信号已发送')
    await getRunRecordList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '停止失败')
  }
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
          ElNotification({
            type: 'error',
            title: '任务运行记录删除失败！',
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
</script>

<style scoped>
</style>