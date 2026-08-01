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
          <el-button size="small" :loading="locatorBusy" :disabled="!canRun" @click="clearHighlight">
            取消高亮
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

            执行当前步

          </el-button>

          <el-button size="small" :loading="running" :disabled="!canRun" @click="runThroughStep">

            从当前步执行至末尾

          </el-button>

          <el-button size="small" @click="hotkeyDialogVisible = true">
            快捷键设置
          </el-button>
          <el-button size="small" type="danger" plain :loading="closing" @click="closeSession">

            关闭浏览器

          </el-button>

        </div>

      </div>

      <el-dialog v-model="hotkeyDialogVisible" title="交互调试快捷键" width="560px" destroy-on-close>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="此处修改会保存到本机浏览器，并在打开/更新调试会话时下发到 Runner。执行器客户端设置里也可改本机默认。"
          style="margin-bottom: 12px"
        />
        <div v-for="action in hotkeyActionList" :key="action" class="hotkey-row">
          <span class="hotkey-label">{{ hotkeyActionLabels[action] }}</span>
          <el-input
            :model-value="hotkeyDraft[action] || '未绑定'"
            readonly
            class="hotkey-input"
            @keydown="onHotkeyCapture(action, $event)"
            placeholder="点击后按下组合键"
          />
          <el-button link type="danger" @click="clearHotkey(action)">清空</el-button>
        </div>
        <template #footer>
          <el-button @click="resetHotkeysDraft">恢复默认</el-button>
          <el-button @click="hotkeyDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="hotkeySaving" @click="saveHotkeys">保存</el-button>
        </template>
      </el-dialog>



      <el-alert

        v-if="stepsStale"

        type="warning"

        :closable="false"

        show-icon

        class="stale-alert"

        title="编辑器步骤已变更时会自动同步到 Runner；平台侧执行 / 高亮 / 验证也会先同步。若仍提示不一致，可手动点「同步最新步骤」。"

      />

      <el-alert
        v-if="pickModeActive"
        type="warning"
        :closable="false"
        show-icon
        class="stale-alert"
        title="推荐：先手动悬停/等短弹窗 →「冻结页面」（默认 Ctrl+Shift+F，可在快捷键设置修改）→ 再点目标。直接「拾取」适合抓默认态"
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

    <el-dialog v-model="pickDialogVisible" title="拾取元素 — 回填定位器" width="680px" destroy-on-close>
      <p class="pick-dialog-tip">选择定位器用途：替换某个步骤，或在指定位置新增一步。</p>
      <p v-if="pickPreview.frame" class="pick-frame-hint">iframe：{{ pickPreview.frame }}</p>
      <p v-if="pickMatchIndex > 1" class="pick-frame-hint">
        同名匹配下标：{{ pickMatchIndex }}（写入步骤 params.index；若定位器已唯一可改为 1）
      </p>
      <p v-else-if="pickMatchIndex === 1" class="pick-index-hint">匹配下标：1</p>

      <div class="pick-apply-form">
        <div class="pick-form-row">
          <span class="pick-form-label">应用方式</span>
          <el-radio-group v-model="pickApplyMode" size="small">
            <el-radio-button value="replace">替换已有步骤</el-radio-button>
            <el-radio-button value="insert">新增步骤</el-radio-button>
          </el-radio-group>
        </div>
        <div class="pick-form-row">
          <span class="pick-form-label">{{ pickApplyMode === 'insert' ? '插入位置' : '目标步骤' }}</span>
          <el-select v-model="pickTargetStepIndex" size="small" style="width: 100%" filterable>
            <el-option
              v-for="(step, idx) in (steps || [])"
              :key="step.id || idx"
              :label="`步骤 ${idx + 1} · ${step.desc || step.keyword || step.method || '未命名'}`"
              :value="idx"
            />
            <el-option
              v-if="pickApplyMode === 'insert'"
              :label="`末尾（第 ${(steps?.length || 0) + 1} 步）`"
              :value="steps?.length || 0"
            />
          </el-select>
        </div>
        <div v-if="pickApplyMode === 'insert'" class="pick-form-row">
          <span class="pick-form-label">新步骤类型</span>
          <el-select v-model="pickInsertMethod" size="small" style="width: 220px">
            <el-option label="点击元素" value="click_ele" />
            <el-option label="元素输入" value="fill_value" />
            <el-option label="悬停元素" value="hover" />
          </el-select>
        </div>
      </div>

      <el-input v-model="pickPreview.locator" type="textarea" :rows="3" class="pick-locator-input" />
      <div v-if="pickPreview.candidates?.length" class="pick-candidates">
        <span class="pick-label">候选定位器（点击选用）：</span>
        <el-tag
          v-for="(item, idx) in pickPreview.candidates"
          :key="idx"
          size="small"
          :type="item === pickPreview.locator ? 'primary' : 'info'"
          class="pick-tag"
          @click="selectPickCandidate(item)"
        >{{ item }}</el-tag>
      </div>
      <template #footer>
        <el-button @click="pickDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmApplyPick">
          {{ pickApplyMode === 'insert' ? '新增并写入定位器' : '应用到选中步' }}
        </el-button>
      </template>
    </el-dialog>

  </div>

</template>



<script setup>

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { ElMessage, ElNotification } from 'element-plus'

import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'

import { ProjectStore } from '@/stores/module/ProjectStore.js'

import { UserStore } from '@/stores/module/UserStore.js'

import http from '@/api/index'

import { uiDebugApi } from '@/api/modules/ui.js'

import { filterWebRunnerDevices } from '@/utils/runnerDevice'

import { buildDebugRunningHints, buildDebugExecutionHints, mergeDebugExecutionHints, formatDebugStepStatus, formatIdleRemaining, buildSessionToEditorMap, mapSessionStepResultsToEditor, mergeDebugRunStepResults, groupContiguousStepIndices } from '@/utils/debugSession.js'

import { resolveDefaultStartUrl } from '@/utils/caseDescription.js'

import { formatLocatorActionSummary, pickResultKey, splitCombinedLocator, stepHasLocator, suggestPickStepTemplate } from '@/utils/debugLocator.js'

import {
  DEFAULT_HOTKEYS,
  HOTKEY_ACTIONS,
  HOTKEY_ACTION_LABELS,
  comboFromKeyboardEvent,
  getSessionHotkeyOverride,
  loadStoredHotkeys,
  mergeHotkeys,
  saveStoredHotkeys,
} from '@/utils/uiDebugHotkeys.js'




const props = defineProps({

  caseId: { type: [String, Number], required: true },

  steps: { type: Array, default: () => [] },

  selectedStepIndex: { type: Number, default: 0 },

})



const emit = defineEmits([
  'session-change',
  'debug-hints-change',
  'focus-step',
  'apply-locator',
  'run-selected-request',
])



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
const hotkeyDialogVisible = ref(false)
const hotkeySaving = ref(false)
const hotkeyActionList = HOTKEY_ACTIONS
const hotkeyActionLabels = HOTKEY_ACTION_LABELS
const hotkeyDraft = reactive({ ...DEFAULT_HOTKEYS })

const pickDialogVisible = ref(false)
const pickPreview = reactive({ locator: '', frame: '', element_locator: '', candidates: [], meta: {} })
const pickMatchIndex = computed(() => {
  const raw = pickPreview.meta?.matchIndex ?? pickPreview.meta?.match_index ?? 1
  const n = Number(raw)
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1
})
const pickPollTimer = ref(null)
const pickApplyMode = ref('replace')
const pickTargetStepIndex = ref(0)
const pickInsertMethod = ref('click_ele')
const ignoredPickKey = ref('')
const handledPickKey = ref('')
const handledFeedbackKey = ref('')
const handledRunSelectedKey = ref('')
const handledPickFreezeKey = ref('')
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

  if (['pick_freeze', 'page_freeze', 'run_selected_request', 'recording', 'record_stopped', 'closed'].includes(result.type)) {
    return ''
  }

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

  if (result?.type === 'clear_highlight') return 'info'

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



const previewInitialUrl = computed(() => resolveDefaultStartUrl({
  steps: props.steps,
  envId: openForm.env_id,
  envList: proStore.envList,
  projectInfo: proStore.projectInfo,
}))



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



const lastSyncedSelectKey = ref('')
let selectStepSyncTimer = null

watch(session, (val, oldVal) => {

  emit('session-change', val)

  if (val?.id !== oldVal?.id) {
    lastSyncedSelectKey.value = ''
  }

  const becameReady = val?.id && val?.status === 'ready' && oldVal?.status !== 'ready'
  if (becameReady) {

    scheduleCheckStepsStale()
    scheduleSyncSelectedStepToRunner(props.selectedStepIndex)

  } else if (val?.id && val?.status === 'ready') {

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

watch(() => props.selectedStepIndex, (idx) => {
  if (session.value?.status === 'ready') {
    scheduleSyncSelectedStepToRunner(idx)
  }
})



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



function resolveDebugCloseNotice(data) {
  if (!data || data.status !== 'closed') return null
  const closed = data.last_result?.type === 'closed' ? data.last_result : null
  const message = closed?.message || data.error || '调试浏览器已关闭'
  const reason = closed?.reason || ''
  return { message, reason }
}



function notifyDebugSessionClosed(data) {
  const notice = resolveDebugCloseNotice(data)
  if (!notice) return
  if (notice.reason === 'browser_closed_by_user') {
    ElNotification.warning(notice.message)
    return
  }
  if (notice.reason === 'idle_timeout' || notice.reason === '空闲超时自动关闭' || notice.reason === 'runner_idle_timeout') {
    ElNotification.info(notice.message)
    return
  }
  if (notice.reason === 'force_closed' || (notice.reason && notice.reason.includes('关闭超时'))) {
    ElNotification.warning(notice.message)
    return
  }
  ElNotification.info(notice.message)
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

    // 变更后自动同步，保证浏览器工具条也用最新步骤（执行/高亮前另有兜底）
    if (
      stepsStale.value
      && session.value?.status === 'ready'
      && !running.value
      && !syncing.value
    ) {
      const synced = await syncStepsFromEditor({ silent: true })
      if (synced) {
        lastSyncedSelectKey.value = ''
        await syncSelectedStepToRunner(props.selectedStepIndex)
      }
    }

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
  // 调试默认按编辑器最新步骤执行：不一致时自动同步，不再弹确认框
  const synced = await syncStepsFromEditor({ quiet: true })
  if (!synced) {
    ElMessage.warning('自动同步最新步骤失败，请手动点「同步最新步骤」后重试')
  }
  return synced
}

async function syncStepsFromEditor({ quiet = false, silent = false } = {}) {
  if (!session.value?.id) return false
  syncing.value = true
  try {
    await uiDebugApi.syncSteps(session.value.id, { steps: props.steps })
    const status = await waitUntilReady()
    if (status === 'ready') {
      stepsStale.value = false
      mergedLastResult.value = null
      if (!silent) {
        if (quiet) {
          ElMessage.success('已自动同步最新步骤')
        } else {
          ElNotification.success('步骤已同步到 Runner')
        }
      }
      return true
    }
    return false
  } catch (e) {
    if (!silent) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '同步步骤失败')
    }
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

    const hotkeyOverride = getSessionHotkeyOverride(uStore.userInfo?.id)
    const createPayload = {
      case_id: Number(props.caseId),
      env_id: openForm.env_id,
      browser_type: openForm.browser_type,
      config: false,
      device_id: openForm.device_id,
      steps: props.steps,
      auto_navigate: openForm.auto_navigate,
    }
    // 未在平台保存过快捷键时不下发，避免用默认表盖住执行器客户端偏好
    if (hotkeyOverride) createPayload.hotkeys = hotkeyOverride
    const res = await uiDebugApi.createSession(createPayload)

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
  const valid = normalizeEditorIndices(editorIndices)
  if (!valid.length) {
    throw new Error('所选步骤下标无效')
  }
  const res = await uiDebugApi.resolveRunSegments(session.value.id, {
    steps: props.steps,
    editor_indices: valid,
  })
  const data = parseCompareResponse(res)
  const segments = (data?.segments || []).map((row) => [row.from_index, row.through_index])
  return {
    segments,
    editorMap: data?.editor_map || [],
    stale: !!data?.stale,
  }
}

/** 未选中（-1）时调试工具条默认对齐第 0 步，避免把 -1 传给后端 */
function effectiveEditorStepIndex(editorIndex = props.selectedStepIndex) {
  const idx = Number(editorIndex)
  const len = props.steps?.length || 0
  if (!len) return -1
  if (!Number.isFinite(idx) || idx < 0) return 0
  if (idx >= len) return len - 1
  return idx
}

async function resolveEditorStepSessionIndex(editorIndex) {
  const idx = effectiveEditorStepIndex(editorIndex)
  if (idx < 0) return 0
  try {
    const plan = await resolveEditorRunPlan([idx])
    if (plan.stale) return idx
    const first = plan.segments[0]
    return first ? first[0] : idx
  } catch {
    return idx
  }
}

function normalizeEditorIndices(indices) {
  return [...new Set((indices || []).map((i) => Number(i)))]
    .filter((i) => !Number.isNaN(i) && i >= 0 && i < props.steps.length)
    .sort((a, b) => a - b)
}

async function runSessionSegment(fromIndex, throughIndex, timeoutMs) {
  if (!session.value?.id) return false
  const stepCount = Math.max(1, throughIndex - fromIndex + 1)
  // 多步回放常超过默认 120s；按步数放宽，避免「从这里开始录制」前置回放假死
  const readyTimeout = timeoutMs ?? Math.max(120000, stepCount * 45000)
  try {
    await uiDebugApi.runSteps(session.value.id, { from_index: fromIndex, through_index: throughIndex })
    const status = await waitUntilReady(readyTimeout)
    if (status === 'ready') {
      return true
    }
    if (status === 'error') {
      ElMessage.error(session.value?.error || '调试执行异常')
    } else if (status === 'running') {
      ElMessage.warning(`执行超时（已等待 ${Math.round(readyTimeout / 1000)} 秒），请查看调试浏览器或缩短回放区间`)
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
    let plan = await resolveEditorRunPlan(valid)
    // 竞态兜底：标记未刷新但后端仍报 stale 时，再自动同步一次后重解析
    if (plan.stale) {
      const synced = await syncStepsFromEditor({ quiet: true })
      if (synced) {
        plan = await resolveEditorRunPlan(valid)
      }
    }
    if (plan.stale) {
      ElMessage.warning('步骤与会话仍不一致，将按编辑器下标直接执行；建议手动同步后重试')
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
  if (Number(props.selectedStepIndex) < 0) {
    ElMessage.warning('请先选中一个步骤')
    return Promise.resolve(false)
  }
  return runEditorIndices([props.selectedStepIndex])
}

function runThroughStep() {
  const idx = Number(props.selectedStepIndex)
  if (!Number.isFinite(idx) || idx < 0) {
    ElMessage.warning('请先选中一个步骤')
    return Promise.resolve(false)
  }
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

    } else if (status !== 'closed') {

      ElNotification.info('调试浏览器已关闭')

    }

  } catch (e) {

    ElMessage.error(e?.response?.data?.detail || e?.message || '关闭失败')

  } finally {

    closing.value = false

  }

}



function consumePickResultFromSession() {
  const result = session.value?.last_result
  if (result?.type !== 'pick' || !result.locator) return false
  const key = pickResultKey(result)
  if (!key || key === ignoredPickKey.value || key === handledPickKey.value) return false
  if (pickDialogVisible.value) return false
  handledPickKey.value = key
  ignoredPickKey.value = key
  const keepFrozenPick = !!(result.page_frozen || result.keep_pick_mode)
  if (keepFrozenPick) {
    // 冻结中连续拾取：保持拾取轮询，不自动解冻
    pickModeActive.value = true
    startPickPolling()
  } else {
    pickModeActive.value = false
    stopPickPolling()
  }
  openPickDialog(result)
  return true
}

function locatorFeedbackKey(result) {
  if (!result?.type) return ''
  return [
    result.type,
    result.status || '',
    result.step_index ?? '',
    result.message || '',
    result.locator || '',
  ].join('|')
}

function markLocatorFeedbackHandled(result) {
  const key = locatorFeedbackKey(result)
  if (key) handledFeedbackKey.value = key
}

function surfaceLocatorFeedbackFromSession() {
  const result = session.value?.last_result
  if (!result?.type) return
  if (!['highlight', 'verify', 'clear_highlight'].includes(result.type)) return
  const key = locatorFeedbackKey(result)
  if (!key || key === handledFeedbackKey.value) return
  handledFeedbackKey.value = key
  const msg = formatLocatorActionSummary(result) || result.message
  if (!msg) return
  if (result.type === 'clear_highlight') {
    ElMessage.info(msg)
    return
  }
  if (result.status === 'success') {
    ElMessage.success(msg)
  } else if (result.status === 'ambiguous') {
    ElMessage.warning(msg)
  } else {
    ElMessage.error(msg)
  }
}

function consumePickFreezeFromSession() {
  const result = session.value?.last_result
  if (!result?.type) return
  if (!['pick_freeze', 'page_freeze'].includes(result.type)) return
  const key = [
    result.type,
    result.frozen ? '1' : '0',
    result.message || '',
    result.request_id || '',
    result.hover_forced ?? '',
    result.pinned_ui ?? '',
  ].join('|')
  if (!key || key === handledPickFreezeKey.value) return
  handledPickFreezeKey.value = key
  if (result.type === 'page_freeze') {
    pickModeActive.value = !!result.pick_mode
    if (result.pick_mode) startPickPolling()
    else stopPickPolling()
  }
  const msg = result.message || (result.frozen ? '页面已冻结' : '已解冻')
  if (result.status === 'fail') {
    ElMessage.error(msg)
  } else if (result.frozen) {
    ElMessage.success(msg)
  } else {
    ElMessage.info(msg)
  }
}

function consumeRunSelectedRequestFromSession() {
  const result = session.value?.last_result
  if (result?.type !== 'run_selected_request') return
  if (result.status === 'fail') {
    const key = locatorFeedbackKey(result)
    if (key && key !== handledRunSelectedKey.value) {
      handledRunSelectedKey.value = key
      ElMessage.error(result.message || '工具条「执行勾选」失败')
    }
    return
  }
  const key = result.request_id || locatorFeedbackKey(result)
  if (!key || key === handledRunSelectedKey.value) return
  handledRunSelectedKey.value = key
  emit('run-selected-request', { requestId: key })
}

async function refreshSession() {

  if (!session.value?.id) return

  try {

    const res = await uiDebugApi.getSession(session.value.id)

    session.value = parseSessionResponse(res)

    syncIdleBaseline(session.value)

    if (session.value?.status === 'closed') {

      notifyDebugSessionClosed(session.value)

      stopPolling()

      session.value = null

      stepsStale.value = false

    } else if (session.value?.status === 'error') {

      stopPolling()

    } else {
      consumePickResultFromSession()
      consumePickFreezeFromSession()
      consumeRunSelectedRequestFromSession()
      // 平台侧主动 await 的高亮/验证会自行弹消息，避免重复；仅工具条/闲时轮询补提示
      if (!locatorBusy.value) {
        surfaceLocatorFeedbackFromSession()
      }
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

async function clearHighlight() {
  if (!session.value?.id || !canRun.value) return
  locatorBusy.value = true
  try {
    await uiDebugApi.clearHighlight(session.value.id)
    const result = await waitForLocatorResult()
    markLocatorFeedbackHandled(result)
    ElMessage.success('已取消高亮')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '取消高亮失败')
  } finally {
    locatorBusy.value = false
  }
}

function scheduleSyncSelectedStepToRunner(editorIndex = props.selectedStepIndex) {
  if (selectStepSyncTimer) {
    clearTimeout(selectStepSyncTimer)
    selectStepSyncTimer = null
  }
  selectStepSyncTimer = setTimeout(() => {
    selectStepSyncTimer = null
    syncSelectedStepToRunner(editorIndex)
  }, 120)
}

async function syncSelectedStepToRunner(editorIndex = props.selectedStepIndex) {
  if (!session.value?.id || session.value.status !== 'ready') return
  if (!(props.steps?.length > 0)) return
  const idx = effectiveEditorStepIndex(editorIndex)
  try {
    const sessionIndex = await resolveEditorStepSessionIndex(idx)
    if (!Number.isFinite(sessionIndex) || sessionIndex < 0) return
    const key = `${session.value.id}:${sessionIndex}`
    if (key === lastSyncedSelectKey.value) return
    lastSyncedSelectKey.value = key
    await uiDebugApi.selectStep(session.value.id, { step_index: sessionIndex })
  } catch {
    // 同步选中步失败不阻断操作；允许下次重试
    lastSyncedSelectKey.value = ''
  }
}

async function highlightSelectedStep() {
  if (!session.value?.id || !canLocatorAction.value) return
  locatorBusy.value = true
  try {
    // 高亮/验证必须用编辑器最新定位器；步骤已变更时先同步
    if (stepsStale.value) {
      const synced = await syncStepsFromEditor({ quiet: true })
      if (!synced) {
        ElMessage.warning('请先同步步骤后再高亮')
        return
      }
    }
    const sessionIndex = await resolveEditorStepSessionIndex(props.selectedStepIndex)
    await uiDebugApi.highlightStep(session.value.id, { step_index: sessionIndex })
    const result = await waitForLocatorResult()
    markLocatorFeedbackHandled(result)
    if (result?.type === 'highlight' && result.status !== 'success') {
      ElMessage.error(result.message || '高亮失败')
    } else if (result?.type === 'highlight') {
      ElMessage.success(formatLocatorActionSummary(result) || '高亮成功')
    }
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
    if (stepsStale.value) {
      const synced = await syncStepsFromEditor({ quiet: true })
      if (!synced) {
        ElMessage.warning('请先同步步骤后再验证')
        return
      }
    }
    const sessionIndex = await resolveEditorStepSessionIndex(props.selectedStepIndex)
    await uiDebugApi.verifyLocator(session.value.id, { step_index: sessionIndex })
    const result = await waitForLocatorResult()
    markLocatorFeedbackHandled(result)
    const msg = formatLocatorActionSummary(result) || result?.message
    if (result?.status === 'success') {
      ElMessage.success(msg || '验证成功')
    } else if (result?.status === 'ambiguous') {
      ElMessage.warning(msg || '定位器匹配多个元素')
    } else {
      ElMessage.error(msg || '验证失败')
    }
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
  pickPreview.candidates = payload.candidates || payload.meta?.candidates || []
  pickPreview.meta = payload.meta || {}
  pickApplyMode.value = 'replace'
  const sel = Number(props.selectedStepIndex)
  pickTargetStepIndex.value = Number.isFinite(sel) && sel >= 0 ? sel : 0
  const suggested = suggestPickStepTemplate(payload.meta || payload.element || {})
  pickInsertMethod.value = suggested.method || 'click_ele'
  pickDialogVisible.value = true
}

function startPickPolling() {
  stopPickPolling()
  pickPollTimer.value = setInterval(async () => {
    await refreshSession()
    if (consumePickResultFromSession()) {
      // refreshSession 内已处理；此处再调一次无副作用（已 handled）
    }
  }, 1200)
}


function loadHotkeyDraft() {
  Object.assign(hotkeyDraft, loadStoredHotkeys(uStore.userInfo?.id))
}

function onHotkeyCapture(action, e) {
  e.preventDefault()
  e.stopPropagation()
  const combo = comboFromKeyboardEvent(e)
  if (!combo) return
  // 冲突：清空占用者
  for (const key of hotkeyActionList) {
    if (key !== action && hotkeyDraft[key] === combo) hotkeyDraft[key] = ''
  }
  hotkeyDraft[action] = combo
}

function clearHotkey(action) {
  hotkeyDraft[action] = ''
}

function resetHotkeysDraft() {
  Object.assign(hotkeyDraft, { ...DEFAULT_HOTKEYS })
}

async function saveHotkeys() {
  hotkeySaving.value = true
  try {
    const merged = saveStoredHotkeys(uStore.userInfo?.id, hotkeyDraft)
    Object.assign(hotkeyDraft, merged)
    if (session.value?.status === 'ready') {
      await uiDebugApi.setHotkeys(session.value.id, { hotkeys: merged })
      await waitUntilReady()
      ElMessage.success('快捷键已保存并同步到调试浏览器')
    } else if (session.value) {
      ElMessage.warning('快捷键已保存到本机；请等会话就绪后再保存一次以同步到调试浏览器')
    } else {
      ElMessage.success('快捷键已保存；下次打开调试会话时生效')
    }
    hotkeyDialogVisible.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存快捷键失败')
  } finally {
    hotkeySaving.value = false
  }
}

watch(hotkeyDialogVisible, (v) => { if (v) loadHotkeyDraft() })

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
    await refreshSession()
    // 忽略会话里上一次拾取结果，避免再次开启就立刻弹窗
    const stale = session.value?.last_result
    if (stale?.type === 'pick') {
      ignoredPickKey.value = pickResultKey(stale)
    }
    await uiDebugApi.setPickMode(session.value.id, { enabled: true })
    await waitUntilReady()
    pickModeActive.value = true
    startPickPolling()
    ElNotification.info({
      title: '拾取模式',
      message: '直接拾取≈防悬停抓默认态。悬停后/短弹窗：先操作再「冻结页面」（快捷键可在「快捷键设置」查看），然后拾取；结果在平台面板回填。',
      duration: 8000,
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '开启拾取失败')
  } finally {
    pickModeLoading.value = false
  }
}

function pickInsertTemplate() {
  if (pickInsertMethod.value === 'fill_value') {
    return {
      keyword: '元素输入',
      method: 'fill_value',
      params: { locator: '', value: '', timeout: 20000 },
    }
  }
  if (pickInsertMethod.value === 'hover') {
    return {
      keyword: '鼠标悬停到元素上方',
      method: 'hover',
      params: { locator: '', index: 1, timeout: 20000 },
    }
  }
  return {
    keyword: '点击元素',
    method: 'click_ele',
    params: {
      locator: '',
      index: 1,
      force: false,
      timeout: 20000,
      wait_download: false,
      save_path: '',
      var_name: '',
      download_timeout: 60000,
      accept_dialog: false,
      dismiss_dialog: false,
      dialog_timeout: 10000,
      prompt_text: '',
    },
  }
}

async function confirmApplyPick() {
  if (!pickPreview.locator) {
    ElMessage.warning('定位器为空')
    return
  }
  const stepCount = props.steps?.length || 0
  let stepIndex = Number(pickTargetStepIndex.value)
  if (pickApplyMode.value === 'replace') {
    if (!Number.isFinite(stepIndex) || stepIndex < 0 || stepIndex >= stepCount) {
      ElMessage.warning('请选择有效的目标步骤')
      return
    }
    emit('apply-locator', {
      mode: 'replace',
      stepIndex,
      locator: pickPreview.locator,
      frame: pickPreview.frame,
      element_locator: pickPreview.element_locator,
      match_index: pickPreview.meta?.matchIndex || 1,
      candidates: pickPreview.candidates,
      meta: pickPreview.meta,
    })
  } else {
    if (!Number.isFinite(stepIndex) || stepIndex < 0) stepIndex = stepCount
    stepIndex = Math.min(Math.max(0, stepIndex), stepCount)
    emit('apply-locator', {
      mode: 'insert',
      insertAt: stepIndex,
      template: pickInsertTemplate(),
      locator: pickPreview.locator,
      frame: pickPreview.frame,
      element_locator: pickPreview.element_locator,
      match_index: pickPreview.meta?.matchIndex || 1,
      candidates: pickPreview.candidates,
      meta: pickPreview.meta,
    })
  }
  pickDialogVisible.value = false
  // 工具条高亮/验证读的是 Runner 会话快照；拾取回填后必须同步，否则浏览器内操作条仍用旧步骤
  await nextTick()
  if (session.value?.status === 'ready') {
    lastSyncedSelectKey.value = ''
    const synced = await syncStepsFromEditor()
    if (synced) {
      await syncSelectedStepToRunner(props.selectedStepIndex)
    } else {
      ElMessage.warning('定位器已回填，但同步到调试会话失败；请点「同步最新步骤」后再用工具条高亮')
    }
  }
}



async function resumeActiveSession() {
  if (!props.caseId) return
  try {
    const res = await uiDebugApi.getActiveSession({ case_id: Number(props.caseId) })
    const data = parseSessionResponse(res)
    if (!data?.id || ['closed', 'error'].includes(data.status)) return
    session.value = data
    syncIdleBaseline(data)
    // 恢复会话时忽略历史拾取/高亮结果，避免立刻弹出旧窗或刷提示
    const stale = data.last_result
    if (stale?.type === 'pick') {
      const key = pickResultKey(stale)
      ignoredPickKey.value = key
      handledPickKey.value = key
    }
    if (stale && ['highlight', 'verify', 'clear_highlight'].includes(stale.type)) {
      markLocatorFeedbackHandled(stale)
    }
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

  if (selectStepSyncTimer) {
    clearTimeout(selectStepSyncTimer)
    selectStepSyncTimer = null
  }

  if (staleCheckTimer.value) clearTimeout(staleCheckTimer.value)

  if (idleCountdownTimer) clearInterval(idleCountdownTimer)

  window.removeEventListener('beforeunload', onBeforeUnload)

})



defineExpose({

  showOpenDialog,

  runStepAt,

  runFromStartThrough,

  runSelectedSteps,

  syncSelectedStepToRunner,

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
.pick-index-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
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
.pick-apply-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.pick-form-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pick-form-label {
  flex: 0 0 72px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.pick-locator-input {
  margin-top: 4px;
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
  max-width: 100%;
  height: auto;
  white-space: normal;
  line-height: 1.4;
  padding: 4px 8px;
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


.hotkey-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.hotkey-label {
  width: 120px;
  flex-shrink: 0;
  font-size: 13px;
}
.hotkey-input {
  flex: 1;
}
</style>



