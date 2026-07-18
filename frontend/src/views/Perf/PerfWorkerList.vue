<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">🖥️ 执行机管理</div>
    </template>
    <template #main>
      <el-alert
        title="分布式压测执行机（二选一）"
        type="info"
        :closable="false"
        style="margin-bottom: 16px;"
      >
        <template #default>
          <div style="font-size: 13px; line-height: 1.8;">
            <div>
              <strong>方式 A · 完整执行器</strong>：安装 <strong>BrickCoreRunner</strong>，登录后切换为「仅压测执行机」或「UI + 压测」，选择压测项目后点「上线」。
            </div>
            <div style="margin-top: 8px;">
              <strong>方式 B · 精简压测包</strong>：下载 <strong>BrickCorePerf</strong>（Win / Mac 分包），解压后运行 <code>start-perf</code>；终端会记住上次配置，回车启动或按 <code>C</code> 修改。无浏览器 / GUI，适合服务器常驻。
            </div>
            <div style="margin-top: 8px;">
              施压一律由在线执行机完成。上线后本页应出现节点；完整日志见执行机本机工作目录（完整客户端为 <code>runner/logs/</code>，精简包为 <code>engine</code> 目录）。
            </div>
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
        <el-table-column label="来源" min-width="150" align="center">
          <template #default="{ row }">
            <el-tag size="small" class="agent-kind-tag" :type="agentKindTagType(row.agent_kind)">
              {{ agentKindLabel(row.agent_kind) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="engine_version" label="引擎版本" width="100" align="center">
          <template #default="{ row }">
            {{ row.engine_version || '-' }}
          </template>
        </el-table-column>
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
            请用 BrickCoreRunner（压测角色）或 BrickCorePerf 按上方说明上线
          </div>
        </template>
      </el-empty>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfWorkerApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { parseWorkerList, agentKindLabel, agentKindTagType } from './perfWorkerUtils'

const proStore = ProjectStore()
const loading = ref(false)
const tableData = ref([])
const projectMismatchHint = ref('')

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
.agent-kind-tag {
  max-width: none;
  height: auto;
  white-space: nowrap;
  line-height: 1.4;
  padding: 0 8px;
}
</style>
