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
    <!--显示索引序号-->
    <el-table-column type="expand">
      <template #default="props">
        <CaseReportTimeline :runInfo="props.row.result_data"/>
      </template>
    </el-table-column>
    <el-table-column label="序号" type="index" width="90"></el-table-column>
    <el-table-column prop="case" label="用例名称" min-width='150' show-overflow-tooltip>
      <template #default="scope">
        {{ scope.row.result_data.name }}
      </template>
    </el-table-column>
    <el-table-column prop="skip" label="是否跳过" min-width='150'>
      <template #default="scope">
        {{ scope.row.result_data.skip ? '是' : '否' }}
      </template>
    </el-table-column>
    <el-table-column prop="status" label="运行结果">
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
    <el-table-column label="浏览器" min-width='90' prop="browser">
      <template #default="scope">
        <el-tag v-if="scope.row.env?.browser === 'chromium'" type="success">谷歌</el-tag>
        <el-tag v-else-if="scope.row.env?.browser === 'firefox'" type="warning">火狐</el-tag>
        <el-tag v-else-if="scope.row.env?.browser === 'webkit'" type="info">Safari</el-tag>
        <span v-else class="text-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="headless" label="运行模式">
      <template #default="scope">
        <el-tag v-if='scope.row.env?.headless === false' type="success">界面模式</el-tag>
        <el-tag v-else-if='scope.row.env?.headless === true' type="primary">无头模式</el-tag>
        <span v-else class="text-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column prop="username" label="运行人" min-width='150'/>
    <el-table-column prop="create_time" label="运行时间" min-width='150'>
      <template #default="scope">
        {{ dateTools.rTime(scope.row.start_time) }}
      </template>
    </el-table-column>
    <el-table-column label="操作" width='220'>
      <template #default="scope">
        <el-button
          v-if="isUiFailed(scope.row.status) && canAiAnalyze"
          plain
          type="warning"
          size="small"
          icon="MagicStick"
          @click="openAiAnalyze(scope.row.id)"
        >AI 分析</el-button>
        <el-button @click="clickDelete(scope.row.id)" plain type="danger" icon="Delete">删除</el-button>
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
  <FailureAnalyzer
    v-model="aiAnalyzeVisible"
    target-type="ui"
    :target-id="aiAnalyzeTargetId"
  />
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { List } from '@element-plus/icons-vue'
import http from '@/api/index'
import CaseReportTimeline from '@/components/Report/CaseReportTimeline.vue'
import FailureAnalyzer from '@/views/AI/components/FailureAnalyzer.vue'
import { ElMessageBox, ElMessage, ElNotification } from 'element-plus'
import dateTools from '@/tools/dateTools.js'
import { fileApi } from '@/api/modules/sys'
import { UserStore } from '@/stores/module/UserStore.js'

const uStore = UserStore()
const canAiAnalyze = computed(() => uStore.hasPermission('ai_test:execute'))
const aiAnalyzeVisible = ref(false)
const aiAnalyzeTargetId = ref(null)

const isUiFailed = (status) => ['fail', 'failed', 'error'].includes(status)

const openAiAnalyze = (recordId) => {
  aiAnalyzeTargetId.value = recordId
  aiAnalyzeVisible.value = true
}

// 定义props
const props = defineProps({
  case_id: {
    type: Number,
    default: 0
  }
})

// 获取运行记录列表数据
const RunRecordList = ref([])

const pageConfig = reactive({
  case_id: 0,
  page: 1,
  size: 10,
  total: 0
})

// 获取运行记录数据
const getRunRecordList = async () => {
  pageConfig.case_id = props.case_id
  const res = await http.resultApi.getCaseRecord(pageConfig)
  
  // 处理每条记录的预签名 URL
  const records = res.data.data || []
  for (const record of records) {
    if (record.result_data) {
      record.result_data = await fileApi.processReportUrls(record.result_data)
    }
  }
  
  RunRecordList.value = records
  pageConfig.total = res.data.total
}

getRunRecordList()

// 侦听器，监听任务id
watch(() => props.case_id, (newVal, oldVal) => {
  pageConfig.case_id = newVal
  getRunRecordList()
})

// 删除用例运行记录
const clickDelete = async (record_id) => {
  ElMessageBox.confirm(
      '此操作不可恢复，确定删除该用例运行记录吗？',
      '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        center: true,
        type: 'warning'
      })
      .then(async () => {
        const res = await http.resultApi.deleteCaseRecord(record_id)
        if (res.status === 204) {
          await getRunRecordList()
          ElNotification({
            type: 'success',
            title: '已成功删除用例运行记录！',
            duration: 1500,
          })
        } else {
          ElNotification({
            type: 'error',
            title: '删除用例运行记录失败！',
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