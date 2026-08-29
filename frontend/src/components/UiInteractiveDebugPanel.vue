<template>

  <div class="interactive-debug">

    <el-dialog

      v-model="openDialogVisible"

      title="交互调试 — 打开浏览器"

      width="760px"

      destroy-on-close

      @open="onDialogOpen"

      @closed="onOpenDialogClosed"

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

          <el-tooltip content="按当前选中步骤的定位器，在调试浏览器中高亮目标元素" placement="top" :show-after="300">
            <el-button size="small" :loading="locatorBusy" :disabled="!canLocatorAction" @click="highlightSelectedStep">
              高亮定位器
            </el-button>
          </el-tooltip>
          <el-tooltip content="清除调试浏览器中的定位器高亮" placement="top" :show-after="300">
            <el-button size="small" :loading="locatorBusy" :disabled="!canRun" @click="clearHighlight">
              取消高亮
            </el-button>
          </el-tooltip>
          <el-tooltip content="验证当前步骤定位器是否能匹配到可见元素（多匹配会提示）" placement="top" :show-after="300">
            <el-button size="small" :loading="locatorBusy" :disabled="!canLocatorAction" @click="verifySelectedStep">
              验证定位器
            </el-button>
          </el-tooltip>
          <el-tooltip
            content="在调试浏览器中拾取元素并回填到步骤；悬浮/下拉可先「冻结页面」再确认。也可用浏览器底部操作条"
            placement="top"
            :show-after="300"
          >
            <el-button
              size="small"
              :type="pickModeActive ? 'warning' : 'default'"
              :loading="pickModeLoading"
              :disabled="!canRun"
              @click="togglePickMode"
            >
              {{ pickModeActive ? '退出拾取' : '拾取元素' }}
            </el-button>
          </el-tooltip>
          <el-tooltip content="只执行当前选中的一步；浏览器操作条「执行本步」效果相同，结果会同步到步骤状态" placement="top" :show-after="300">
            <el-button size="small" :loading="running" :disabled="!canRun" @click="runSingleStep">
              执行当前步
            </el-button>
          </el-tooltip>

          <el-tooltip content="从当前选中步连续执行到用例末尾；浏览器操作条「执行至末尾」效果相同" placement="top" :show-after="300">
            <el-button size="small" :loading="running" :disabled="!canRun" @click="runThroughStep">
              从当前步执行至末尾
            </el-button>
          </el-tooltip>

          <el-tooltip content="自定义调试浏览器操作条快捷键，保存后会下发到当前会话" placement="top" :show-after="300">
            <el-button size="small" @click="hotkeyDialogVisible = true">
              快捷键设置
            </el-button>
          </el-tooltip>
          <el-tooltip content="关闭调试浏览器并结束本次交互调试会话" placement="top" :show-after="300">
            <el-button size="small" type="danger" plain :loading="closing" @click="closeSession">
              关闭浏览器
            </el-button>
          </el-tooltip>
          <el-tooltip placement="top" :show-after="200">
            <template #content>
              <div style="max-width: 280px; line-height: 1.5">
                调试浏览器底部操作条可「执行本步 / 执行至末尾 / 高亮 / 验证 / 拾取」。执行完成后浏览器内会弹出结果提示，步骤成功/失败状态会同步到本页卡片（约 1～2 秒内刷新）。
              </div>
            </template>
            <el-icon class="debug-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>

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
            <div v-else-if="item.variables?.length" class="result-step-msg">
              <div v-for="(v, vi) in item.variables" :key="`${v.name}-${vi}`">
                {{ v.name }} = {{ typeof v.value === 'string' ? v.value : JSON.stringify(v.value) }}
              </div>
            </div>
            <p v-else-if="item.result != null && item.result !== ''" class="result-step-msg">
              结果：{{ typeof item.result === 'string' ? item.result : JSON.stringify(item.result) }}
            </p>

          </div>

        </div>

      </div>

    </div>

    <el-dialog v-model="pickDialogVisible" title="拾取元素 — 回填定位器" width="680px" destroy-on-close>
      <p class="pick-dialog-tip">相对参照步骤：可在其前/后新增，或直接替换该步定位器。</p>
      <p v-if="pickPreview.frame" class="pick-frame-hint">iframe：{{ pickPreview.frame }}</p>
      <p v-if="pickMatchIndex > 1" class="pick-frame-hint">
        同名匹配下标：{{ pickMatchIndex }}（写入步骤 params.index；若定位器已唯一可改为 1）
      </p>
      <p v-else-if="pickMatchIndex === 1" class="pick-index-hint">匹配下标：1</p>

      <div class="pick-apply-form">
        <div class="pick-form-row">
          <span class="pick-form-label">应用方式</span>
          <el-radio-group v-model="pickPlaceMode" size="small">
            <el-radio-button value="before" :disabled="!pickHasSteps">步骤前插入</el-radio-button>
            <el-radio-button value="after">步骤后插入</el-radio-button>
            <el-radio-button value="replace" :disabled="!pickHasSteps">替换该步骤</el-radio-button>
          </el-radio-group>
        </div>
        <div class="pick-form-row">
          <span class="pick-form-label">参照步骤</span>
          <el-select
            v-model="pickTargetStepIndex"
            size="small"
            style="width: 100%"
            filterable
            :disabled="!pickHasSteps && pickPlaceMode !== 'after'"
          >
            <el-option
              v-for="(step, idx) in (steps || [])"
              :key="step.id || idx"
              :label="`步骤 ${idx + 1} · ${step.desc || step.keyword || step.method || '未命名'}`"
              :value="idx"
            />
            <el-option
              v-if="pickPlaceMode === 'after'"
              :label="pickHasSteps ? `末尾（第 ${(steps?.length || 0) + 1} 步）` : '作为第 1 步'"
              :value="steps?.length || 0"
            />
          </el-select>
        </div>
        <p v-if="pickPlaceHint" class="pick-place-hint">{{ pickPlaceHint }}</p>
        <div v-if="pickPlaceMode !== 'replace'" class="pick-form-row">
          <span class="pick-form-label">新步骤类型</span>
          <el-select v-model="pickInsertMethod" size="small" style="width: 220px">
            <el-option label="点击元素" value="click_ele" />
            <el-option label="元素输入" value="fill_value" />
            <el-option
              v-if="pickPreview.frame"
              label="iframe内元素输入"
              value="frame_fill_value"
            />
            <el-option label="悬停元素" value="hover" />
          </el-select>
        </div>
      </div>

      <el-input v-model="pickPreview.locator" type="textarea" :rows="3" class="pick-locator-input" />
      <el-alert
        v-if="pickShellWarning"
        type="warning"
        :closable="false"
        show-icon
        class="pick-shell-warning"
        title="当前定位停在输入组件外壳，fill 可能失败；建议改选带「语义 / 可填」标签的候选，或落到 input.el-input__inner。"
      />
      <div v-if="pickPreview.candidates?.length" class="pick-candidates">
        <span class="pick-label">候选定位器（点击选用）：</span>
        <el-tag
          v-for="(item, idx) in pickPreview.candidates"
          :key="idx"
          size="small"
          :type="item === pickPreview.locator ? 'primary' : 'info'"
          class="pick-tag"
          @click="selectPickCandidate(item)"
        >{{ formatPickCandidateLabel(item) }}</el-tag>
      </div>
      <template #footer>
        <el-button @click="pickDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmApplyPick">
          {{ pickPlaceMode === 'replace' ? '应用到选中步' : '新增并写入定位器' }}
        </el-button>
      </template>
    </el-dialog>

  </div>

</template>



<script setup>

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { ElMessage, ElNotification } from 'element-plus'

import { ArrowDown, ArrowUp, QuestionFilled } from '@element-plus/icons-vue'

import { ProjectStore } from '@/stores/module/ProjectStore.js'

import { UserStore } from '@/stores/module/UserStore.js'

import http from '@/api/index'

import { uiDebugApi } from '@/api/modules/ui.js'

import { filterWebRunnerDevices } from '@/utils/runnerDevice'

import { buildDebugRunningHints, buildOptimisticRunningHints, buildDebugExecutionHints, mergeDebugExecutionHints, formatDebugStepStatus, formatIdleRemaining, buildSessionToEditorMap, mapSessionStepResultsToEditor, mergeDebugRunStepResults, groupContiguousStepIndices, fingerprintDebugRunResult, mapDebugRunResultToEditor, mergeIncomingDebugRunResult, formatStepOutcomeText } from '@/utils/debugSession.js'

import { resolveDefaultStartUrl } from '@/utils/caseDescription.js'

import { formatLocatorActionSummary, formatPickCandidateLabel, isInputShellLocator, pickResultKey, splitCombinedLocator, stepHasLocator, suggestPickStepTemplate } from '@/utils/debugLocator.js'

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
/** 打开浏览器请求世代号：弹窗取消时递增，丢弃进行中的 createSession 成功结果 */
let openSessionGen = 0

const opening = ref(false)

const running = ref(false)
/** 正在执行的编辑器步骤下标（乐观 UI，不依赖会话轮询） */
const localRunningEditorIndices = ref([])

const closing = ref(false)

const syncing = ref(false)
const pendingResync = ref(false)

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
/** before | after | replace — 相对参照步骤的落点 */
const pickPlaceMode = ref('after')
const pickTargetStepIndex = ref(0)
const pickInsertMethod = ref('click_ele')
const pickHasSteps = computed(() => (props.steps?.length || 0) > 0)
const pickPlaceHint = computed(() => {
  const n = props.steps?.length || 0
  let idx = Number(pickTargetStepIndex.value)
  if (!Number.isFinite(idx)) idx = 0
  if (pickPlaceMode.value === 'replace') {
    if (!n) return '当前无步骤，请改为插入'
    if (idx < 0 || idx >= n) return '请选择要替换的步骤'
    return `将更新步骤 ${idx + 1} 的定位器（不新增步骤）`
  }
  if (pickPlaceMode.value === 'before') {
    if (!n) return '将作为第 1 步写入'
    if (idx < 0 || idx >= n) return '请选择参照步骤'
    return `将在步骤 ${idx + 1} 之前插入新步骤（原步骤顺延）`
  }
  // after
  if (!n || idx >= n) return `将追加为第 ${n + 1} 步`
  return `将在步骤 ${idx + 1} 之后插入新步骤`
})
const pickShellWarning = computed(() => isInputShellLocator(pickPreview.locator))
const ignoredPickKey = ref('')
const handledPickKey = ref('')
const handledFeedbackKey = ref('')
const handledRunSelectedKey = ref('')
const handledPickFreezeKey = ref('')
const staleCheckTimer = ref(null)
const mergedLastResult = ref(null)
/** 已吸收的 session.last_result 指纹；避免平台多段合并结果被工具条/轮询覆盖，也避免挡住工具条新结果 */
const lastSeenRunFingerprint = ref('')
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
    const from = Number(r.from_index ?? 0) + 1
    const through = Number(r.through_index ?? from - 1) + 1
    if (from === through) {
      const step = r.steps.find((s) => Number(s?.step_index) === from - 1) || r.steps[0]
      const outcome = formatStepOutcomeText(step)
      const brief = outcome ? outcome.replace(/\s+/g, ' ').slice(0, 160) : ''
      return brief ? `第 ${from} 步成功 — ${brief}` : `第 ${from} 步执行成功`
    }
    return `第 ${from}～${through} 步执行成功`
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
  const optimistic = buildOptimisticRunningHints(localRunningEditorIndices.value)
  const runningHints = buildDebugRunningHints(session.value)
  let resultHints = null
  const sessionRun = session.value?.last_result?.type === 'run' ? session.value.last_result : null
  const merged = mergedLastResult.value

  // 工具条直报会更新 session.last_result（带 reported_at）；若比本地合并缓存新，优先用会话结果，避免卡片不刷新
  const sessionNewer = (() => {
    if (running.value || !sessionRun) return false
    if (!merged) return true
    const sAt = Number(sessionRun.reported_at)
    const mAt = Number(merged.reported_at)
    if (Number.isFinite(sAt) && Number.isFinite(mAt)) return sAt > mAt
    if (Number.isFinite(sAt) && !Number.isFinite(mAt)) return true
    return fingerprintDebugRunResult(sessionRun) !== fingerprintDebugRunResult(merged)
  })()

  if (sessionNewer) {
    const mapped = mapDebugRunResultToEditor(sessionRun, lastEditorMap.value) || sessionRun
    resultHints = buildDebugExecutionHints(mapped)
  } else if (merged) {
    resultHints = buildDebugExecutionHints(merged)
  } else if (sessionRun) {
    const mapped = mapDebugRunResultToEditor(sessionRun, lastEditorMap.value) || sessionRun
    resultHints = buildDebugExecutionHints(mapped)
  }
  return mergeDebugExecutionHints(
    mergeDebugExecutionHints(optimistic, runningHints),
    resultHints,
  )
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
    openDialogVisible.value = false
    opening.value = false
    scheduleCheckStepsStale()
    scheduleSyncSelectedStepToRunner(props.selectedStepIndex)

  } else if (val?.id && val?.status === 'ready') {

    openDialogVisible.value = false
    scheduleCheckStepsStale()

  }

}, { deep: true })

// 工具条执行完成后 last_result 变化：立刻吸收，不依赖下一次 1.5s 轮询才刷新卡片
watch(
  () => session.value?.last_result,
  (lr, prev) => {
    if (!lr || lr === prev) return
    if (lr.type !== 'run') return
    if (running.value) return
    absorbExternalRunResultFromSession()
  },
)



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

  const status = session.value?.status
  if (status === 'ready') {
    ElMessage.info('调试浏览器已打开，可直接试跑或拾取')
    return
  }
  if (status && ['starting', 'running', 'closing'].includes(status)) {
    ElMessage.warning('交互调试会话进行中，请稍候')
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

function onOpenDialogClosed() {
  // 请求进行中关窗视为取消：作废 in-flight，避免取消后仍挂上会话
  if (opening.value) {
    openSessionGen += 1
  }
  resetOpenForm()
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
  if (notice.reason === 'runner_offline' || notice.reason === '执行器异常下线') {
    ElNotification.error(notice.message)
    return
  }
  if (notice.reason === 'admin_force_stop') {
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
  // 拖拽改序会连续触发 deep watch；略拉长防抖，减少与 select_step 抢命令槽
  staleCheckTimer.value = setTimeout(() => {
    staleCheckTimer.value = null
    checkStepsStale()
  }, 800)
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
    } else if (stepsStale.value && syncing.value) {
      pendingResync.value = true
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
  if (syncing.value) {
    pendingResync.value = true
    return false
  }
  syncing.value = true
  try {
    let ok = false
    do {
      pendingResync.value = false
      try {
        await uiDebugApi.syncSteps(
          session.value.id,
          { steps: props.steps },
          (silent || quiet) ? { skipErrorHandler: true } : {},
        )
      } catch (e) {
        const status = e?.status || e?.response?.status
        const detail = e?.data?.detail || e?.response?.data?.detail || ''
        // 命令槽被占用：等会话回到 ready 后静默再试一次（拖拽连点常见）
        if ((silent || quiet) && status === 409) {
          const ready = await waitUntilReady(45000)
          if (ready !== 'ready') {
            if (!silent) {
              ElMessage.error(typeof detail === 'string' && detail ? detail : '同步步骤失败')
            }
            return false
          }
          await uiDebugApi.syncSteps(
            session.value.id,
            { steps: props.steps },
            { skipErrorHandler: true },
          )
        } else {
          throw e
        }
      }
      const status = await waitUntilReady()
      if (status === 'ready') {
        stepsStale.value = false
        // 静默自动同步很频繁，不能清空调试结果，否则工具条刚写入的「调试成功」会被抹掉
        if (!silent) {
          mergedLastResult.value = null
          lastSeenRunFingerprint.value = ''
        }
        if (!silent) {
          if (quiet) {
            ElMessage.success('已自动同步最新步骤')
          } else {
            ElNotification.success('步骤已同步到 Runner')
          }
        }
        ok = true
      } else {
        ok = false
        break
      }
    } while (pendingResync.value)
    return ok
  } catch (e) {
    if (!silent) {
      ElMessage.error(e?.response?.data?.detail || e?.data?.detail || e?.message || '同步步骤失败')
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

  const gen = ++openSessionGen
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
    const created = parseSessionResponse(res)

    if (gen !== openSessionGen) {
      // 用户已取消弹窗：关闭刚创建的会话，避免「取消了浏览器还开着」
      if (created?.id) {
        try {
          await uiDebugApi.closeSession(created.id)
        } catch {
          /* ignore */
        }
      }
      return
    }

    session.value = created

    syncIdleBaseline(session.value)

    mergedLastResult.value = null
    lastSeenRunFingerprint.value = ''
    lastEditorMap.value = []

    startPolling()

    opening.value = false
    openDialogVisible.value = false
    ElNotification.success('调试浏览器正在 Runner 上启动，请稍候…')

  } catch (e) {

    if (gen === openSessionGen) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '打开调试会话失败')
    }

  } finally {

    if (gen === openSessionGen) {
      opening.value = false
    }

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

  localRunningEditorIndices.value = [...valid]
  running.value = true
  ElMessage.info(valid.length === 1 ? `正在执行第 ${valid[0] + 1} 步…` : `正在执行 ${valid.length} 个步骤…`)
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
    // 记住本轮平台执行留下的 session.last_result，后续轮询不要当成「工具条新结果」冲掉合并缓存
    lastSeenRunFingerprint.value = fingerprintDebugRunResult(session.value?.last_result)
    return accumulated.length > 0 && mergedLastResult.value?.status !== 'fail'
  } finally {
    running.value = false
    localRunningEditorIndices.value = []
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
      lastSeenRunFingerprint.value = ''
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

/**
 * 工具条「执行本步/到结尾」直报 step_result：不经平台 run API，不会走 runEditorIndices。
 * 若仍保留上次平台多段的 mergedLastResult，步骤卡片状态会一直不更新。
 */
async function absorbExternalRunResultFromSession(options = {}) {
  if (running.value) return
  const lr = session.value?.last_result
  if (lr?.type !== 'run') return
  const fp = fingerprintDebugRunResult(lr)
  if (!fp || fp === lastSeenRunFingerprint.value) return
  lastSeenRunFingerprint.value = fp

  let editorMap = lastEditorMap.value
  if ((!editorMap || !editorMap.length) && props.steps?.length) {
    try {
      const allIdx = props.steps.map((_, i) => i)
      const plan = await resolveEditorRunPlan(allIdx)
      if (!plan.stale && plan.editorMap?.length) {
        lastEditorMap.value = plan.editorMap
        editorMap = plan.editorMap
      }
    } catch {
      // 映射失败时按会话下标展示，无片段场景通常仍正确
    }
  }

  const mapped = mapDebugRunResultToEditor(lr, editorMap)
  if (!mapped) return
  mergedLastResult.value = mergeIncomingDebugRunResult(mergedLastResult.value, mapped)
  resultExpanded.value = true
  if (options.notify !== false) {
    notifyToolbarRunResult(mapped)
  }
}

function notifyToolbarRunResult(mapped) {
  if (!mapped) return
  const steps = mapped.steps || []
  const failed = steps.find((s) => ['fail', 'failed', 'error'].includes(String(s?.status || '').toLowerCase()))
  const statusFail = ['fail', 'failed', 'error', 'cancelled'].includes(String(mapped.status || '').toLowerCase())
  if (failed || statusFail) {
    const idx = Number(failed?.step_index ?? mapped.from_index ?? 0) + 1
    const detail = String(failed?.message || mapped.message || '').trim()
    ElMessage.error(detail ? `工具条：第 ${idx} 步失败 — ${detail}` : `工具条：第 ${idx} 步失败`)
    return
  }
  const from = Number(mapped.from_index ?? 0) + 1
  const through = Number(mapped.through_index ?? from - 1) + 1
  if (from === through) {
    const outcome = formatStepOutcomeText(steps.find((s) => Number(s?.step_index) === from - 1) || steps[0])
    const brief = outcome ? outcome.replace(/\s+/g, ' ').slice(0, 120) : ''
    ElMessage.success(brief ? `工具条：第 ${from} 步成功 — ${brief}` : `工具条：第 ${from} 步执行成功`)
  } else {
    ElMessage.success(`工具条：第 ${from}～${through} 步执行成功`)
  }
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
      mergedLastResult.value = null
      lastSeenRunFingerprint.value = ''
      stepsStale.value = false

    } else if (session.value?.status === 'error') {

      stopPolling()

    } else {
      await absorbExternalRunResultFromSession()
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
    // 同步步骤进行中不抢命令槽；结束后会再 syncSelectedStepToRunner
    if (syncing.value) return
    syncSelectedStepToRunner(editorIndex)
  }, 280)
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

async function verifySelectedStep(opts = {}) {
  if (!session.value?.id || !canLocatorAction.value) return
  locatorBusy.value = true
  try {
    if (opts.forceSync || stepsStale.value) {
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
    // 候选通常无 iframe|| 前缀；保留拾取时已解析的 frame，避免切候选后丢失
    pickPreview.element_locator = split.locator || item
    if (pickPreview.frame) {
      pickPreview.locator = `${pickPreview.frame}||${pickPreview.element_locator}`
    }
  }
}

function openPickDialog(payload) {
  pickPreview.locator = payload.locator || ''
  pickPreview.frame = payload.frame || ''
  pickPreview.element_locator = payload.element_locator || ''
  pickPreview.candidates = payload.candidates || payload.meta?.candidates || []
  pickPreview.meta = payload.meta || {}
  const stepCount = props.steps?.length || 0
  const sel = Number(props.selectedStepIndex)
  if (stepCount <= 0) {
    pickPlaceMode.value = 'after'
    pickTargetStepIndex.value = 0
  } else {
    // 有选中步时默认「步骤后插入」，便于连点补步骤；要改定位器可选手动切到「替换」
    pickPlaceMode.value = 'after'
    pickTargetStepIndex.value = Number.isFinite(sel) && sel >= 0 && sel < stepCount ? sel : stepCount - 1
  }
  const suggested = suggestPickStepTemplate(payload.meta || payload.element || {}, {
    frame: payload.frame || '',
  })
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

watch(pickPlaceMode, (mode) => {
  const n = props.steps?.length || 0
  if (!n && mode !== 'after') {
    pickPlaceMode.value = 'after'
    pickTargetStepIndex.value = 0
    return
  }
  if ((mode === 'before' || mode === 'replace') && Number(pickTargetStepIndex.value) >= n) {
    pickTargetStepIndex.value = Math.max(0, n - 1)
  }
})

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
  if (pickInsertMethod.value === 'frame_fill_value') {
    return {
      keyword: 'iframe内元素输入',
      method: 'frame_fill_value',
      params: { frame: '', locator: '', value: '', index: 1 },
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
  let refIndex = Number(pickTargetStepIndex.value)
  const place = pickPlaceMode.value
  const common = {
    locator: pickPreview.locator,
    frame: pickPreview.frame,
    element_locator: pickPreview.element_locator,
    match_index: pickPreview.meta?.matchIndex || 1,
    candidates: pickPreview.candidates,
    meta: pickPreview.meta,
  }

  if (place === 'replace') {
    if (!stepCount || !Number.isFinite(refIndex) || refIndex < 0 || refIndex >= stepCount) {
      ElMessage.warning('请选择要替换的步骤')
      return
    }
    emit('apply-locator', {
      mode: 'replace',
      stepIndex: refIndex,
      ...common,
    })
  } else {
    let insertAt = 0
    if (!stepCount) {
      insertAt = 0
    } else if (place === 'before') {
      if (!Number.isFinite(refIndex) || refIndex < 0 || refIndex >= stepCount) {
        ElMessage.warning('请选择参照步骤')
        return
      }
      insertAt = refIndex
    } else {
      // after：参照步之后；选「末尾」时 value 已是 length
      if (!Number.isFinite(refIndex) || refIndex < 0) refIndex = stepCount
      insertAt = refIndex >= stepCount ? stepCount : refIndex + 1
    }
    emit('apply-locator', {
      mode: 'insert',
      insertAt,
      template: pickInsertTemplate(),
      ...common,
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
    // 恢复会话时忽略历史拾取/高亮/执行结果提示，避免立刻弹旧窗或刷 toast
    lastSeenRunFingerprint.value = fingerprintDebugRunResult(data.last_result)
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

  syncStepsFromEditor,

  verifySelectedStep,

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

  align-items: center;

}

.debug-help-icon {
  margin-left: 2px;
  font-size: 15px;
  color: var(--el-text-color-secondary);
  cursor: help;
  vertical-align: middle;
}

.debug-help-icon:hover {
  color: var(--el-color-primary);
}

.pick-dialog-tip {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.pick-place-hint {
  margin: -2px 0 0 84px;
  font-size: 12px;
  color: var(--el-color-primary);
  line-height: 1.4;
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
.pick-shell-warning {
  margin-top: 10px;
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



