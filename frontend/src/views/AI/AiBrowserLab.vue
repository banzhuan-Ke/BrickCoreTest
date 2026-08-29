<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <div>
          <b>智能浏览器</b>
          <span class="page-sub">browser-use 自然语言驱动浏览器 · Linux 云部署无头执行，实时截图流展示</span>
        </div>
        <el-button link type="primary" :loading="historyLoading" @click="loadHistory" icon="Refresh">刷新历史</el-button>
      </div>
    </template>
    <template #main>
      <el-alert
        v-if="!projectId"
        type="warning"
        :closable="false"
        show-icon
        title="请先在顶部导航栏选择项目"
        style="margin-bottom: 12px;"
      />

      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <el-card shadow="never" class="panel-card">
            <template #header><span>新建任务</span></template>
            <el-form :model="form" label-width="96px" @submit.prevent>
              <el-form-item label="起始 URL" required>
                <el-input v-model="form.start_url" placeholder="https://example.com" clearable />
              </el-form-item>
              <el-form-item label="任务描述" required>
                <el-input
                  v-model="form.task_text"
                  type="textarea"
                  :rows="4"
                  placeholder="例如：注册一个新账号，用户名 test001，密码 Test@123，完成后停留在个人中心页"
                />
              </el-form-item>
              <el-form-item label="AI 模型">
                <el-select v-model="aiConfigId" placeholder="选择模型" style="width: 100%;" :loading="loadingConfigs">
                  <el-option
                    v-for="c in enabledConfigs"
                    :key="c.id"
                    :label="`${c.name} (${c.model})`"
                    :value="c.id"
                  />
                </el-select>
                <div class="hint">
                  此处下拉框优先；未选时走「场景绑定 → 智能浏览器」。超时取该模型配置或场景「参数覆盖」中的 timeout（须部署最新后端才生效，非固定 180s）
                </div>
              </el-form-item>
              <el-form-item label="最大步数">
                <el-slider v-model="form.max_steps" :min="5" :max="50" show-input />
              </el-form-item>
              <el-form-item label="选项">
                <el-checkbox v-model="form.use_vision">Vision 截图理解</el-checkbox>
                <el-checkbox v-model="form.generate_gif">生成回放 GIF</el-checkbox>
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  :loading="running"
                  :disabled="!canExecute || !form.task_text || !form.start_url"
                  @click="startTask"
                >
                  开始执行
                </el-button>
                <el-button v-if="activeTaskId && isActive" :loading="stopping" @click="stopTask">停止</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card shadow="never" class="panel-card history-card">
            <template #header><span>历史任务</span></template>
            <el-table :data="history" size="small" v-loading="historyLoading" max-height="320" @row-click="viewHistory">
              <el-table-column prop="id" label="#" width="56" />
              <el-table-column prop="status" label="状态" width="80">
                <template #default="{ row }">
                  <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="task_text" label="任务" show-overflow-tooltip />
              <el-table-column prop="steps_count" label="步数" width="56" align="center" />
              <el-table-column prop="create_time" label="时间" width="150">
                <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="14">
          <el-card shadow="never" class="panel-card live-card">
            <template #header>
              <div class="live-header">
                <span>实时执行</span>
                <span v-if="activeTaskId" class="live-meta">任务 #{{ activeTaskId }} · {{ statusLabel(liveStatus) }}</span>
              </div>
            </template>

            <div class="screenshot-wrap">
              <img v-if="currentScreenshotUrl" :src="currentScreenshotUrl" alt="当前截图" class="screenshot-img" />
              <el-empty v-else description="执行后将在此显示最新截图（云服务器无头模式）" :image-size="80" />
            </div>

            <div v-if="liveSummary" class="result-box">
              <div class="result-title">执行结果</div>
              <div class="result-text">{{ liveSummary }}</div>
              <div v-if="gifUrl" class="gif-row">
                <a :href="gifUrl" target="_blank" rel="noopener">查看回放 GIF</a>
              </div>
            </div>

            <div v-if="liveHint" class="live-hint">{{ liveHint }}</div>
            <div class="log-wrap">
              <div v-for="(item, idx) in displaySteps" :key="`${item.index}-${idx}`" class="log-item">
                <div class="log-head">
                  <span class="log-step">{{ stepLabel(item) }}</span>
                  <span class="log-url">{{ item.url }}</span>
                </div>
                <div v-if="item.next_goal" class="log-goal">{{ item.next_goal }}</div>
                <div v-if="item.thinking && item.step_status !== 'ok'" class="log-think">{{ item.thinking }}</div>
              </div>
              <el-empty v-if="!displaySteps.length && !running" description="暂无执行日志" :image-size="48" />
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { browserLabApi } from '@/api/modules/ai.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import { useBrowserLabTaskPoll } from '@/composables/useBrowserLabTaskPoll.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import {
  browserLabLiveHint,
  browserLabStepLabel,
  normalizeBrowserLabSteps,
} from './browserLab/browserLabStepLog.js'

const pStore = ProjectStore()
const uStore = UserStore()
const projectId = computed(() => pStore.projectInfo?.id)
const canExecute = computed(() => uStore.hasPermission('ai_test:execute'))

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect({ scene: 'browser_lab' })

const form = ref({
  start_url: '',
  task_text: '',
  max_steps: 25,
  use_vision: true,
  generate_gif: true
})

const running = ref(false)
const stopping = ref(false)
const historyLoading = ref(false)
const history = ref([])
const activeTaskId = ref(null)
const liveStatus = ref('pending')
const liveSummary = ref('')
const gifUrl = ref('')
const stepLogs = ref([])
const displaySteps = computed(() => normalizeBrowserLabSteps(stepLogs.value))
const liveHint = computed(() =>
  browserLabLiveHint(stepLogs.value, { running: running.value, status: liveStatus.value })
)
const stepLabel = browserLabStepLabel
const taskPoll = useBrowserLabTaskPoll()
const currentScreenshotUrl = ref('')
const screenshotObjectUrls = ref([])

const isActive = computed(() => ['pending', 'running'].includes(liveStatus.value))

function statusLabel(s) {
  const map = { pending: '等待', running: '执行中', done: '完成', failed: '失败', stopped: '已停止' }
  return map[s] || s
}

function statusTag(s) {
  const map = { done: 'success', running: 'warning', failed: 'danger', stopped: 'info' }
  return map[s] || 'info'
}

function formatTime(t) {
  if (!t) return '-'
  return String(t).replace('T', ' ').slice(0, 19)
}

function assetUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  const origin = (import.meta.env.VITE_BASE_API || window.location.origin).replace(/\/$/, '')
  return path.startsWith('/') ? `${origin}${path}` : `${origin}/${path}`
}

function revokeScreenshots() {
  screenshotObjectUrls.value.forEach((u) => URL.revokeObjectURL(u))
  screenshotObjectUrls.value = []
}

async function loadScreenshot(taskId, filename, directUrl) {
  if (directUrl) {
    currentScreenshotUrl.value = directUrl
    return
  }
  if (!filename || !projectId.value) return
  try {
    const blob = await browserLabApi.fetchScreenshotBlob(taskId, filename, projectId.value)
    const url = URL.createObjectURL(blob)
    screenshotObjectUrls.value.push(url)
    currentScreenshotUrl.value = url
  } catch (e) {
    console.warn('截图加载失败', e)
  }
}

function handleStreamEvent(data) {
  if (data.type === 'step') {
    stepLogs.value.push(data)
    if (data.screenshot_url) {
      currentScreenshotUrl.value = data.screenshot_url
    } else if (data.screenshot_file && activeTaskId.value) {
      loadScreenshot(activeTaskId.value, data.screenshot_file)
    }
  } else if (data.type === 'done') {
    liveStatus.value = data.status || 'done'
    liveSummary.value = data.error_message || data.summary || ''
    if (data.gif_url) gifUrl.value = assetUrl(data.gif_url)
    if (!gifUrl.value && data.gif_path) gifUrl.value = assetUrl(`/static/${data.gif_path}`)
    running.value = false
    loadHistory()
  } else if (data.type === 'error') {
    liveStatus.value = 'failed'
    liveSummary.value = data.message || '执行失败'
    running.value = false
  }
}

function subscribeTask(taskId) {
  taskPoll.start(taskId, projectId.value, {
    onDone: (data) => handleStreamEvent({ ...data, type: 'done' }),
    onFail: (payload) => handleStreamEvent({ type: 'error', message: payload.error_message }),
  })
}

watch(taskPoll.displayedSteps, (steps) => {
  stepLogs.value = steps
  if (activeTaskId.value) {
    const last = [...steps].reverse().find((s) => s.screenshot_url || s.screenshot_file)
    if (last?.screenshot_url) {
      currentScreenshotUrl.value = last.screenshot_url
    } else if (last?.screenshot_file) loadScreenshot(activeTaskId.value, last.screenshot_file)
  }
}, { deep: true })

watch(
  () => taskPoll.taskData.value,
  (task) => {
    if (!task) return
    liveStatus.value = task.status || liveStatus.value
    if (task.result_summary && ['done', 'failed', 'stopped'].includes(task.status)) {
      liveSummary.value = task.error_message || task.result_summary || liveSummary.value
      running.value = false
    }
  },
  { deep: true }
)

async function startTask() {
  if (!projectId.value) {
    ElMessage.warning('请先在顶部导航栏选择项目')
    return
  }
  if (!canExecute.value) {
    ElMessage.warning('需要 ai_test:execute 权限才能创建任务')
    return
  }
  revokeScreenshots()
  stepLogs.value = []
  liveSummary.value = ''
  gifUrl.value = ''
  currentScreenshotUrl.value = ''
  liveStatus.value = 'running'
  running.value = true

  try {
    const res = await browserLabApi.createTask({
      ...form.value,
      ai_config_id: aiConfigId.value || null
    }, projectId.value)
    if (res.data?.code !== 200) {
      throw new Error(res.data?.message || '创建失败')
    }
    const task = res.data.data
    activeTaskId.value = task.id
    liveStatus.value = task.status
    subscribeTask(task.id)
    loadHistory()
  } catch (e) {
    running.value = false
    liveStatus.value = 'failed'
    const msg = e?.response?.data?.detail || e?.response?.data?.message || e.message || String(e)
    liveSummary.value = msg
    ElMessage.error(msg)
  }
}

async function stopTask() {
  if (!activeTaskId.value) return
  stopping.value = true
  try {
    const res = await browserLabApi.stopTask(activeTaskId.value, projectId.value)
    if (res.data?.code === 200) {
      liveStatus.value = 'stopped'
      liveSummary.value = '用户已停止'
      running.value = false
      ElMessage.success('任务已停止')
      loadHistory()
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.response?.data?.message || e.message || '停止失败'
    ElMessage.error(msg)
  } finally {
    stopping.value = false
  }
}

async function loadHistory() {
  if (!projectId.value) return
  historyLoading.value = true
  try {
    const res = await browserLabApi.listTasks(projectId.value, { page: 1, size: 20 })
    if (res.data?.code === 200) {
      history.value = res.data.data?.list || []
    }
  } finally {
    historyLoading.value = false
  }
}

async function viewHistory(row) {
  if (!row?.id) return
  revokeScreenshots()
  stepLogs.value = []
  liveSummary.value = row.result_summary || ''
  gifUrl.value = assetUrl(row.gif_url || (row.gif_path ? `/static/${row.gif_path}` : ''))
  activeTaskId.value = row.id
  liveStatus.value = row.status
  running.value = ['pending', 'running'].includes(row.status)

  const res = await browserLabApi.getTask(row.id, projectId.value)
  if (res.data?.code === 200) {
    const task = res.data.data
    if (running.value) {
      subscribeTask(row.id)
    } else {
      stepLogs.value = (task.step_log || []).filter((e) => e.type === 'step')
      const lastShot = [...stepLogs.value].reverse().find((s) => s.screenshot_file)
      if (lastShot) await loadScreenshot(row.id, lastShot.screenshot_file)
    }
  }
}

onMounted(() => {
  loadConfigs()
  loadHistory()
})

onBeforeUnmount(() => {
  taskPoll.stop()
  revokeScreenshots()
})
</script>

<style scoped>
.page-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.page-sub {
  display: block;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.panel-card {
  margin-bottom: 16px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.live-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.live-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.screenshot-wrap {
  min-height: 240px;
  background: #0f172a;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
  overflow: hidden;
}
.screenshot-img {
  max-width: 100%;
  max-height: 420px;
  object-fit: contain;
}
.log-wrap {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 12px;
}
.log-item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.log-item:last-child {
  border-bottom: none;
}
.log-head {
  display: flex;
  gap: 8px;
  font-size: 12px;
}
.log-step {
  font-weight: 600;
  color: var(--el-color-primary);
}
.log-url {
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-goal {
  margin-top: 4px;
  font-size: 13px;
}
.log-think {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.result-box {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.result-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.result-text {
  white-space: pre-wrap;
  font-size: 13px;
}
.gif-row {
  margin-top: 8px;
}
</style>
