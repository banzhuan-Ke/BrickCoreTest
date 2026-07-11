<template>

  <div class="interactive-debug">

    <el-dialog

      v-model="openDialogVisible"

      title="交互调试 — 打开浏览器"

      width="760px"

      destroy-on-close

      @open="onDialogOpen"

      @closed="resetOpenForm"

    >

      <el-alert

        type="info"

        :closable="false"

        show-icon

        title="Runner 将打开有头浏览器，不会自动执行业务步骤。可先自动打开起始页，再手动操作到目标状态后按步试跑；失败时浏览器保持打开。"

        style="margin-bottom: 16px;"

      />

      <div class="run-config-container">

        <div class="config-section">

          <div class="section-title"><span>运行环境</span></div>

          <div class="env-cards">

            <div

              v-for="env in proStore.envList"

              :key="env.id"

              :class="['env-card', { active: openForm.env_id === env.id }]"

              @click="openForm.env_id = env.id"

            >

              <div class="env-name">{{ env.name }}</div>

              <div class="env-host">{{ env.host }}</div>

            </div>

          </div>

        </div>

        <div class="config-section">

          <div class="section-title"><span>浏览器</span></div>

          <el-radio-group v-model="openForm.browser_type">

            <el-radio value="chromium">Chrome</el-radio>

            <el-radio value="firefox">Firefox</el-radio>

            <el-radio value="webkit">Safari</el-radio>

          </el-radio-group>

        </div>

        <div class="config-section">

          <div class="section-title"><span>起始页</span></div>

          <el-checkbox v-model="openForm.auto_navigate">

            打开后自动导航到环境地址或首步 open_url

          </el-checkbox>

          <p v-if="previewInitialUrl" class="initial-url-hint">预计打开：{{ previewInitialUrl }}</p>

        </div>

        <div class="config-section">

          <div class="section-title"><span>执行设备</span></div>

          <el-select v-model="openForm.device_id" placeholder="请选择在线 Web Runner" style="width: 100%;">

            <el-option

              v-for="device in deviceList"

              :key="device.id"

              :label="device.name || device.username"

              :value="device.id"

            />

          </el-select>

        </div>

      </div>

      <template #footer>

        <el-button @click="openDialogVisible = false">取消</el-button>

        <el-button type="primary" :loading="opening" @click="startSession">打开浏览器</el-button>

      </template>

    </el-dialog>



    <div v-if="session" class="debug-session-bar">

      <div class="bar-main">

        <div class="bar-left">

          <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>

          <span class="bar-meta">调试会话 #{{ session.id }} · {{ session.steps_count }} 步</span>

          <el-tag v-if="stepsStale" type="warning" size="small">步骤已变更</el-tag>

          <span v-if="idleRemainingLabel" class="bar-meta idle-hint">空闲 {{ idleRemainingLabel }} 后自动关闭</span>

          <span v-if="lastRunSummary" :class="['bar-result', lastRunFailed ? 'is-fail' : 'is-ok']">{{ lastRunSummary }}</span>

        </div>

        <div class="bar-actions">

          <el-button v-if="stepsStale" size="small" type="warning" plain :loading="syncing" @click="syncStepsFromEditor">

            同步最新步骤

          </el-button>

          <el-button size="small" :loading="locatorBusy" :disabled="!canLocatorAction" @click="highlightSelectedStep">
            高亮定位器
          </el-button>
          <el-button size="small" :loading="locatorBusy" :disabled="!canLocatorAction" @click="verifySelectedStep">
            验证定位器
          </el-button>
          <el-button
            size="small"
            :type="pickModeActive ? 'warning' : 'default'"
            :loading="pickModeLoading"
            :disabled="!canRun"
            @click="togglePickMode"
          >
            {{ pickModeActive ? '退出拾取' : '拾取元素' }}
          </el-button>
          <el-button size="small" :loading="running" :disabled="!canRun" @click="runSingleStep">

            执行选中步

          </el-button>

          <el-button size="small" :loading="running" :disabled="!canRun" @click="runThroughStep">

            从选中步执行至末尾

          </el-button>

          <el-button size="small" type="danger" plain :loading="closing" @click="closeSession">

            关闭浏览器

          </el-button>

        </div>

      </div>



      <el-alert

        v-if="stepsStale"

        type="warning"

        :closable="false"

        show-icon

        class="stale-alert"

        title="编辑器步骤与会话快照不一致。执行前建议同步，否则 Runner 仍使用打开会话时的步骤。"

      />

      <el-alert
        v-if="pickModeActive"
        type="warning"
        :closable="false"
        show-icon
        class="stale-alert"
        title="拾取模式已开启：请在 Runner 浏览器中点击目标元素"
      />

      <el-alert
        v-if="locatorActionSummary"
        :type="locatorActionType"
        :closable="false"
        show-icon
        class="stale-alert"
        :title="locatorActionSummary"
      />



      <div v-if="lastResultSteps.length" class="result-panel">

        <div class="result-panel-head" @click="resultExpanded = !resultExpanded">

          <span>最近执行明细（{{ lastResultSteps.length }} 步）</span>

          <el-icon><ArrowDown v-if="!resultExpanded" /><ArrowUp v-else /></el-icon>

        </div>

        <div v-show="resultExpanded" class="result-steps">

          <div

            v-for="item in lastResultSteps"

            :key="item.step_index"

            :class="['result-step-item', `is-${item.status}`]"

            @click="focusStep(item.step_index)"

          >

            <div class="result-step-head">

              <span class="result-step-no">步骤 {{ item.step_index + 1 }}</span>

              <el-tag size="small" :type="item.status === 'success' ? 'success' : 'danger'">

                {{ formatDebugStepStatus(item.status) }}

              </el-tag>

              <span class="result-step-kw">{{ item.keyword || item.desc }}</span>

            </div>

            <p v-if="item.message" class="result-step-msg">{{ item.message }}</p>

          </div>

        </div>

      </div>

    </div>

    <el-dialog v-model="pickDialogVisible" title="拾取元素 — 回填定位器" width="640px" destroy-on-close>
      <p class="pick-dialog-tip">将拾取到的定位器应用到当前选中步骤（步骤 {{ selectedStepIndex + 1 }}）</p>
      <p v-if="pickPreview.frame" class="pick-frame-hint">iframe：{{ pickPreview.frame }}</p>
      <el-input v-model="pickPreview.locator" type="textarea" :rows="3" readonly />
      <div v-if="pickPreview.candidates?.length" class="pick-candidates">
        <span class="pick-label">候选定位器：</span>
        <el-tag
          v-for="(item, idx) in pickPreview.candidates"
          :key="idx"
          size="small"
          class="pick-tag"
          @click="selectPickCandidate(item)"
        >{{ item }}</el-tag>
      </div>
      <template #footer>
        <el-button @click="pickDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmApplyPick">应用到选中步</el-button>
      </template>
    </el-dialog>

  </div>

</template>



<script setup>

import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'

import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'

import { ProjectStore } from '@/stores/module/ProjectStore.js'

import { UserStore } from '@/stores/module/UserStore.js'

import http from '@/api/index'

import { uiDebugApi } from '@/api/modules/ui.js'

import { filterWebRunnerDevices } from '@/utils/runnerDevice'

import { buildDebugRunningHints, buildDebugExecutionHints, mergeDebugExecutionHints, formatDebugStepStatus, formatIdleRemaining, buildSessionToEditorMap, mapSessionStepResultsToEditor, mergeDebugRunStepResults, groupContiguousStepIndices } from '@/utils/debugSession.js'

import { extractOpenUrlFromSteps } from '@/utils/caseDescription.js'

import { formatLocatorActionSummary, splitCombinedLocator, stepHasLocator } from '@/utils/debugLocator.js'



const props = defineProps({

  caseId: { type: [String, Number], required: true },

  steps: { type: Array, default: () => [] },

  selectedStepIndex: { type: Number, default: 0 },

})



const emit = defineEmits(['session-change', 'debug-hints-change', 'focus-step', 'apply-locator'])



const proStore = ProjectStore()

const uStore = UserStore()



const openDialogVisible = ref(false)

const opening = ref(false)

const running = ref(false)

const closing = ref(false)

const syncing = ref(false)

const deviceList = ref([])

const session = ref(null)

const pollTimer = ref(null)

const stepsStale = ref(false)

const resultExpanded = ref(true)
const locatorBusy = ref(false)
const pickModeActive = ref(false)
const pickModeLoading = ref(false)
const pickDialogVisible = ref(false)
const pickPreview = reactive({ locator: '', frame: '', element_locator: '', candidates: [], meta: {} })
const pickPollTimer = ref(null)
const staleCheckTimer = ref(null)
const mergedLastResult = ref(null)
const lastEditorMap = ref([])
const idleBaseline = ref({ fetchedAt: 0, remaining: 0 })
const idleTick = ref(0)
let idleCountdownTimer = null



const openForm = reactive({

  env_id: '',

  browser_type: 'chromium',

  device_id: '',

  auto_navigate: true,

  username: uStore.userInfo?.username || '',

})



const statusLabel = computed(() => {

  const map = {

    starting: '启动中',

    ready: '就绪',

    running: '执行中',

    closing: '关闭中',

    closed: '已关闭',

    error: '异常',

  }

  return map[session.value?.status] || session.value?.status || '—'

})



const statusTagType = computed(() => {

  const s = session.value?.status

  if (s === 'ready') return 'success'

  if (s === 'running' || s === 'starting' || s === 'closing') return 'primary'

  if (s === 'closed') return 'info'

  return 'danger'

})



const canRun = computed(() => session.value?.status === 'ready' && props.steps?.length > 0)



const selectedStep = computed(() => props.steps?.[props.selectedStepIndex] || null)



const canLocatorAction = computed(() => canRun.value && stepHasLocator(selectedStep.value))



const locatorActionSummary = computed(() => {

  const result = session.value?.last_result

  if (!result?.type || result.type === 'run') return ''

  if (result.steps?.length) return ''

  return formatLocatorActionSummary(result)

})



const locatorActionType = computed(() => {

  const result = session.value?.last_result

  if (result?.type === 'verify') {

    if (result.status === 'success') return 'success'

    if (result.status === 'ambiguous') return 'warning'

    return 'error'

  }

  if (result?.type === 'highlight') return result.status === 'success' ? 'success' : 'error'

  if (result?.type === 'pick') return 'success'

  return 'info'

})



const effectiveRunResult = computed(() => {
  if (mergedLastResult.value) return mergedLastResult.value
  const r = session.value?.last_result
  return r?.type === 'run' ? r : null
})

const lastRunSummary = computed(() => {

  const r = effectiveRunResult.value

  if (!r || r.type !== 'run') return ''

  if (!r.steps?.length) return ''

  const failed = r.steps.find((s) => s.status === 'fail')

  if (failed) {

    return `第 ${failed.step_index + 1} 步失败: ${failed.message || failed.keyword || ''}`

  }

  if (r.status === 'success') {

    return `第 ${(r.from_index ?? 0) + 1}～${(r.through_index ?? 0) + 1} 步执行成功`

  }

  return ''

})



const lastRunFailed = computed(() => effectiveRunResult.value?.status === 'fail')

const idleRemainingLabel = computed(() => {
  idleTick.value
  if (session.value?.status !== 'ready') return ''
  const base = idleBaseline.value
  if (!base.fetchedAt) return ''
  const elapsed = Math.floor((Date.now() - base.fetchedAt) / 1000)
  return formatIdleRemaining(Math.max(0, base.remaining - elapsed))
})

const lastResultSteps = computed(() => {

  const r = effectiveRunResult.value

  if (!r || r.type !== 'run') return []

  return r.steps || []

})



const previewInitialUrl = computed(() => {

  const openUrl = extractOpenUrlFromSteps(props.steps)

  if (openUrl) return openUrl

  const env = proStore.envList?.find((e) => e.id === openForm.env_id)

  const host = (env?.host || '').trim()

  if (!host) return ''

  return host.startsWith('http') ? host : `https://${host}`

})



const debugHints = computed(() => {
  const runningHints = buildDebugRunningHints(session.value)
  let resultHints = null
  if (mergedLastResult.value) {
    resultHints = buildDebugExecutionHints(mergedLastResult.value)
  } else if (session.value?.last_result?.type === 'run') {
    resultHints = buildDebugExecutionHints(session.value.last_result)
  }
  return mergeDebugExecutionHints(runningHints, resultHints)
})



watch(session, (val) => {

  emit('session-change', val)

  if (val?.id && val?.status === 'ready') {

    scheduleCheckStepsStale()

  }

}, { deep: true })



watch(debugHints, (val) => {

  emit('debug-hints-change', val)

}, { immediate: true })



watch(() => props.steps, () => {

  if (session.value?.id) {

    scheduleCheckStepsStale()

  }

}, { deep: true })



function focusStep(index) {

  emit('focus-step', index)

}



function showOpenDialog() {

  if (!props.steps?.length) {

    ElNotification.warning('请先添加步骤')

    return

  }

  openDialogVisible.value = true

}



function onDialogOpen() {

  openForm.env_id = proStore.envList?.[0]?.id || ''

  openForm.device_id = ''

  openForm.browser_type = 'chromium'

  openForm.auto_navigate = true

  openForm.username = uStore.userInfo?.username || ''

  loadDevices()

}



function resetOpenForm() {

  opening.value = false

}



async function loadDevices() {

  try {

    const res = await http.deviceApi.getList({ status: '在线' })

    deviceList.value = res.status === 200 ? filterWebRunnerDevices(res.data || []) : []

    if (!openForm.device_id && deviceList.value.length) {

      openForm.device_id = deviceList.value[0].id

    }

  } catch (e) {

    ElMessage.error(e?.message || '加载设备失败')

  }

}



function parseSessionResponse(res) {

  const body = res?.data ?? res

  return body?.data ?? body

}



function parseCompareResponse(res) {

  const body = res?.data ?? res

  return body?.data ?? body

}



function syncIdleBaseline(data) {
  if (data?.status === 'ready' && data.idle_remaining_seconds != null) {
    idleBaseline.value = {
      fetchedAt: Date.now(),
      remaining: Number(data.idle_remaining_seconds),
    }
  }
}

function scheduleCheckStepsStale() {
  if (staleCheckTimer.value) clearTimeout(staleCheckTimer.value)
  staleCheckTimer.value = setTimeout(() => {
    staleCheckTimer.value = null
    checkStepsStale()
  }, 450)
}

async function checkStepsStale() {

  if (!session.value?.id || !props.steps?.length) {

    stepsStale.value = false

    return

  }

  try {

    const res = await uiDebugApi.compareSteps(session.value.id, { steps: props.steps })

    const data = parseCompareResponse(res)

    stepsStale.value = !!data?.stale

  } catch {

    stepsStale.value = false

  }

}



async function waitUntilReady(timeoutMs = 120000) {

  const started = Date.now()

  while (Date.now() - started < timeoutMs) {

    await refreshSession()

    if (!session.value) return 'closed'

    const status = session.value?.status

    if (status === 'ready' || status === 'error' || status === 'closed') {

      return status

    }

    if (status === 'closing') {

      await new Promise((resolve) => setTimeout(resolve, 1200))

      continue

    }

    await new Promise((resolve) => setTimeout(resolve, 1200))

  }

  ElMessage.warning('等待 Runner 执行结果超时，请查看会话状态')

  return session.value?.status

}



async function ensureStepsForRun() {

  if (!stepsStale.value) return true

  try {

    await ElMessageBox.confirm(

      '编辑器步骤与会话快照不一致。请选择执行方式：',

      '步骤已变更',

      {

        confirmButtonText: '同步最新步骤并执行',

        cancelButtonText: '仍用会话快照执行',

        distinguishCancelAndClose: true,

        type: 'warning',

      },

    )

    const synced = await syncStepsFromEditor()

    return synced

  } catch (action) {

    if (action === 'cancel') return true

    return false

  }

}



async function syncStepsFromEditor() {

  if (!session.value?.id) return false

  syncing.value = true

  try {

    await uiDebugApi.syncSteps(session.value.id, { steps: props.steps })

    const status = await waitUntilReady()

    if (status === 'ready') {

      stepsStale.value = false
      mergedLastResult.value = null

      ElNotification.success('步骤已同步到 Runner')

      return true

    }

    return false

  } catch (e) {

    ElMessage.error(e?.response?.data?.detail || e?.message || '同步步骤失败')

    return false

  } finally {

    syncing.value = false

  }

}



async function startSession() {

  if (!openForm.env_id || !openForm.device_id) {

    ElMessage.warning('请选择环境和 Runner 设备')

    return

  }

  opening.value = true

  try {

    const res = await uiDebugApi.createSession({

      case_id: Number(props.caseId),

      env_id: openForm.env_id,

      browser_type: openForm.browser_type,

      config: false,

      device_id: openForm.device_id,

      steps: props.steps,

      auto_navigate: openForm.auto_navigate,

    })

    session.value = parseSessionResponse(res)

    syncIdleBaseline(session.value)

    mergedLastResult.value = null
    lastEditorMap.value = []

    stepsStale.value = false

    openDialogVisible.value = false

    startPolling()

    ElNotification.success('调试浏览器正在 Runner 上启动，请稍候…')

  } catch (e) {

    ElMessage.error(e?.response?.data?.detail || e?.message || '打开调试会话失败')

  } finally {

    opening.value = false

  }

}



async function resolveEditorRunPlan(editorIndices) {
  const res = await uiDebugApi.resolveRunSegments(session.value.id, {
    steps: props.steps,
    editor_indices: editorIndices,
  })
  const data = parseCompareResponse(res)
  const segments = (data?.segments || []).map((row) => [row.from_index, row.through_index])
  return {
    segments,
    editorMap: data?.editor_map || [],
    stale: !!data?.stale,
  }
}

async function resolveEditorStepSessionIndex(editorIndex) {
  try {
    const plan = await resolveEditorRunPlan([editorIndex])
    if (plan.stale) return editorIndex
    const first = plan.segments[0]
    return first ? first[0] : editorIndex
  } catch {
    return editorIndex
  }
}

function normalizeEditorIndices(indices) {
  return [...new Set((indices || []).map((i) => Number(i)))]
    .filter((i) => !Number.isNaN(i) && i >= 0 && i < props.steps.length)
    .sort((a, b) => a - b)
}

async function runSessionSegment(fromIndex, throughIndex) {
  if (!session.value?.id) return false
  try {
    await uiDebugApi.runSteps(session.value.id, { from_index: fromIndex, through_index: throughIndex })
    const status = await waitUntilReady()
    if (status === 'ready') {
      return true
    }
    if (status === 'error') {
      ElMessage.error(session.value?.error || '调试执行异常')
    }
    return false
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '执行失败')
    return false
  }
}

async function runEditorIndices(editorIndices, { skipEnsure = false } = {}) {
  if (!session.value?.id) return false
  const valid = normalizeEditorIndices(editorIndices)
  if (!valid.length) {
    ElMessage.warning('所选步骤下标无效')
    return false
  }

  if (!skipEnsure) {
    const proceed = await ensureStepsForRun()
    if (!proceed) return false
  }

  let segments = []
  let editorMap = []
  let useDirectIndices = false
  try {
    const plan = await resolveEditorRunPlan(valid)
    if (plan.stale) {
      ElMessage.warning('步骤与会话不一致，将按编辑器下标直接映射到会话快照执行')
      segments = groupContiguousStepIndices(valid)
      useDirectIndices = true
    } else {
      segments = plan.segments
      editorMap = plan.editorMap
      lastEditorMap.value = editorMap
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '解析执行区间失败')
    return false
  }
  if (!segments.length) {
    ElMessage.warning('未能解析出可执行的步骤区间')
    return false
  }

  mergedLastResult.value = null
  const sessionToEditor = useDirectIndices
    ? Object.fromEntries(valid.map((i) => [i, i]))
    : buildSessionToEditorMap(editorMap)
  const accumulated = []

  running.value = true
  try {
    for (const [fromIndex, throughIndex] of segments) {
      const ok = await runSessionSegment(fromIndex, throughIndex)
      const lr = session.value?.last_result
      if (lr?.steps?.length) {
        const steps = useDirectIndices
          ? lr.steps.map((item) => ({
            ...item,
            session_step_index: item.step_index,
          }))
          : mapSessionStepResultsToEditor(lr.steps, sessionToEditor)
        accumulated.push({ ...lr, steps })
      }
      if (!ok) break
      const failed = lr?.steps?.find((s) => s.status === 'fail')
      if (failed) {
        const editorIdx = useDirectIndices
          ? failed.step_index
          : (sessionToEditor[failed.step_index] ?? failed.step_index)
        emit('focus-step', editorIdx)
        break
      }
    }

    if (accumulated.length) {
      mergedLastResult.value = mergeDebugRunStepResults(accumulated)
      resultExpanded.value = true
    }
    return accumulated.length > 0 && mergedLastResult.value?.status !== 'fail'
  } finally {
    running.value = false
  }
}

async function runSelectedSteps(indices) {
  if (!indices?.length) return 'empty'
  if (!session.value) return 'no_session'
  if (session.value.status !== 'ready') {
    ElMessage.warning('调试会话尚未就绪，请稍候')
    return 'not_ready'
  }
  const ok = await runEditorIndices(indices)
  return ok ? 'ok' : 'failed'
}

function runSingleStep() {
  return runEditorIndices([props.selectedStepIndex])
}

function runThroughStep() {
  const idx = props.selectedStepIndex
  const indices = Array.from({ length: props.steps.length - idx }, (_, i) => idx + i)
  return runEditorIndices(indices)
}

async function runFromStartThrough(throughIndex) {
  const through = Math.max(0, Math.min(throughIndex, (props.steps?.length || 1) - 1))
  const indices = Array.from({ length: through + 1 }, (_, i) => i)
  return runEditorIndices(indices)
}

async function runStepAt(index, throughEnd = false) {
  if (!session.value) {
    showOpenDialog()
    return
  }
  if (session.value.status !== 'ready') {
    ElMessage.warning('调试会话尚未就绪，请稍候')
    return
  }
  if (throughEnd) {
    return runFromStartThrough(index)
  }
  return runEditorIndices([index])
}

async function closeSession() {

  if (!session.value?.id) return

  closing.value = true

  try {

    await uiDebugApi.closeSession(session.value.id)

    const status = await waitUntilReady(60000)

    stopPickPolling()

    pickModeActive.value = false

    stopPolling()

    if (status === 'closed' || !session.value) {

      session.value = null
      mergedLastResult.value = null
      lastEditorMap.value = []

      stepsStale.value = false

    } else if (status === 'error') {

      stepsStale.value = false

    } else if (status === 'closing') {

      await refreshSession()

      if (!session.value || session.value.status === 'closed') {

        session.value = null

        stepsStale.value = false

      } else {

        ElMessage.warning('会话关闭超时，后台将继续清理，可稍后刷新页面')

      }

    }

    ElNotification.info('调试浏览器已关闭')

  } catch (e) {

    ElMessage.error(e?.response?.data?.detail || e?.message || '关闭失败')

  } finally {

    closing.value = false

  }

}



async function refreshSession() {

  if (!session.value?.id) return

  try {

    const res = await uiDebugApi.getSession(session.value.id)

    session.value = parseSessionResponse(res)

    syncIdleBaseline(session.value)

    if (session.value?.status === 'closed') {

      stopPolling()

      session.value = null

      stepsStale.value = false

    } else if (session.value?.status === 'error') {

      stopPolling()

    }

  } catch (e) {

    // 轮询时静默

  }

}



function startPolling() {

  stopPolling()

  pollTimer.value = setInterval(refreshSession, 1500)

}



function stopPolling() {

  if (pollTimer.value) {

    clearInterval(pollTimer.value)

    pollTimer.value = null

  }

}



async function waitForLocatorResult(timeoutMs = 60000) {
  const status = await waitUntilReady(timeoutMs)
  if (status === 'ready') {
    return session.value?.last_result
  }
  return null
}

async function highlightSelectedStep() {
  if (!session.value?.id || !canLocatorAction.value) return
  locatorBusy.value = true
  try {
    const sessionIndex = await resolveEditorStepSessionIndex(props.selectedStepIndex)
    await uiDebugApi.highlightStep(session.value.id, { step_index: sessionIndex })
    await waitForLocatorResult()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '高亮失败')
  } finally {
    locatorBusy.value = false
  }
}

async function verifySelectedStep() {
  if (!session.value?.id || !canLocatorAction.value) return
  locatorBusy.value = true
  try {
    const sessionIndex = await resolveEditorStepSessionIndex(props.selectedStepIndex)
    await uiDebugApi.verifyLocator(session.value.id, { step_index: sessionIndex })
    await waitForLocatorResult()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '验证失败')
  } finally {
    locatorBusy.value = false
  }
}

function stopPickPolling() {
  if (pickPollTimer.value) {
    clearInterval(pickPollTimer.value)
    pickPollTimer.value = null
  }
}

function selectPickCandidate(item) {
  const split = splitCombinedLocator(item)
  pickPreview.locator = item
  if (split.frame) {
    pickPreview.frame = split.frame
    pickPreview.element_locator = split.locator
  } else {
    pickPreview.frame = ''
    pickPreview.element_locator = split.locator || item
  }
}

function openPickDialog(payload) {
  pickPreview.locator = payload.locator || ''
  pickPreview.frame = payload.frame || ''
  pickPreview.element_locator = payload.element_locator || ''
  pickPreview.candidates = payload.candidates || []
  pickPreview.meta = payload.meta || {}
  pickDialogVisible.value = true
}

function startPickPolling() {
  stopPickPolling()
  pickPollTimer.value = setInterval(async () => {
    await refreshSession()
    const result = session.value?.last_result
    if (result?.type === 'pick' && result.locator) {
      stopPickPolling()
      pickModeActive.value = false
      openPickDialog(result)
    }
  }, 1200)
}

async function togglePickMode() {
  if (!session.value?.id) return
  if (pickModeActive.value) {
    pickModeLoading.value = true
    try {
      await uiDebugApi.setPickMode(session.value.id, { enabled: false })
      await waitUntilReady()
      pickModeActive.value = false
      stopPickPolling()
    } catch (e) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '退出拾取失败')
    } finally {
      pickModeLoading.value = false
    }
    return
  }
  pickModeLoading.value = true
  try {
    await uiDebugApi.setPickMode(session.value.id, { enabled: true })
    await waitUntilReady()
    pickModeActive.value = true
    startPickPolling()
    ElNotification.info('请在 Runner 浏览器中点击要拾取的元素')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '开启拾取失败')
  } finally {
    pickModeLoading.value = false
  }
}

function confirmApplyPick() {
  if (!pickPreview.locator) {
    ElMessage.warning('定位器为空')
    return
  }
  emit('apply-locator', {
    stepIndex: props.selectedStepIndex,
    locator: pickPreview.locator,
    frame: pickPreview.frame,
    element_locator: pickPreview.element_locator,
    match_index: pickPreview.meta?.matchIndex || 1,
    candidates: pickPreview.candidates,
    meta: pickPreview.meta,
  })
  pickDialogVisible.value = false
  ElNotification.success(`已回填到步骤 ${props.selectedStepIndex + 1}`)
}



async function resumeActiveSession() {
  if (!props.caseId) return
  try {
    const res = await uiDebugApi.getActiveSession({ case_id: Number(props.caseId) })
    const data = parseSessionResponse(res)
    if (!data?.id || ['closed', 'error'].includes(data.status)) return
    session.value = data
    syncIdleBaseline(data)
    pickModeActive.value = false
    stopPickPolling()
    startPolling()
    const hint = data.status === 'closing' ? '（关闭中）' : ''
    ElNotification.info(`已恢复调试会话 #${data.id}${hint}`)
  } catch {
    // 静默：无活跃会话
  }
}

function onBeforeUnload(event) {

  if (session.value && !['closed', 'error', 'closing'].includes(session.value.status)) {

    event.preventDefault()

    event.returnValue = ''

  }

}



onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  idleCountdownTimer = setInterval(() => {
    idleTick.value += 1
  }, 1000)
  resumeActiveSession()
})



onBeforeUnmount(() => {

  stopPolling()

  stopPickPolling()

  if (staleCheckTimer.value) clearTimeout(staleCheckTimer.value)

  if (idleCountdownTimer) clearInterval(idleCountdownTimer)

  window.removeEventListener('beforeunload', onBeforeUnload)

})



defineExpose({

  showOpenDialog,

  runStepAt,

  runFromStartThrough,

  runSelectedSteps,

  session,

  canRun,

})

</script>



<style scoped lang="scss">

.run-config-container {

  .config-section {

    margin-bottom: 18px;

  }

  .section-title {

    font-weight: 600;

    margin-bottom: 8px;

  }

  .env-cards {

    display: flex;

    flex-wrap: wrap;

    gap: 10px;

  }

  .env-card {

    border: 1px solid var(--el-border-color);

    border-radius: 8px;

    padding: 10px 14px;

    cursor: pointer;

    min-width: 140px;

    &.active {

      border-color: var(--el-color-primary);

      background: var(--el-color-primary-light-9);

    }

  }

  .env-name { font-weight: 600; }

  .env-host { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }

  .initial-url-hint {

    margin: 8px 0 0;

    font-size: 12px;

    color: var(--el-text-color-secondary);

    word-break: break-all;

  }

}



.debug-session-bar {

  margin: 12px 0 16px;

  padding: 10px 14px;

  border: 1px solid var(--el-color-primary-light-5);

  border-radius: 8px;

  background: var(--el-color-primary-light-9);

}

.bar-main {

  display: flex;

  align-items: center;

  justify-content: space-between;

  gap: 12px;

  flex-wrap: wrap;

}

.bar-left {

  display: flex;

  align-items: center;

  gap: 10px;

  flex-wrap: wrap;

}

.bar-meta, .bar-result {

  font-size: 13px;

  color: var(--el-text-color-regular);

}

.idle-hint {

  color: var(--el-text-color-secondary);

}

.pick-frame-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}

.bar-result.is-fail { color: var(--el-color-danger); }

.bar-result.is-ok { color: var(--el-color-success); }

.bar-actions {

  display: flex;

  gap: 8px;

  flex-wrap: wrap;

}

.pick-dialog-tip {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.pick-candidates {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.pick-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pick-tag {
  cursor: pointer;
}

.stale-alert {

  margin-top: 10px;

}

.result-panel {

  margin-top: 12px;

  border-top: 1px dashed var(--el-border-color);

  padding-top: 10px;

}

.result-panel-head {

  display: flex;

  align-items: center;

  justify-content: space-between;

  cursor: pointer;

  font-size: 13px;

  font-weight: 600;

  color: var(--el-text-color-primary);

}

.result-steps {

  margin-top: 10px;

  display: flex;

  flex-direction: column;

  gap: 8px;

}

.result-step-item {

  padding: 8px 10px;

  border-radius: 6px;

  border: 1px solid var(--el-border-color-lighter);

  background: #fff;

  cursor: pointer;

  &.is-success { border-left: 3px solid var(--el-color-success); }

  &.is-fail { border-left: 3px solid var(--el-color-danger); }

}

.result-step-head {

  display: flex;

  align-items: center;

  gap: 8px;

  flex-wrap: wrap;

}

.result-step-no {

  font-weight: 600;

  font-size: 13px;

}

.result-step-kw {

  font-size: 12px;

  color: var(--el-text-color-secondary);

}

.result-step-msg {

  margin: 6px 0 0;

  font-size: 12px;

  color: var(--el-color-danger);

  word-break: break-word;

}

.result-step-shot {

  margin-top: 8px;

  max-width: 280px;

  max-height: 160px;

  border-radius: 4px;

  border: 1px solid var(--el-border-color-lighter);

}

</style>


