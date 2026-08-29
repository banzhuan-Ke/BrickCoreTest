<template>
  <PageCard>
    <template #title>
      <b>推送记录</b>
    </template>
    <template #main>
      <!-- 筛选栏 -->
      <div style="margin-bottom: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
        <el-select v-model="filter.project_id" placeholder="选择项目" clearable style="width: 160px;">
          <el-option v-for="item in projectList" :key="item.id" :label="item.name" :value="item.id"/>
        </el-select>
        <el-select v-model="filter.channel_type" placeholder="通知渠道" clearable style="width: 120px;">
          <el-option label="邮件" value="email"/>
          <el-option label="钉钉" value="dingtalk"/>
          <el-option label="企微" value="wechat"/>
          <el-option label="飞书" value="feishu"/>
        </el-select>
        <el-select v-model="filter.notify_type" placeholder="通知类型" clearable style="width: 140px;">
          <el-option label="告警" value="alert"/>
          <el-option label="报告" value="report"/>
          <el-option label="指派" value="assignment"/>
          <el-option label="公告" value="notice"/>
          <el-option label="SMTP 测试" value="smtp_test"/>
        </el-select>
        <el-select v-model="filter.status" placeholder="推送状态" clearable style="width: 120px;">
          <el-option label="成功" value="success"/>
          <el-option label="跳过" value="skipped"/>
          <el-option label="失败" value="failed"/>
        </el-select>
        <el-button type="primary" @click="getLogList" icon="Search">查询</el-button>
        <el-button type="danger" @click="handleBatchDelete" :disabled="selectedIds.length === 0" icon="Delete">批量删除</el-button>
      </div>

      <el-table :data="logList" style="width: 100%" stripe v-loading="loading"
                @selection-change="handleSelectionChange"
                :header-cell-style="{'text-align':'center'}"
                :cell-style="{'text-align':'center'}">
        <el-table-column type="selection" width="55"/>
        <el-table-column label="时间" prop="create_time" width="160"/>
        <el-table-column label="项目" width="140">
          <template #default="scope">
            {{ scope.row.project_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.notify_type === 'alert'" type="danger">告警</el-tag>
            <el-tag v-else-if="scope.row.notify_type === 'report'" type="primary">报告</el-tag>
            <el-tag v-else-if="scope.row.notify_type === 'assignment'" type="warning">指派</el-tag>
            <el-tag v-else-if="scope.row.notify_type === 'notice'" type="success">公告</el-tag>
            <el-tag v-else-if="scope.row.notify_type === 'smtp_test'" type="info">SMTP 测试</el-tag>
            <span v-else>{{ scope.row.notify_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="渠道" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.channel_type === 'email'" type="primary">邮件</el-tag>
            <el-tag v-else-if="scope.row.channel_type === 'dingtalk'" type="warning">钉钉</el-tag>
            <el-tag v-else-if="scope.row.channel_type === 'wechat'" type="success">企微</el-tag>
            <el-tag v-else-if="scope.row.channel_type === 'feishu'" type="info">飞书</el-tag>
            <span v-else>{{ scope.row.channel_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="标题" prop="title" min-width="180" show-overflow-tooltip/>
        <el-table-column label="接收人" min-width="140" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.channel_type === 'email'">
              {{ formatRecipients(scope.row.recipients) }}
            </span>
            <span v-else>{{ scope.row.recipients?.[0] || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag v-if="scope.row.status === 'success'" type="success">成功</el-tag>
            <el-tag v-else-if="scope.row.status === 'skipped'" type="info">跳过</el-tag>
            <el-tag v-else-if="scope.row.error_msg && /跳过|未配置|免打扰|偏好|未开启测试指派/.test(scope.row.error_msg)" type="info">跳过</el-tag>
            <el-tag v-else type="danger">失败</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="错误信息" prop="error_msg" min-width="160" show-overflow-tooltip/>
      </el-table>

      <div style="margin-top: 15px; display: flex; justify-content: flex-end;">
        <el-pagination
          v-model:current-page="filter.page"
          v-model:page-size="filter.size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="getLogList"
          @current-change="getLogList"
        />
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/api/index'
import PageCard from "@/components/PageCard.vue"

const projectList = ref([])
const logList = ref([])
const total = ref(0)
const loading = ref(false)
const selectedIds = ref([])

const filter = reactive({
  project_id: null,
  channel_type: '',
  notify_type: '',
  status: '',
  page: 1,
  size: 10
})

onMounted(() => {
  getProjectList()
  getLogList()
})

const getProjectList = async () => {
  const res = await http.projectApi.getProjectList({ page: 1, size: 1000 })
  if (res.status === 200) {
    projectList.value = res.data.data || []
  }
}

const getLogList = async () => {
  loading.value = true
  try {
    const params = { page: filter.page, size: filter.size }
    if (filter.project_id) params.project_id = filter.project_id
    if (filter.channel_type) params.channel_type = filter.channel_type
    if (filter.notify_type) params.notify_type = filter.notify_type
    if (filter.status) params.status = filter.status
    const res = await http.notificationApi.getLogList(params)
    if (res.status === 200) {
      logList.value = res.data.data || []
      total.value = res.data.total || 0
    }
  } finally {
    loading.value = false
  }
}

const handleSelectionChange = (selection) => {
  selectedIds.value = selection.map(item => item.id)
}

const formatRecipients = (list) => {
  if (!list || !list.length) return '-'
  return list.join('、')
}

const handleBatchDelete = () => {
  ElMessageBox.confirm('确定要删除选中的推送记录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    const res = await http.notificationApi.batchDeleteLogs(selectedIds.value)
    if (res.status === 204) {
      ElMessage.success('删除成功')
      getLogList()
    }
  }).catch(() => {})
}
</script>
