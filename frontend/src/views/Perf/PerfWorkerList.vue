<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">🖥️ 执行机管理</div>
    </template>
    <template #main>
      <el-alert
        title="分布式压测执行机"
        type="info"
        :closable="false"
        style="margin-bottom: 16px;"
      >
        <template #default>
          <div style="font-size: 13px; line-height: 1.8;">
            <div>
              <strong>推荐</strong>：使用 <strong>BrickCoreRunner v1.3.14+</strong>，登录后默认 UI 执行器；压测时在客户端切换为「仅压测执行机」或「UI + 压测」，选择压测项目后点「上线」。压测引擎与下方脚本相同，报告指标一致。
            </div>
            <div style="margin-top: 8px;">
              执行压测时在场景弹窗勾选「使用分布式 Worker 执行」。客户端「当前会话日志」会实时显示秒级 QPS / RT；完整日志见本机 <code>runner/logs/perf_worker.log</code>。
            </div>
            <div style="margin-top: 12px;">
              <strong>备选：命令行脚本</strong>（<code>--project-id</code> 须与当前项目 <b>{{ proStore.projectInfo?.id || '未选择' }}</b> 一致）：
            </div>
            <pre class="cmd-block">{{ startCommand }}</pre>
          </div>
        </template>
      </el-alert>

      <el-alert
        v-if="projectMismatchHint"
        :title="projectMismatchHint"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 12px;"
      />

      <div class="toolbar">
        <el-button type="primary" @click="fetchData" :icon="Refresh">刷新</el-button>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="节点名称" min-width="120" />
        <el-table-column prop="host" label="IP/主机" width="140" />
        <el-table-column prop="max_concurrent" label="最大并发" width="100" align="center" />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前任务" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.current_record_id" size="small" type="warning">执行中 #{{ row.current_record_id }}</el-tag>
            <span v-else style="color: #999;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="last_heartbeat" label="上次心跳" width="160" />
        <el-table-column prop="create_time" label="注册时间" width="160" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该执行机吗?" @confirm="handleDelete(row)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && tableData.length === 0" description="暂无执行机">
        <template #description>
          <div style="color: #909399;">暂无执行机</div>
          <div style="font-size: 13px; color: #606266; margin-top: 8px;">
            推荐使用 BrickCoreRunner 客户端（压测模式上线），或运行 runner 目录的 perf_worker.py
          </div>
        </template>
      </el-empty>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfWorkerApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { parseWorkerList } from './perfWorkerUtils'

const proStore = ProjectStore()
const loading = ref(false)
const tableData = ref([])
const projectMismatchHint = ref('')

const backendUrl = computed(() => {
  const base = import.meta.env.VITE_BASE_API || ''
  return base.replace(/\/api$/, '')
})

const startCommand = computed(() => {
  const pid = proStore.projectInfo?.id || 1
  return `cd runner\npython -u perf_worker.py --master ${backendUrl.value} --token my-local-token --name "我的电脑" --max-concurrent 200 --project-id ${pid}`
})

const getStatusType = (status) => {
  const map = { online: 'success', idle: 'success', busy: 'warning', offline: 'info' }
  return map[status] || 'info'
}

const getStatusLabel = (status) => {
  const map = { online: '在线', idle: '空闲', busy: '执行中', offline: '离线' }
  return map[status] || status
}

const fetchData = async () => {
  const pid = proStore.projectInfo?.id
  if (!pid) {
    ElMessage.warning('请先在顶部选择项目')
    return
  }
  loading.value = true
  projectMismatchHint.value = ''
  try {
    const res = await perfWorkerApi.getList({ project_id: pid })
    let list = parseWorkerList(res)
    if (!list.length) {
      const resAll = await perfWorkerApi.getList({})
      const all = parseWorkerList(resAll)
      if (all.length) {
        projectMismatchHint.value = `检测到 ${all.length} 个执行机注册在其他项目，请在客户端选择项目 ${pid} 后重新上线`
        list = all
      }
    }
    tableData.value = list
  } catch (err) {
    console.error(err)
    ElMessage.error('获取执行机列表失败')
  } finally {
    loading.value = false
  }
}

const handleDelete = async (row) => {
  try {
    await perfWorkerApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (err) {
    console.error(err)
    ElMessage.error('删除失败')
  }
}

watch(
  () => proStore.projectInfo?.id,
  (id) => {
    if (id) fetchData()
  },
  { immediate: true }
)

onMounted(() => {
  if (proStore.projectInfo?.id) fetchData()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.cmd-block {
  margin: 8px 0 0;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
