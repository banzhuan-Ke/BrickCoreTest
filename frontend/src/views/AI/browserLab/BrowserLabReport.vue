<template>
  <PageCard>
    <template #title>
      <div class="report-head">
        <div>
          <b>执行报告 #{{ taskId }}</b>
          <span v-if="report" class="sub">
            {{ report.case_name ? `用例：${report.case_name} · ` : '' }}{{ statusLabel(report.status) }}
          </span>
        </div>
        <div class="actions">
          <el-button @click="goBack">返回记录</el-button>
          <el-button
            v-if="canImport && report && importableStatus"
            type="success"
            plain
            @click="importVisible = true"
          >
            导入 Web 用例
          </el-button>
          <el-button v-if="canExecute && report" type="primary" @click="rerun">再次执行</el-button>
        </div>
      </div>
    </template>
    <template #main>
      <div v-loading="loading">
        <template v-if="report">
          <el-descriptions :column="2" border size="small" class="meta">
            <el-descriptions-item label="起始 URL">{{ report.start_url }}</el-descriptions-item>
            <el-descriptions-item label="执行人">{{ report.created_by || '-' }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatTime(report.started_at) }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ formatTime(report.finished_at) }}</el-descriptions-item>
            <el-descriptions-item label="步数">{{ report.step_count ?? report.steps_count }}</el-descriptions-item>
            <el-descriptions-item label="耗时">{{ report.duration_sec != null ? `${report.duration_sec}s` : '-' }}</el-descriptions-item>
            <el-descriptions-item label="Token 消耗">
              <span :class="{ 'token-zero': !report.tokens_used }">{{ formatTokens(report.tokens_used) }}</span>
              <span v-if="report.token_saved_estimate" class="token-saved">
                （约省 {{ Number(report.token_saved_estimate).toLocaleString() }}）
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTag(report.status)" size="small">{{ statusLabel(report.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="动作缓存">
              <el-tag v-if="report.cache_status" :type="cacheTag(report.cache_status)" size="small">
                {{ cacheLabel(report.cache_status) }}
              </el-tag>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="运行位置">
              {{ runModeLabel }}
            </el-descriptions-item>
            <el-descriptions-item v-if="report.device_id" label="执行设备">
              {{ report.device_id }}
            </el-descriptions-item>
            <el-descriptions-item label="执行引擎">{{ report.engine || 'browser_use' }}</el-descriptions-item>
          </el-descriptions>

          <el-card shadow="never" class="block">
            <template #header>任务描述</template>
            <div class="pre">{{ report.task_text }}</div>
          </el-card>

          <el-card shadow="never" class="block">
            <template #header>执行结果</template>
            <div class="pre">{{ report.error_message || report.result_summary || '无' }}</div>
            <div v-if="gifPreviewHref" class="gif-row">
              <a :href="gifPreviewHref" target="_blank" rel="noopener">查看回放 GIF</a>
            </div>
          </el-card>

          <el-card shadow="never" class="block">
            <template #header>步骤明细</template>
            <el-timeline>
              <el-timeline-item
                v-for="(step, idx) in reportSteps"
                :key="idx"
                :timestamp="stepLabel(step)"
              >
                <div class="step-url">{{ step.url }}</div>
                <div v-if="step.next_goal" class="step-goal">{{ step.next_goal }}</div>
                <div v-if="step.thinking" class="step-think">{{ step.thinking }}</div>
                <img
                  v-if="step.screenshot_url || (step.screenshot_file && screenshotSrc(step))"
                  class="step-shot"
                  :src="step.screenshot_url || screenshotSrc(step)"
                  alt="步骤截图"
                  @click="previewShot(step)"
                />
                <div
                  v-else-if="step.screenshot_file && screenshotsLoading"
                  class="step-shot-loading"
                >
                  截图加载中…
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-if="!reportSteps.length" description="暂无步骤" />
          </el-card>
        </template>
      </div>
    </template>
  </PageCard>
  <BrowserLabImportDialog
    v-model="importVisible"
    :task-id="taskId"
    :project-id="projectId"
    :default-case-name="report?.case_name || ''"
    :task-text="report?.task_text || ''"
    :task-start-url="report?.start_url || ''"
    :task-device-id="report?.device_id || report?.config_json?.device_id || ''"
  />
  <BrowserLabExecConfirmDialog ref="execConfirmRef" />
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import BrowserLabImportDialog from './BrowserLabImportDialog.vue'
import BrowserLabExecConfirmDialog from './BrowserLabExecConfirmDialog.vue'
import { browserLabApi } from '@/api/modules/ai.js'
import { browserLabGifPreviewHref } from './browserLabGif.js'
import { cacheStatusLabel, cacheStatusTag } from './browserLabExecOptions.js'
import { buildExecConfirmContext } from './browserLabExecConfirmHelpers.js'
import { registerBrowserLabExecConfirmDialog, openBrowserLabExecConfirm } from '@/composables/useBrowserLabExecConfirm.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import { browserLabStepLabel, normalizeBrowserLabSteps } from './browserLabStepLog.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const execConfirmRef = ref(null)

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.taskId)
const projectId = computed(() => ProjectStore().projectInfo?.id)
const canExecute = computed(() => UserStore().hasPermission('ai_test:execute'))
const canImport = computed(() =>
  UserStore().hasPermission('ai_test:execute') && UserStore().hasPermission('ui_case:edit')
)
const importableStatus = computed(() =>
  ['done', 'failed', 'stopped'].includes(report.value?.status)
)
const importVisible = ref(false)
const { enabledConfigs, loadConfigs } = useAiConfigSelect({ scene: 'browser_lab' })

const runModeLabel = computed(() => {
  const mode = report.value?.run_mode || report.value?.config_json?.run_mode || 'local'
  if (mode === 'runner') return 'Runner 执行机'
  return '平台本机'
})

const loading = ref(false)
const report = ref(null)
const reportSteps = computed(() => normalizeBrowserLabSteps(report.value?.steps || []))
const stepLabel = browserLabStepLabel
const hasGif = ref(false)
const gifPreviewHref = computed(() =>
  hasGif.value ? browserLabGifPreviewHref(taskId.value, projectId.value) : ''
)
const screenshotsLoading = ref(false)
const screenshotUrls = ref({})
const screenshotObjectUrls = ref([])

function statusLabel(s) {
  return { done: '完成', running: '执行中', failed: '失败', stopped: '已停止', pending: '等待' }[s] || s
}
function statusTag(s) {
  return { done: 'success', running: 'warning', failed: 'danger', stopped: 'info' }[s] || 'info'
}
const cacheLabel = cacheStatusLabel
const cacheTag = cacheStatusTag
function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '-'
}

function formatTokens(n) {
  const v = Number(n || 0)
  if (!v) {
    if (report.value?.cache_hit || report.value?.engine === 'action_cache') return '0（缓存命中）'
    return '未统计（旧记录或 API 未返回 usage）'
  }
  return v.toLocaleString()
}

function screenshotSrc(step) {
  return step?.screenshot_url || screenshotUrls.value[step.screenshot_file] || ''
}

function revokeScreenshots() {
  screenshotObjectUrls.value.forEach((url) => URL.revokeObjectURL(url))
  screenshotObjectUrls.value = []
  screenshotUrls.value = {}
}

async function loadStepScreenshots() {
  revokeScreenshots()
  const steps = report.value?.steps || []
  const files = steps.filter((s) => s.screenshot_file && !s.screenshot_url)
  if (!files.length || !projectId.value || !taskId.value) return
  screenshotsLoading.value = true
  try {
    await Promise.all(
      files.map(async (step) => {
        const filename = step.screenshot_file
        try {
          const blob = await browserLabApi.fetchScreenshotBlob(
            taskId.value,
            filename,
            projectId.value
          )
          const url = URL.createObjectURL(blob)
          screenshotObjectUrls.value.push(url)
          screenshotUrls.value = { ...screenshotUrls.value, [filename]: url }
        } catch (e) {
          console.warn('步骤截图加载失败', filename, e)
        }
      })
    )
  } finally {
    screenshotsLoading.value = false
  }
}

function previewShot(step) {
  const url = step?.screenshot_url || screenshotSrc(step)
  if (url) window.open(url, '_blank')
}

async function loadReport() {
  if (!projectId.value || !taskId.value) return
  loading.value = true
  try {
    const res = await browserLabApi.getTaskReport(taskId.value, projectId.value)
    if (res.data?.code === 200) {
      report.value = res.data.data
      hasGif.value = Boolean(report.value.gif_url || report.value.gif_path)
      await loadStepScreenshots()
    }
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/browser-lab/records')
}

async function rerun() {
  const r = report.value
  if (!r) return
  const ctx = buildExecConfirmContext({
    title: '确认重跑',
    name: r.case_name || `报告 #${taskId.value}`,
    source: r,
    aiConfigs: enabledConfigs.value,
    taskId: taskId.value,
  })
  let confirmed
  try {
    confirmed = await openBrowserLabExecConfirm(ctx)
  } catch {
    return ElMessage.warning('执行确认弹窗未就绪，请刷新页面后重试')
  }
  if (!confirmed) return
  const res = await browserLabApi.rerunTask(taskId.value, projectId.value, {
    device_id: confirmed.device_id,
    headless: confirmed.execForm?.headless,
  })
  if (res.data?.code === 200) {
    ElMessage.success('已重新执行')
    router.push({ path: '/browser-lab/run', query: { taskId: res.data.data?.id } })
  }
}

watch(execConfirmRef, (v) => {
  if (v) registerBrowserLabExecConfirmDialog(v)
})

onMounted(async () => {
  await loadConfigs()
  nextTick(() => {
    if (execConfirmRef.value) registerBrowserLabExecConfirmDialog(execConfirmRef.value)
  })
  loadReport()
})
onBeforeUnmount(revokeScreenshots)
</script>

<style scoped>
.report-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.sub { display: block; font-size: 12px; font-weight: normal; color: var(--el-text-color-secondary); margin-top: 4px; }
.actions { display: flex; gap: 8px; }
.meta { margin-bottom: 16px; }
.block { margin-bottom: 16px; }
.pre { white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
.gif-row { margin-top: 8px; }
.step-url { font-size: 12px; color: var(--el-text-color-secondary); }
.step-goal { margin-top: 4px; }
.step-think { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.step-shot { margin-top: 8px; max-width: 100%; max-height: 280px; border-radius: 6px; cursor: zoom-in; }
.step-shot-loading { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.token-zero { color: var(--el-text-color-secondary); }
.token-saved { margin-left: 6px; font-size: 12px; color: var(--el-color-success); }
</style>
