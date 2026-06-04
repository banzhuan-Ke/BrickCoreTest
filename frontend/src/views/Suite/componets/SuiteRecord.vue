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
    <el-table-column prop="suite_name" label="套件名称" min-width='100' show-overflow-tooltip/>
    <el-table-column prop="status" label="执行状态" min-width='100'>
      <template #default="scope">
        <el-tag v-if="scope.row.status === '执行完成'" type="success">运行完成</el-tag>
        <el-tag v-if="scope.row.status === '等待执行'" type="info">等待运行</el-tag>
        <el-tag v-if="scope.row.status === '运行中'" type="primary">运行中</el-tag>
      </template>
    </el-table-column>
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
    <el-table-column prop="duration" label="执行耗时">
      <template #default="scope">
        <!-- 保留两位小数-->
        {{ scope.row.duration.toFixed(2) }}秒
      </template>
    </el-table-column>
    <el-table-column label="通过率" min-width='100'>
      <template #default="scope">
        {{ (scope.row.pass_rate || 0).toFixed(2) + '%' }}
      </template>
    </el-table-column>
    <el-table-column prop="case_count" label="用例总数"/>
    <el-table-column prop="success" label="成功数"/>
    <el-table-column prop="fail" label="失败数"/>
    <el-table-column prop="error" label="错误数"/>
    <el-table-column prop="skip" label="跳过数"/>
    <el-table-column prop="no_run" label="未运行数"/>
    <el-table-column prop="username" label="执行人"/>
    <el-table-column prop="create_time" label="执行时间" min-width='200'>
      <template #default="scope">
        {{ dateTools.rTime(scope.row.start_time) }}
      </template>
    </el-table-column>
    <el-table-column label="操作" width="200px">
      <template #default="scope">
        <el-button @click="router.push({name: 'suiteReport', params: {id: scope.row.id}})" type="success" plain
                   icon="View">报告
        </el-button>
        <el-tooltip class="box-item" effect="dark" content="将删除套件、用例运行记录" placement="bottom">
          <el-button @click="clickDelete(scope.row.id)" plain type="danger" icon="Delete">删除</el-button>
        </el-tooltip>
      </template>
    </el-table-column>
  </el-table>
  <!-- 分页器-->
  <el-pagination
      :hide-on-single-page="true"
      v-model:current-page="pageConfig.page"
      v-model:page-size="pageConfig.size"
      :page-sizes="[10, 20, 30, 40]"
      layout="total, sizes, prev, pager, next, jumper"
      :total="pageConfig.total"
      @current-change="getRunRecordList"
      @size-change="getRunRecordList"/>
</template>

<script setup>
import {ref, reactive, watch} from 'vue'
import {List} from "@element-plus/icons-vue"
import http from '@/api/index'
import {useRouter} from 'vue-router'
import {ElMessageBox, ElMessage, ElNotification} from 'element-plus'
import dateTools from "@/tools/dateTools.js"

// 定义props
const props = defineProps({
  suite_id: {
    type: Number,
    default: 0
  }
})

const router = useRouter()
// 获取运行记录列表数据
const RunRecordList = ref([])

const pageConfig = reactive({
  suite_id: 0,
  page: 1,
  size: 10,
  total: 0
})

// 获取运行记录数据
const getRunRecordList = async () => {
  pageConfig.suite_id = props.suite_id
  const res = await http.resultApi.getSuiteRecord(pageConfig)
  RunRecordList.value = res.data.data
  pageConfig.total = res.data.total
}

getRunRecordList()

// 侦听器，监听任务id
watch(() => props.suite_id, (newVal, oldVal) => {
  pageConfig.suite_id = newVal
  getRunRecordList()
})

// 删除套件运行记录
const clickDelete = async (record_id) => {
  ElMessageBox.confirm(
      '此操作不可恢复，确定删除该套件运行记录吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const res = await http.resultApi.deleteSuiteRecord(record_id)
        if (res.status === 204) {
          await getRunRecordList()
          ElNotification({
            type: 'success',
            title: '已成功删除套件运行记录！',
            duration: 1500,
          })
        } else {
          ElMessage({
            type: 'error',
            title: '套件运行记录删除失败！',
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