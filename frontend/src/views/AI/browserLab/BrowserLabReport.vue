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
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTag(report.status)" size="small">{{ statusLabel(report.status) }}</el-tag>
            </el-descriptions-item>
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
              <el-timeline-item v-for="(step, idx) in report.steps" :key="idx" :timestamp="`Step ${step.index}`">
                <div class="step-url">{{ step.url }}</div>
                <div v-if="step.next_goal" class="step-goal">{{ step.next_goal }}</div>
                <div v-if="step.thinking" class="step-think">{{ step.thinking }}</div>
                <img
                  v-if="step.screenshot_file && screenshotSrc(step.screenshot_file)"
                  class="step-shot"
                  :src="screenshotSrc(step.screenshot_file)"
                  alt="步骤截图"
                  @click="previewShot(step.screenshot_file)"
                />
                <div
                  v-else-if="step.screenshot_file && screenshotsLoading"
                  class="step-shot-loading"
                >
                  截图加载中…
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-if="!report.steps?.length" description="暂无步骤" />
          </el-card>
        </template>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { browserLabApi } from '@/api/modules/ai.js'
import { browserLabGifPreviewHref } from './browserLabGif.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.taskId)
const projectId = computed(() => ProjectStore().projectInfo?.id)
const canExecute = computed(() => UserStore().hasPermission('ai_test:execute'))

const loading = ref(false)
const report = ref(null)
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
function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '-'
}

function formatTokens(n) {
  const v = Number(n || 0)
  if (!v) return '未统计（旧记录或 API 未返回 usage）'
  return v.toLocaleString()
}

function screenshotSrc(filename) {
  return screenshotUrls.value[filename] || ''
}

function revokeScreenshots() {
  screenshotObjectUrls.value.forEach((url) => URL.revokeObjectURL(url))
  screenshotObjectUrls.value = []
  screenshotUrls.value = {}
}

async function loadStepScreenshots() {
  revokeScreenshots()
  const steps = report.value?.steps || []
  const files = steps.map((s) => s.screenshot_file).filter(Boolean)
  if (!files.length || !projectId.value || !taskId.value) return
  screenshotsLoading.value = true
  try {
    await Promise.all(
      files.map(async (filename) => {
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

function previewShot(filename) {
  const url = screenshotSrc(filename)
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
  const res = await browserLabApi.rerunTask(taskId.value, projectId.value)
  if (res.data?.code === 200) {
    ElMessage.success('已重新执行')
    router.push({ path: '/browser-lab/run', query: { taskId: res.data.data?.id } })
  }
}

onMounted(loadReport)
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
</style>
