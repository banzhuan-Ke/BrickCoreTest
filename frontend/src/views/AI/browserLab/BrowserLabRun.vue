<template>
  <div>
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
          <template #header>
            <div class="card-head">
              <span>{{ caseName ? `执行用例：${caseName}` : '新建执行' }}</span>
              <el-button v-if="caseId" link type="primary" @click="clearCase">切换为自由执行</el-button>
            </div>
          </template>
          <el-form :model="form" label-width="96px" @submit.prevent>
            <el-form-item label="起始 URL" required>
              <div class="param-input-row">
                <el-input v-model="form.start_url" placeholder="https://example.com" clearable />
                <VarInsertButton :env-id="numericRunEnvId" label="变量" />
              </div>
            </el-form-item>
            <BrowserLabTaskTextField
              v-model="form.task_text"
              required
              :start-url="form.start_url"
              :case-name="caseName"
              :ai-config-id="aiConfigId"
              :project-id="projectId"
              :env-id="form.env_id"
            />
            <el-form-item label="AI 模型">
              <el-select v-model="aiConfigId" placeholder="选择模型" style="width: 100%;" :loading="loadingConfigs">
                <el-option v-for="c in enabledConfigs" :key="c.id" :label="`${c.name} (${c.model})`" :value="c.id" />
              </el-select>
            </el-form-item>
            <BrowserLabExecOptionsFields :form="form" />
            <el-form-item>
              <el-button type="primary" :loading="running" :disabled="!canExecute || !form.task_text || !form.start_url" @click="startTask">
                开始执行
              </el-button>
              <el-button v-if="activeTaskId && isActive" :loading="stopping" @click="stopTask">停止</el-button>
              <el-button v-if="canExecute && !caseId" @click="openSaveCase">保存为用例</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="panel-card live-card">
          <template #header>
            <div class="live-header">
              <span>实时执行</span>
              <span v-if="activeTaskId" class="live-meta">
                任务 #{{ activeTaskId }} · {{ statusLabel(liveStatus) }}
                <el-button v-if="!isActive && activeTaskId" link type="primary" @click="goReport(activeTaskId)">查看报告</el-button>
              </span>
            </div>
          </template>
          <div class="screenshot-wrap">
            <img v-if="currentScreenshotUrl" :src="currentScreenshotUrl" alt="当前截图" class="screenshot-img" />
            <el-empty v-else description="执行后将在此显示最新截图" :image-size="80" />
          </div>
          <div v-if="liveSummary" class="result-box">
            <div class="result-title">执行结果</div>
            <div v-if="liveTokens" class="result-tokens">Token 消耗：{{ liveTokens }}</div>
            <div class="result-text">{{ liveSummary }}</div>
            <div v-if="gifPreviewHref" class="gif-row">
              <a :href="gifPreviewHref" target="_blank" rel="noopener">查看回放 GIF</a>
            </div>
          </div>
          <div v-if="liveHint" class="live-hint">{{ liveHint }}</div>
          <div class="log-wrap">
            <div v-for="(item, idx) in displaySteps" :key="`${item.index}-${idx}`" class="log-item">
              <div class="log-head">
                <span class="log-step">{{ stepLabel(item) }}</span>
                <el-tag v-if="item.step_status === 'failed'" size="small" type="danger">重试/跳过</el-tag>
                <el-tag v-else-if="item.step_status === 'recovered'" size="small" type="warning">已补齐</el-tag>
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

    <el-dialog v-model="saveDialog.visible" title="保存为用例" width="520px" destroy-on-close>
      <el-form :model="saveDialog.form" label-width="88px">
        <el-form-item label="用例名称" required>
          <el-input v-model="saveDialog.form.name" placeholder="便于识别的名称" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="saveDialog.form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="saveDialog.form.tags" placeholder="逗号分隔，如：登录,知识库" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="saveDialog.saving" @click="confirmSaveCase">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { browserLabApi } from '@/api/modules/ai.js'
import { browserLabGifPreviewHref } from './browserLabGif.js'
import BrowserLabExecOptionsFields from './BrowserLabExecOptionsFields.vue'
import BrowserLabTaskTextField from './BrowserLabTaskTextField.vue'
import { mergeBrowserLabExecForm, browserLabExecConfigPayload } from './browserLabExecOptions.js'
import { buildExecConfirmContext } from './browserLabExecConfirmHelpers.js'
import { openBrowserLabExecConfirm } from '@/composables/useBrowserLabExecConfirm.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import { useBrowserLabTaskPoll } from '@/composables/useBrowserLabTaskPoll.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import VarInsertButton from '@/components/VarInsertButton.vue'
import {
  browserLabLiveHint,
  browserLabStepLabel,
  normalizeBrowserLabSteps,
} from './browserLabStepLog.js'

const route = useRoute()
const router = useRouter()
const pStore = ProjectStore()
const uStore = UserStore()
const projectId = computed(() => pStore.projectInfo?.id)
const canExecute = computed(() => uStore.hasPermission('ai_test:execute'))

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect({ scene: 'browser_lab' })

const caseId = ref(null)
const caseName = ref('')
const form = ref({
  start_url: '',
  task_text: '',
  ...mergeBrowserLabExecForm()
})
const running = ref(false)
const stopping = ref(false)
const activeTaskId = ref(null)
const liveStatus = ref('pending')
const liveSummary = ref('')
const liveTokens = ref(0)
const hasGif = ref(false)
const gifPreviewHref = computed(() =>
  hasGif.value && activeTaskId.value
    ? browserLabGifPreviewHref(activeTaskId.value, projectId.value)
    : ''
)
const stepLogs = ref([])
const displaySteps = computed(() => normalizeBrowserLabSteps(stepLogs.value))
const liveHint = computed(() =>
  browserLabLiveHint(stepLogs.value, { running: running.value, status: liveStatus.value })
)
const stepLabel = browserLabStepLabel
const taskPoll = useBrowserLabTaskPoll()
const currentScreenshotUrl = ref('')
const screenshotObjectUrls = ref([])
const saveDialog = ref({ visible: false, saving: false, form: { name: '', description: '', tags: '' } })

const isActive = computed(() => ['pending', 'running'].includes(liveStatus.value))
const numericRunEnvId = computed(() => {
  const n = Number(form.value.env_id)
  return Number.isFinite(n) && n > 0 ? n : null
})

function statusLabel(s) {
  const map = { pending: '等待', running: '执行中', done: '完成', failed: '失败', stopped: '已停止' }
  return map[s] || s
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
    liveTokens.value = Number(data.tokens_used || 0)
    hasGif.value = Boolean(data.gif_url || data.gif_path)
    running.value = false
    if (!hasGif.value && activeTaskId.value && form.value.generate_gif !== false) {
      syncGifFromTask(activeTaskId.value)
    }
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
  if (!activeTaskId.value || !steps?.length) return
  const last = [...steps].reverse().find((s) => s.screenshot_url || s.screenshot_file)
  if (!last) return
  if (last.screenshot_url) {
    currentScreenshotUrl.value = last.screenshot_url
  } else if (last.screenshot_file) {
    loadScreenshot(activeTaskId.value, last.screenshot_file, last.screenshot_url)
  }
}, { deep: true })

watch(
  () => taskPoll.taskStatus.value,
  (status) => {
    if (status) liveStatus.value = status
  }
)

watch(
  () => taskPoll.taskData.value,
  (task) => {
    if (!task) return
    liveStatus.value = task.status || liveStatus.value
    if (task.result_summary && ['done', 'failed', 'stopped'].includes(task.status)) {
      liveSummary.value = task.error_message || task.result_summary || liveSummary.value
      liveTokens.value = Number(task.tokens_used || liveTokens.value)
      hasGif.value = Boolean(task.gif_url || task.gif_path || hasGif.value)
      running.value = false
    }
  },
  { deep: true }
)

async function syncGifFromTask(taskId) {
  if (!projectId.value) return
  try {
    const res = await browserLabApi.getTask(taskId, projectId.value)
    if (res.data?.code === 200) {
      hasGif.value = Boolean(res.data.data?.gif_url || res.data.data?.gif_path)
    }
  } catch {
    /* ignore */
  }
}

async function startTask(execOverride = null) {
  if (!projectId.value) return ElMessage.warning('请先选择项目')
  if (!canExecute.value) return ElMessage.warning('需要 ai_test:execute 权限')

  let execForm = execOverride?.execForm || { ...form.value }
  if (!execOverride) {
    const ctx = buildExecConfirmContext({
      title: caseName.value ? `确认执行：${caseName.value}` : '确认执行',
      name: caseName.value || '',
      source: { ...form.value, ai_config_id: aiConfigId.value },
      aiConfigs: enabledConfigs.value,
      caseId: caseId.value,
    })
    let confirmed
    try {
      confirmed = await openBrowserLabExecConfirm(ctx)
    } catch {
      return ElMessage.warning('执行确认弹窗未就绪，请刷新页面后重试')
    }
    if (!confirmed) return
    execForm = confirmed.execForm
    form.value.device_id = confirmed.device_id
    form.value.headless = confirmed.execForm?.headless !== false
  } else if (execOverride.execForm) {
    execForm = execOverride.execForm
    form.value.device_id = execOverride.device_id
    form.value.headless = execOverride.execForm.headless !== false
  }

  revokeScreenshots()
  stepLogs.value = []
  liveSummary.value = ''
  liveTokens.value = 0
  hasGif.value = false
  currentScreenshotUrl.value = ''
  liveStatus.value = 'running'
  running.value = true
  try {
    const payload = {
      start_url: form.value.start_url,
      task_text: form.value.task_text,
      ai_config_id: aiConfigId.value || null,
      case_id: caseId.value || null,
      ...browserLabExecConfigPayload(execForm),
    }
    const res = await browserLabApi.createTask(payload, projectId.value)
    if (res.data?.code !== 200) throw new Error(res.data?.message || '创建失败')
    const task = res.data.data
    activeTaskId.value = task.id
    liveStatus.value = task.status
    subscribeTask(task.id)
    router.replace({ path: '/browser-lab/run', query: { taskId: task.id } })
  } catch (e) {
    running.value = false
    liveStatus.value = 'failed'
    ElMessage.error(e?.response?.data?.detail || e?.response?.data?.message || e.message)
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
    }
  } finally {
    stopping.value = false
  }
}

function goReport(taskId) {
  router.push({ name: 'browserLabReport', params: { taskId } })
}

function openSaveCase() {
  saveDialog.value.form = {
    name: form.value.task_text.slice(0, 40) || '未命名用例',
    description: '',
    tags: ''
  }
  saveDialog.value.visible = true
}

async function confirmSaveCase() {
  if (!saveDialog.value.form.name?.trim()) return ElMessage.warning('请填写用例名称')
  saveDialog.value.saving = true
  try {
    const res = await browserLabApi.createCase({
      name: saveDialog.value.form.name.trim(),
      description: saveDialog.value.form.description,
      tags: saveDialog.value.form.tags,
      task_text: form.value.task_text,
      start_url: form.value.start_url,
      config: {
        ai_config_id: aiConfigId.value || null,
        ...browserLabExecConfigPayload(form.value)
      }
    }, projectId.value)
    if (res.data?.code === 200) {
      ElMessage.success('已保存到用例库')
      saveDialog.value.visible = false
      caseId.value = res.data.data?.id
      caseName.value = res.data.data?.name
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '保存失败')
  } finally {
    saveDialog.value.saving = false
  }
}

async function loadCase(id) {
  const res = await browserLabApi.getCase(id, projectId.value)
  if (res.data?.code !== 200) return
  const c = res.data.data
  caseId.value = c.id
  caseName.value = c.name
  form.value = {
    ...form.value,
    start_url: c.start_url,
    task_text: c.task_text,
    ...mergeBrowserLabExecForm(c)
  }
  if (c.ai_config_id) aiConfigId.value = c.ai_config_id
}

function clearCase() {
  caseId.value = null
  caseName.value = ''
  router.replace({ path: '/browser-lab/run' })
}

async function loadRunningTask(taskId) {
  const res = await browserLabApi.getTask(taskId, projectId.value)
  if (res.data?.code !== 200) return
  const task = res.data.data
  activeTaskId.value = task.id
  liveStatus.value = task.status
  liveSummary.value = task.error_message || task.result_summary || ''
  liveTokens.value = Number(task.tokens_used || 0)
  hasGif.value = Boolean(task.gif_url || task.gif_path)
  running.value = ['pending', 'running'].includes(task.status)
  if (running.value) {
    subscribeTask(task.id)
  } else {
    stepLogs.value = normalizeBrowserLabSteps(task.step_log || [])
    const lastShot = [...stepLogs.value].reverse().find((s) => s.screenshot_file)
    if (lastShot) await loadScreenshot(task.id, lastShot.screenshot_file)
  }
}

async function initFromRoute() {
  const qTask = route.query.taskId
  if (qTask && projectId.value) {
    await loadRunningTask(Number(qTask))
    return
  }
  const qCase = route.query.caseId
  const qRun = route.query.run === '1'
  const qDeviceId = route.query.deviceId
  const qHeadless = route.query.headless
  if (qCase && projectId.value) {
    await loadCase(Number(qCase))
    if (qDeviceId) form.value.device_id = String(qDeviceId)
    if (qHeadless === '0') form.value.headless = false
    if (qRun && canExecute.value) {
      const execOverride = qDeviceId
        ? {
            device_id: String(qDeviceId),
            execForm: {
              ...mergeBrowserLabExecForm(form.value),
              device_id: String(qDeviceId),
              headless: qHeadless !== '0',
            },
          }
        : null
      await startTask(execOverride)
    }
  }
}

watch(() => [route.query.caseId, route.query.taskId], () => initFromRoute())
watch(projectId, () => { if (projectId.value) initFromRoute() })

onMounted(async () => {
  await loadConfigs()
  await initFromRoute()
})

onBeforeUnmount(() => {
  taskPoll.stop()
  revokeScreenshots()
})
</script>

<style scoped>
.panel-card { margin-bottom: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.live-header { display: flex; justify-content: space-between; align-items: center; }
.live-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.screenshot-wrap {
  min-height: 240px; background: #0f172a; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; margin-bottom: 12px; overflow: hidden;
}
.screenshot-img { max-width: 100%; max-height: 420px; object-fit: contain; }
.log-wrap {
  max-height: 280px; overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 8px 12px;
}
.log-item { padding: 8px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.log-item:last-child { border-bottom: none; }
.log-head { display: flex; gap: 8px; font-size: 12px; }
.log-step { font-weight: 600; color: var(--el-color-primary); }
.log-url { color: var(--el-text-color-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.log-goal { margin-top: 4px; font-size: 13px; }
.log-think { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); white-space: pre-wrap; }
.live-hint {
  margin-bottom: 8px; padding: 8px 10px; font-size: 13px;
  background: var(--el-color-primary-light-9); border-radius: 6px; color: var(--el-text-color-regular);
}
.result-box { margin-bottom: 12px; padding: 10px 12px; background: var(--el-fill-color-light); border-radius: 8px; }
.result-title { font-weight: 600; margin-bottom: 6px; }
.result-tokens { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.result-text { white-space: pre-wrap; font-size: 13px; }
.gif-row { margin-top: 8px; }
.field-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5; }
.param-input-row { display: flex; gap: 8px; align-items: flex-start; width: 100%; }
</style>
