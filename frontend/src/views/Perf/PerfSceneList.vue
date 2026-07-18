<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">🚀 性能测试场景</div>
    </template>
    <template #main>
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索场景名称"
          clearable
          style="width: 240px"
          @keyup.enter="fetchData"
        />
        <el-button type="primary" @click="fetchData" :icon="Search">搜索</el-button>
        <el-button
          v-permission="'perf_scene:edit'"
          type="success"
          @click="handleAdd"
          :icon="Plus"
        >新建场景</el-button>
      </div>

      <!-- 表格 -->
      <div style="overflow-x: auto; width: 100%;">
        <el-table :data="tableData" v-loading="loading" stripe style="min-width: 1200px;">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="场景名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="120" show-overflow-tooltip />
        <el-table-column label="模式" width="90" align="center">
          <template #default="{ row }">
            <div class="mode-cell">
              <el-tag size="small" :type="getModeType(row.config?.mode)">
                {{ getModeLabel(row.config?.mode) }}
              </el-tag>
              <el-tag size="small" :type="row.config?.distribution_mode === 'fixed_ratio' ? 'success' : 'info'" style="margin-top: 2px;">
                {{ row.config?.distribution_mode === 'fixed_ratio' ? '固定' : '随机' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="case_count" label="用例数" width="80" align="center" />
        <el-table-column label="并发数" width="80" align="center">
          <template #default="{ row }">
            {{ row.config?.concurrent_users || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Ramp-up" width="90" align="center">
          <template #default="{ row }">
            {{ row.config?.ramp_up_seconds !== undefined ? row.config.ramp_up_seconds + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="持续时间" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.config?.mode === 'fixed'">
              {{ row.config?.duration_seconds ? row.config.duration_seconds + 's' : '-' }}
            </span>
            <span v-else-if="row.config?.mode === 'loop'">
              {{ row.config?.loop_count ? row.config.loop_count + '次' : '-' }}
            </span>
            <span v-else-if="row.config?.mode === 'stepping'">
              {{ row.config?.steps ? row.config.steps.length + '阶段' : '-' }}
            </span>
            <span v-else-if="row.config?.mode === 'stream_burst' || row.config?.mode === 'sse_burst'">
              {{ row.config?.concurrent_users ? row.config.concurrent_users + '并发×1次' : '-' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="create_by" label="创建人" width="100" />
        <el-table-column prop="create_time" label="创建时间" width="160" />
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button
                v-permission="'perf_scene:execute'"
                type="primary"
                size="small"
                :icon="VideoPlay"
                @click="handleRun(row)"
              >执行</el-button>
              <el-button
                v-permission="'perf_scene:edit'"
                type="info"
                size="small"
                :icon="CopyDocument"
                @click="handleClone(row)"
              >复制</el-button>
              <el-button
                v-permission="'perf_scene:edit'"
                type="warning"
                size="small"
                :icon="Edit"
                @click="handleEdit(row)"
              >编辑</el-button>
              <el-button
                v-permission="'perf_scene:edit'"
                type="danger"
                size="small"
                :icon="Delete"
                @click="handleDelete(row)"
              >删除</el-button>
            </div>
          </template>
        </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>

      <!-- 执行对话框 -->
      <el-dialog v-model="runDialogVisible" title="启动性能测试" width="580px">
        <el-form :model="runForm" label-width="90px">
          <el-form-item label="场景">
            <el-input v-model="runForm.sceneName" disabled />
          </el-form-item>
          <el-form-item label="环境" required>
            <el-select v-model="runForm.envId" placeholder="选择执行环境" style="width: 100%">
              <el-option
                v-for="env in envList"
                :key="env.id"
                :label="env.name"
                :value="env.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="配置">
            <div class="config-preview">
              <div class="config-row">
                <span>并发用户: {{ runForm.config?.concurrent_users }}</span>
                <el-tooltip placement="top" content="同时发起请求的虚拟用户数">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="config-row">
                <span>Ramp-up: {{ runForm.config?.ramp_up_seconds }}s</span>
                <el-tooltip placement="top" content="从0用户到目标并发数的渐进加压时间，0表示立即加压">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="config-row">
                <span v-if="runForm.config?.mode === 'fixed'">持续时间: {{ runForm.config?.duration_seconds }}s</span>
                <span v-else-if="runForm.config?.mode === 'loop'">循环次数: {{ runForm.config?.loop_count }}次</span>
                <span v-else-if="runForm.config?.mode === 'stepping'">梯度阶段: {{ runForm.config?.steps?.length || 0 }}个</span>
                <span v-else-if="runForm.config?.mode === 'stream_burst' || runForm.config?.mode === 'sse_burst'">并发单次: {{ runForm.config?.concurrent_users }}用户×1次</span>
                <el-tooltip placement="top" :content="getDurationTip(runForm.config)">
                  <el-icon class="tip-icon"><QuestionFilled /></el-icon>
                </el-tooltip>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="接口明细">
            <el-radio-group v-model="runForm.requestDetailLevel" class="detail-level-group">
              <el-radio value="brief">简略（失败含详情）</el-radio>
              <el-radio value="full">详细（含成功请求）</el-radio>
            </el-radio-group>
            <div class="detail-level-hint">
              <strong>不影响 QPS、平均/P95 响应时间、错误率等汇总数据</strong>——请求发出与 RT 计时逻辑与简略模式完全相同，仅在请求结束后额外记录接口信息供报告排查。
              失败请求两种模式均保留最多 50 条详情；详细模式另采集最多 500 条成功请求。高并发时可能略增内存与收尾耗时，不改变已测得的性能指标。
            </div>
          </el-form-item>
          <el-form-item label="执行器">
            <div style="width: 100%;">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="压测施压由在线 Worker 执行（后端不再本机直跑）"
                style="margin-bottom: 10px;"
              />
              <el-alert
                v-if="workerList.length === 0"
                type="warning"
                :closable="false"
                show-icon
              >
                <template #title>暂无在线执行机，无法启动</template>
                <template #default>
                  <div style="font-size: 12px; line-height: 1.6;">
                    任选其一：<strong>BrickCoreRunner</strong>（压测角色上线），或精简包 <strong>BrickCorePerf</strong>；开发可用 <code>runner/perf_worker.py</code>。
                    项目 ID 须与当前项目（{{ proStore.projectInfo?.id }}）一致。
                  </div>
                </template>
              </el-alert>
              <el-alert
                v-else
                :title="`当前在线 ${workerList.length} 个执行机，总并发能力 ${workerTotalConcurrent} 用户`"
                type="success"
                :closable="false"
                show-icon
              />
              <div v-if="workerList.length > 0" style="margin-top: 8px; font-size: 12px; color: #606266;">
                <div v-for="w in workerList" :key="w.id" style="display: flex; justify-content: space-between; gap: 12px; padding: 2px 0;">
                  <span>{{ w.name }} ({{ w.host }}) · {{ agentKindShort(w.agent_kind) }}</span>
                  <span>并发: {{ w.max_concurrent }}</span>
                </div>
              </div>
            </div>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="runDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmRun" :loading="runLoading">确认执行</el-button>
        </template>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Plus, Edit, Delete, VideoPlay, QuestionFilled, CopyDocument } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { perfSceneApi, perfExecApi, perfWorkerApi } from '@/api'
import { parseWorkerList, filterOnlineWorkers, agentKindShort } from './perfWorkerUtils'
import { envApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const loading = ref(false)
const tableData = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const searchKeyword = ref('')

const runDialogVisible = ref(false)
const runLoading = ref(false)
const runForm = ref({ sceneId: null, sceneName: '', envId: null, config: {}, useWorkers: false, requestDetailLevel: 'brief' })
const workerList = ref([])
const workerTotalConcurrent = computed(() => workerList.value.reduce((sum, w) => sum + (w.max_concurrent || 0), 0))
const envList = ref([])

const getModeType = (mode) => {
  const map = { fixed: 'primary', loop: 'success', stepping: 'warning', stream_burst: 'danger', sse_burst: 'danger' }
  return map[mode] || ''
}

const getModeLabel = (mode) => {
  const map = { fixed: '固定', loop: '循环', stepping: '梯度', stream_burst: '流式阶段', sse_burst: '流式阶段' }
  return map[mode] || mode
}

const fetchData = async () => {
  if (!proStore.projectInfo?.id) return
  loading.value = true
  try {
    const res = await perfSceneApi.getList({
      project_id: proStore.projectInfo.id,
      keyword: searchKeyword.value || undefined,
      page: page.value,
      size: size.value
    })
    const data = res.data || res
    tableData.value = data.data || []
    total.value = data.total || 0
  } catch (err) {
    console.error(err)
    ElMessage.error('获取场景列表失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = () => {
  router.push('/perf-scene/add')
}

const handleEdit = (row) => {
  router.push(`/perf-scene/edit/${row.id}`)
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除场景 "${row.name}" 吗？`, '提示', { type: 'warning' })
    await perfSceneApi.delete(row.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleClone = async (row) => {
  try {
    await perfSceneApi.clone(row.id)
    ElMessage.success('复制成功')
    fetchData()
  } catch (err) {
    console.error(err)
    ElMessage.error('复制失败')
  }
}

const handleRun = async (row) => {
  runForm.value = {
    sceneId: row.id,
    sceneName: row.name,
    envId: null,
    config: row.config || {},
    useWorkers: true,
    requestDetailLevel: 'brief'
  }
  // 加载环境列表
  try {
    const res = await envApi.getEnvList({ project_id: proStore.projectInfo.id })
    envList.value = res.data || res || []
  } catch (e) {
    console.error(e)
  }
  // 加载 Worker 列表
  try {
    const res = await perfWorkerApi.getList({ project_id: proStore.projectInfo.id })
    workerList.value = filterOnlineWorkers(parseWorkerList(res))
  } catch (e) {
    console.error(e)
    workerList.value = []
  }
  runDialogVisible.value = true
}

const getDurationTip = (config) => {
  const mode = config?.mode || 'fixed'
  const tips = {
    fixed: '压测持续的总时长',
    loop: '每个并发用户执行的总次数',
    stepping: '分阶段递增并发的阶段数',
    stream_burst: '每个虚拟用户只发送 1 次流式请求',
    sse_burst: '每个虚拟用户只发送 1 次流式请求'
  }
  return tips[mode] || ''
}

const confirmRun = async () => {
  if (!runForm.value.envId) {
    ElMessage.warning('请选择执行环境')
    return
  }
  if (!workerList.value.length) {
    ElMessage.warning('暂无在线压测 Worker，请先上线执行器')
    return
  }
  runLoading.value = true
  try {
    const res = await perfExecApi.start(
      runForm.value.sceneId,
      runForm.value.envId,
      true,
      runForm.value.requestDetailLevel
    )
    ElMessage.success('性能测试已启动')
    runDialogVisible.value = false
    // 跳转到记录页
    router.push('/perf-records')
  } catch (err) {
    console.error(err)
    ElMessage.error('启动失败')
  } finally {
    runLoading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.config-preview {
  background: #f5f7fa;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  color: #666;
}
.config-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0;
}
.tip-icon {
  color: #909399;
  cursor: pointer;
  font-size: 14px;
}
.tip-icon:hover {
  color: #409eff;
}
.op-btns {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
}
.detail-level-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}
.detail-level-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.65;
  max-width: 100%;
}
</style>
